# HWP 자동화 무한 루프 해결 - 핵심 기술 문서

> **⚠️ CRITICAL**: 이 문서는 HWP 자동화의 핵심 문제와 해결책을 담고 있습니다.  
> 무한 루프 발생 시 반드시 이 문서를 먼저 읽고 구현하세요!

---

## 🎯 문제의 본질

### **왜 `hwp.Open()`에서 무한 루프가 발생하는가?**

```python
# ❌ 이 코드는 보안 팝업이 뜨면 영원히 리턴하지 않습니다!
hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
hwp.Open(filepath)  # 👈 메인 스레드 완전 블로킹!
```

**근본 원인:**
1. **COM STA 모델**: HWP 객체는 Single Threaded Apartment 모델로 동작
2. **동기 호출**: `hwp.Open()`은 동기(synchronous) 메서드
3. **보안 팝업**: 팝업이 뜨면 사용자가 닫을 때까지 메서드가 리턴하지 않음
4. **스레드 블로킹**: 메인 스레드가 완전히 멈춰서 Watchdog도 소용없음

---

## 🚫 실패한 시도들

### ❌ 시도 1: 별도 스레드에서 Open() 호출
```python
def _open_thread():
    self.hwp.Open(path)  # COM Apartment 에러 발생!
```
**실패 이유**: HWP 객체는 메인 스레드에서 생성됨 → 다른 스레드에서 사용 불가

### ❌ 시도 2: Monitor 스레드로 타임아웃 감지
```python
def _monitor_thread():
    time.sleep(30)
    print("30초 경과!")  # 감지만 하고 해결 못함
```
**실패 이유**: 감지해도 블로킹된 메인 스레드를 중단할 방법이 없음

### ❌ 시도 3: Watchdog으로 팝업 클릭
```python
# 별도 스레드에서
win32gui.PostMessage(button_hwnd, win32con.BM_CLICK, 0, 0)
```
**실패 이유**: 버튼을 클릭해도 `hwp.Open()`이 내부적으로 대기 상태라 리턴 안 함

---

## ✅ 최종 해결책: 프로세스 격리 방식

> **한컴 공식 포럼**: "한글 오토메이션은 멀티스레드를 지원하지 않으므로, 각 작업마다 별도 프로세스를 띄워야 합니다."

### **핵심 아이디어**
- **워커 프로세스**: HWP 제어 전담 (블로킹되어도 메인 프로세스는 자유)
- **IPC**: `multiprocessing.Queue`로 결과 전달
- **타임아웃**: 30초 초과 시 워커 프로세스 강제 종료 (`terminate()`)

### **구현 예시**

```python
from multiprocessing import Process, Queue
import win32com.client
import pythoncom

def hwp_worker(filepath, result_queue):
    """워커 프로세스: HWP 제어 전담"""
    try:
        # 1. COM 초기화 (각 프로세스마다 필수!)
        pythoncom.CoInitialize()
        
        # 2. HWP 객체 생성
        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
        
        # 3. 보안 모듈 등록 (중요!)
        hwp.RegisterModule("FilePathCheckDLL", "레지스트리_키_이름")
        
        # 4. 파일 열기
        hwp.Open(filepath, "HWP", "forceopen:true")
        
        # 5. 작업 수행 (예: PDF 변환)
        pdf_path = filepath.replace(".hwp", ".pdf")
        hwp.SaveAs(pdf_path, "PDF")
        
        # 6. 성공 결과 전달
        result_queue.put({"status": "success", "pdf_path": pdf_path})
        
        # 7. 정리
        hwp.Quit()
        pythoncom.CoUninitialize()
        
    except Exception as e:
        result_queue.put({"status": "error", "message": str(e)})
        pythoncom.CoUninitialize()


def open_hwp_safe(filepath, timeout=30):
    """메인 프로세스: 타임아웃 제어"""
    result_queue = Queue()
    
    # 워커 프로세스 시작
    worker = Process(target=hwp_worker, args=(filepath, result_queue))
    worker.start()
    
    # 타임아웃 대기
    worker.join(timeout=timeout)
    
    # 타임아웃 체크
    if worker.is_alive():
        print(f"[Timeout] {timeout}초 초과 - 워커 프로세스 강제 종료")
        worker.terminate()
        worker.join()
        return {"status": "timeout"}
    
    # 결과 수신
    if not result_queue.empty():
        return result_queue.get()
    else:
        return {"status": "error", "message": "No result from worker"}


# 사용 예시
result = open_hwp_safe("test.hwp", timeout=30)
if result["status"] == "success":
    print(f"PDF 생성 완료: {result['pdf_path']}")
elif result["status"] == "timeout":
    print("타임아웃 발생 - 다음 파일로 진행")
else:
    print(f"에러 발생: {result['message']}")
```

---

## 🔑 중요한 구현 포인트

### 1️⃣ **RegisterModule 올바른 사용법**

```python
# ❌ 잘못된 방법 (DLL 파일명 사용)
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule.dll")

# ✅ 올바른 방법 (레지스트리 키 이름 사용)
hwp.RegisterModule("FilePathCheckDLL", "MySecurityModule")
```

**레지스트리 경로:**
```
HKEY_CURRENT_USER\Software\HNC\HwpAutomation\Modules
  - 값 이름: MySecurityModule
  - 값 데이터: C:\Path\To\FilePathCheckerModule.dll
```

### 2️⃣ **각 프로세스마다 COM 초기화 필수**

```python
# 워커 프로세스 시작 시
pythoncom.CoInitialize()

# 워커 프로세스 종료 시
pythoncom.CoUninitialize()
```

### 3️⃣ **타임아웃 값 설정**

- **일반 파일**: 10~30초
- **대용량 파일**: 60초
- **네트워크 드라이브**: 90초

---

## 🛡️ 추가 방어 전략

### **Plan A: 레지스트리 보안 모듈 등록 (최우선)**
- 팝업 자체를 방지하는 가장 근본적인 해결책
- `HwpRegistryManager`로 자동 등록 구현

### **Plan B: 프로세스 격리 (필수)**
- 레지스트리 등록이 실패해도 타임아웃으로 복구 가능
- 무한 루프 완전 차단

### **Plan C: Watchdog (보조)**
- 예상치 못한 팝업 자동 클릭
- 프로세스 격리와 병행 가능

---

## 📋 체크리스트

구현 전 반드시 확인:

- [ ] `multiprocessing.Process` 사용 (threading.Thread ❌)
- [ ] 워커 함수에서 `pythoncom.CoInitialize()` 호출
- [ ] `RegisterModule` 호출 시 레지스트리 키 이름 사용
- [ ] `Queue`로 결과 전달
- [ ] `worker.join(timeout=N)` 설정
- [ ] `worker.is_alive()` 체크 후 `terminate()` 호출
- [ ] 워커 종료 시 `pythoncom.CoUninitialize()` 호출

---

## 🔗 참고 자료

- **한컴 공식 포럼**: 멀티스레드 미지원 공식 확인
- **Windows COM 문서**: STA 모델 설명
- **Python multiprocessing**: 프로세스 격리 가이드

---

## 🚨 절대 하지 말아야 할 것

1. ❌ **threading.Thread로 hwp.Open() 호출** → COM Apartment 에러
2. ❌ **메인 스레드에서 동기 Open() 호출** → 무한 루프
3. ❌ **RegisterModule에 DLL 파일명 전달** → 보안 모듈 등록 실패
4. ❌ **타임아웃 없이 worker.join() 호출** → 메인 프로세스도 블로킹

---

**마지막 업데이트**: 2026-01-20  
**작성자**: AnG Engine Team  
**버전**: 1.0 (Final Solution)
