# 문항입력 프로그램 UI 설계 명세

## 📋 메인 화면 구성

### 입력 필드

#### 필수 입력
- **연도**: 텍스트 입력 (예: 2025)
- **학년**: 드롭다운 [고1, 고2, 고3]
- **학기**: 드롭다운 [1학기, 2학기]
- **시험**: 드롭다운 [중간고사, 기말고사, 모의고사, 기타]
- **과목**: 드롭다운 (교육과정에 따라 동적 변경)
  - 2022: 공통수학1, 공통수학2, 대수, 미적분1, 확률과 통계, 미적분2, 기하
  - 2015: 수학(상), 수학(하), 수학1, 수학2, 미적분, 확률과 통계, 기하

#### 선택 입력
- **학교명**: 텍스트 입력 (선택, 파일명에서 자동 추출 가능)

### 옵션 체크박스

```
☐ 구방식 태그 사용
☐ 2015 개정교과
```

**기본값**:
- 체크 안 됨 = 신방식 태그 + 2022 개정교과
- 체크 시 = 구방식 태그 + 2015 개정교과

**동작**:
- `2015 개정교과` 체크 시 → 과목 드롭다운 자동 변경

### 폴더 선택

```
폴더 경로: [G:\문제은행\문제은행2        ] [찾아보기]
```

### 실행 버튼

```
[스캔 시작]  [중지]  [로그 보기]
```

---

## 🎨 UI 레이아웃 (Tkinter)

```python
import tkinter as tk
from tkinter import ttk, filedialog

class ProblemInputApp:
    def __init__(self, root):
        self.root = root
        self.root.title("문항입력 프로그램")
        
        # 기본 설정
        frame = ttk.Frame(root, padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 연도
        ttk.Label(frame, text="연도:").grid(row=0, column=0, sticky=tk.W)
        self.year_entry = ttk.Entry(frame, width=20)
        self.year_entry.grid(row=0, column=1, sticky=tk.W)
        self.year_entry.insert(0, "2025")
        
        # 학년
        ttk.Label(frame, text="학년:").grid(row=1, column=0, sticky=tk.W)
        self.grade_combo = ttk.Combobox(frame, values=["고1", "고2", "고3"], width=18)
        self.grade_combo.grid(row=1, column=1, sticky=tk.W)
        self.grade_combo.current(0)
        
        # 학기
        ttk.Label(frame, text="학기:").grid(row=2, column=0, sticky=tk.W)
        self.semester_combo = ttk.Combobox(frame, values=["1학기", "2학기"], width=18)
        self.semester_combo.grid(row=2, column=1, sticky=tk.W)
        self.semester_combo.current(0)
        
        # 시험
        ttk.Label(frame, text="시험:").grid(row=3, column=0, sticky=tk.W)
        self.exam_combo = ttk.Combobox(frame, values=["중간고사", "기말고사", "모의고사", "기타"], width=18)
        self.exam_combo.grid(row=3, column=1, sticky=tk.W)
        self.exam_combo.current(0)
        
        # 과목
        ttk.Label(frame, text="과목:").grid(row=4, column=0, sticky=tk.W)
        self.subject_combo = ttk.Combobox(frame, width=18)
        self.subject_combo.grid(row=4, column=1, sticky=tk.W)
        
        # 학교명 (선택)
        ttk.Label(frame, text="학교명:").grid(row=5, column=0, sticky=tk.W)
        self.school_entry = ttk.Entry(frame, width=20)
        self.school_entry.grid(row=5, column=1, sticky=tk.W)
        ttk.Label(frame, text="(선택, 파일명에서 자동추출)", font=("", 8)).grid(row=5, column=2, sticky=tk.W)
        
        # 구분선
        ttk.Separator(frame, orient='horizontal').grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # 옵션 체크박스
        self.old_tag_var = tk.BooleanVar()
        self.old_tag_check = ttk.Checkbutton(frame, text="구방식 태그 사용", variable=self.old_tag_var)
        self.old_tag_check.grid(row=7, column=0, columnspan=2, sticky=tk.W)
        
        self.curriculum_2015_var = tk.BooleanVar()
        self.curriculum_2015_check = ttk.Checkbutton(
            frame, 
            text="2015 개정교과", 
            variable=self.curriculum_2015_var,
            command=self.update_subject_list
        )
        self.curriculum_2015_check.grid(row=8, column=0, columnspan=2, sticky=tk.W)
        
        # 초기 과목 리스트 설정
        self.update_subject_list()
        
        # 폴더 선택
        ttk.Separator(frame, orient='horizontal').grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(frame, text="폴더:").grid(row=10, column=0, sticky=tk.W)
        self.folder_entry = ttk.Entry(frame, width=40)
        self.folder_entry.grid(row=10, column=1, sticky=tk.W)
        ttk.Button(frame, text="찾아보기", command=self.browse_folder).grid(row=10, column=2, sticky=tk.W)
        
        # 실행 버튼
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=11, column=0, columnspan=3, pady=20)
        
        ttk.Button(button_frame, text="스캔 시작", command=self.start_scan).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="중지", command=self.stop_scan).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="로그 보기", command=self.show_log).pack(side=tk.LEFT, padx=5)
        
        # 진행 상황
        self.progress = ttk.Progressbar(frame, length=400, mode='determinate')
        self.progress.grid(row=12, column=0, columnspan=3, sticky=(tk.W, tk.E))
        
        # 로그 출력
        self.log_text = tk.Text(frame, height=10, width=60)
        self.log_text.grid(row=13, column=0, columnspan=3, pady=10)
        
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.log_text.yview)
        scrollbar.grid(row=13, column=3, sticky=(tk.N, tk.S))
        self.log_text['yscrollcommand'] = scrollbar.set
    
    def update_subject_list(self):
        """교육과정에 따라 과목 리스트 업데이트"""
        if self.curriculum_2015_var.get():
            subjects = ["수학(상)", "수학(하)", "수학1", "수학2", "미적분", "확률과 통계", "기하"]
        else:
            subjects = ["공통수학1", "공통수학2", "대수", "미적분1", "확률과 통계", "미적분2", "기하"]
        
        self.subject_combo['values'] = subjects
        self.subject_combo.current(0)
    
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)
    
    def start_scan(self):
        # 메타데이터 수집
        common_meta = {
            "year": self.year_entry.get(),
            "grade": self.grade_combo.get(),
            "semester": self.semester_combo.get(),
            "exam_type": self.exam_combo.get(),
            "subject": self.subject_combo.get(),
            "school": self.school_entry.get() or None,
            "curriculum": "2015" if self.curriculum_2015_var.get() else "2022",
            "tag_version": "v1" if self.old_tag_var.get() else "v2"
        }
        
        folder_path = self.folder_entry.get()
        
        # TODO: 스캔 로직 실행
        self.log(f"스캔 시작: {folder_path}")
        self.log(f"설정: {common_meta}")
    
    def stop_scan(self):
        self.log("스캔 중지")
    
    def show_log(self):
        self.log("로그 보기")
    
    def log(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = ProblemInputApp(root)
    root.mainloop()
```

---

## 🔄 데이터 흐름

1. **사용자 입력** → UI 폼
2. **체크박스 상태** → `curriculum`, `tag_version` 결정
3. **스캔 시작** → `common_meta` 생성
4. **폴더 스캔** → `hwp_metadata_parser_v2.py` 호출
5. **진행 상황** → 프로그레스바 + 로그 출력
6. **완료** → Firebase 업로드 + `registration_log.json` 기록

---

**작성일**: 2026-01-23  
**상태**: UI 설계 완료, 구현 대기 중
