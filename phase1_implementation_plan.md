# 📋 Phase 1: 스캔 엔진 구현 계획

## 목표
HWP 파일에서 ★S/★E 마커를 인식하고 문제 정보를 추출하여 Firebase에 업로드하는 로컬 프로그램 개발

---

## 핵심 기능

### 1. HWP 파일 제어
- [x] 한글 프로그램 COM API 연동 (`pywin32`)
- [ ] 파일 열기/닫기 안정화
- [ ] 프로세스 타임아웃 및 재시작 로직

### 2. 문제 범위 인식 (Endnote-Based Detection)
- [x] 미주 번호 위치 탐지 (HeadCtrl 사용)
- [x] 문제 시작점: 미주 -1단락 (태그 위치)
- [x] 문제 끝점: 다음 미주 또는 문서 끝
- [x] 무한루프 방지 로직 (타임아웃, 프로세스 격리)

### 3. 문제 정보 추출
- [ ] 미주 번호 추출
- [ ] 메타데이터 파싱 (난이도, 단원 등)
- [ ] 높이 측정 (보류 - 추후 테스트)

### 4. Firebase 연동
- [x] Firebase Admin SDK 설정
- [ ] Firestore에 문제 데이터 업로드
- [ ] 파일 인덱스 관리

### 5. 관리자 UI
- [ ] 공통 정보 입력 폼 (학교, 연도, 학기 등)
- [ ] 파일 선택 및 진행 상황 표시
- [ ] 에러 로그 출력

---

## 개발 우선순위

### 🔴 Priority 1: HWP 기본 제어 (1주)
**목표**: HWP 파일을 안정적으로 열고 닫기

```python
# hwp_controller.py
import win32com.client as win32
import time

class HwpController:
    def __init__(self):
        self.hwp = None
        
    def open_file(self, file_path, timeout=30):
        """HWP 파일을 안전하게 열기"""
        try:
            self.hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
            self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
            self.hwp.Open(file_path)
            return True
        except Exception as e:
            print(f"파일 열기 실패: {e}")
            return False
            
    def close_file(self):
        """HWP 파일 닫기"""
        if self.hwp:
            try:
                self.hwp.Clear(1)  # 저장하지 않고 닫기
                self.hwp.Quit()
            except:
                pass
            finally:
                self.hwp = None
```

**검증 방법**:
- 테스트 HWP 파일 10개 연속으로 열고 닫기
- 메모리 누수 확인
- 프로세스 정상 종료 확인

---

### 🟠 Priority 2: 문제 범위 탐지 로직 (1주)
**목표**: 미주 번호 기반으로 문제 시작/끝 위치를 안정적으로 찾기

> [!IMPORTANT]
> **새로운 접근법**: 사각형 마커(★S/★E) 제도를 폐지하고, 미주 번호와 태그 위치를 기반으로 문제 범위를 결정합니다.

```python
def get_problem_range(self, endnote_num, is_upper_problem):
    """
    미주 번호 기반 문제 범위 추출
    
    Args:
        endnote_num: 현재 문제의 미주 번호
        is_upper_problem: 상단 문제 여부 (True: 상단, False: 하단)
    
    Returns:
        dict: {'start_line': int, 'end_line': int}
    """
    # 1. 현재 미주 위치 찾기
    current_endnote_line = self.find_endnote_line(endnote_num)
    
    if is_upper_problem:
        # 상단 문제: 미주 위치부터 시작
        start_line = current_endnote_line
        
        # 다음 미주 찾기
        next_endnote_line = self.find_endnote_line(endnote_num + 1)
        
        if next_endnote_line:
            # 다음 태그는 미주 -1줄
            next_tag_line = next_endnote_line - 1
            # 끝점: 다음 태그로부터 위로 3줄
            end_line = next_tag_line - 3
        else:
            # 마지막 문제면 단 끝까지
            end_line = self.find_column_end(current_endnote_line)
    
    else:
        # 하단 문제: 태그(미주 -1줄)부터 시작
        tag_line = current_endnote_line - 1
        start_line = tag_line
        
        # 단 끝까지
        end_line = self.find_column_end(current_endnote_line)
    
    return {
        'start_line': start_line,
        'end_line': end_line
    }

def find_endnote_line(self, endnote_num):
    """미주 번호의 줄 위치 찾기"""
    # TODO: HWP API를 사용하여 미주 위치 탐지
    pass

def find_column_end(self, current_line):
    """현재 위치에서 단 끝 찾기 (단 나누기/쪽 나누기 직전)"""
    # TODO: HWP API를 사용하여 단 끝 탐지
    pass
```

**검증 방법**:
- 2단 구성, 각 단에 2개 문제가 있는 테스트 파일 준비
- 상단 문제 2개, 하단 문제 2개 정확히 추출되는지 확인
- 그림/수식이 포함된 문제에서 잘림 없이 추출되는지 확인
- 3줄 마진이 적절한지 검증

---

### 🟡 Priority 3: 미주 번호 추출 (3일)
**목표**: 각 문제의 미주 번호 추출

```python
def extract_endnote(self, start_pos):
    """★S 위치에서 미주 번호 추출"""
    # start_pos로 이동
    self.move_to_position(start_pos)
    
    # 미주 찾기 (★S 이후 첫 번째 미주)
    self.hwp.HAction.GetDefault("NextEndnote", 
                                self.hwp.HParameterSet.HSet)
    if self.hwp.HAction.Execute("NextEndnote", 
                                self.hwp.HParameterSet.HSet):
        # 미주 번호 가져오기
        endnote_num = self.hwp.GetFieldText("Endnote")
        return endnote_num
    
    return None
```

---

### 🟢 Priority 4: Firebase 업로드 (3일)
**목표**: 추출한 데이터를 Firestore에 저장

```python
# firebase_uploader.py
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

class FirebaseUploader:
    def __init__(self, cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()
        
    def upload_problem(self, problem_data):
        """문제 데이터 업로드"""
        problem_id = f"hwp_{problem_data['file_name']}_{problem_data['endnote']}"
        
        doc_data = {
            'problem_id': problem_id,
            'file_name': problem_data['file_name'],
            'endnote': problem_data['endnote'],
            'position': problem_data['position'],
            'source_school': problem_data['source_school'],
            'year': problem_data['year'],
            'grade': problem_data['grade'],
            'semester': problem_data['semester'],
            'exam_type': problem_data['exam_type'],
            'subject': problem_data['subject'],
            'created_at': firestore.SERVER_TIMESTAMP,
            'created_by': 'admin'
        }
        
        self.db.collection('problems').document(problem_id).set(doc_data)
        print(f"✅ {problem_id} 업로드 완료")
```

---

### 🔵 Priority 5: 관리자 UI (1주)
**목표**: Tkinter 기반 간단한 GUI

```python
# main_ui.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AnG 문제 스캐너")
        
        # 공통 정보 입력
        ttk.Label(root, text="학교명:").grid(row=0, column=0)
        self.school_entry = ttk.Entry(root)
        self.school_entry.grid(row=0, column=1)
        
        ttk.Label(root, text="연도:").grid(row=1, column=0)
        self.year_entry = ttk.Entry(root)
        self.year_entry.grid(row=1, column=1)
        
        # 파일 선택 버튼
        ttk.Button(root, text="파일 선택", 
                  command=self.select_file).grid(row=2, column=0)
        
        # 진행 상황
        self.progress = ttk.Progressbar(root, length=300)
        self.progress.grid(row=3, column=0, columnspan=2)
        
        # 로그
        self.log_text = tk.Text(root, height=10, width=50)
        self.log_text.grid(row=4, column=0, columnspan=2)
        
    def select_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("HWP files", "*.hwp")]
        )
        if file_path:
            self.scan_file(file_path)
            
    def scan_file(self, file_path):
        # TODO: HWP 스캔 로직 호출
        self.log(f"스캔 시작: {file_path}")
```

---

## 보류 사항

### 높이 측정
- 실제 테스트 파일로 검증 필요
- 그림/표 포함 시 정확도 확인
- 대안: 수동 입력 또는 표준 높이 사용

---

## 예상 일정

| 주차 | 작업 내용 | 산출물 |
|------|----------|--------|
| 1주 | HWP 기본 제어 + 마커 검색 | `hwp_controller.py` |
| 2주 | 미주 추출 + Firebase 연동 | `firebase_uploader.py` |
| 3주 | 관리자 UI + 통합 테스트 | `main_ui.py` |
| 4주 | 버그 수정 + 문서화 | 사용 설명서 |

---

## 다음 단계

1. ✅ 기술 분석 완료
2. ✅ Phase 1 계획 수립
3. ⏭️ **개발 환경 설정**
   - Python 가상환경 생성
   - 필요 라이브러리 설치
4. ⏭️ **Priority 1 개발 시작**
   - `hwp_controller.py` 작성
   - 기본 테스트

---

**작성일**: 2026-01-19  
**다음 리뷰**: Priority 1 완료 후
