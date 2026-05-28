# HWP 오토메이션 무한루프 문제 해결 방안

## 문제 진단

### 1. 무한루프 발생 원인
```
hwp_core.py:_initialize()
  → EnsureDispatch 실패 (line 114)
  → repair_com_registry() 호출 (line 117)
  → hwp.exe /regserver 실행 (hwp_registry_manager.py:186)
  → 새로운 HWP 인스턴스 생성 시도
  → 다시 EnsureDispatch 실패
  → 무한 반복
```

### 2. 핵심 문제점

#### A. `/regserver` 명령의 잘못된 사용
- `/regserver`는 **설치 시 한 번만** 실행하는 명령
- 런타임 중 반복 실행하면 COM 충돌 발생
- **동기 실행**으로 인해 프로세스가 멈춤

#### B. 과도한 파일 시스템 검색
- `_search_files()`가 `C:\Program Files` 전체를 재귀 탐색
- 매 초기화마다 수십 초 소요
- DLL 경로는 **한 번만 찾으면 됨**

#### C. 예외 처리 부재
- `repair_com_registry()` 실패 시 재시도 로직 없음
- 무한 재귀 방지 장치 없음

## 해결 방안

### 1. `/regserver` 호출 제거
```python
# hwp_core.py:116-119 삭제
# repair_com_registry()는 수동 유지보수 용도로만 사용
```

### 2. DLL 경로 캐싱
```python
# hwp_registry_manager.py
_DLL_PATH_CACHE = None

@classmethod
def get_dll_path(cls):
    global _DLL_PATH_CACHE
    if _DLL_PATH_CACHE and os.path.exists(_DLL_PATH_CACHE):
        return _DLL_PATH_CACHE
    
    # 레지스트리 확인
    # 파일 검색
    _DLL_PATH_CACHE = found_path
    return _DLL_PATH_CACHE
```

### 3. 재시도 로직 개선
```python
# hwp_core.py
MAX_RETRIES = 2
for attempt in range(MAX_RETRIES):
    try:
        self.hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        break
    except Exception as e:
        if attempt == MAX_RETRIES - 1:
            raise
        time.sleep(2)
```

### 4. RegisterModule 반환값 체크
```python
result = self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
if not result:
    print("[Warning] RegisterModule returned False - popups may appear")
```

## 수정 우선순위

1. **즉시 수정**: `repair_com_registry()` 호출 제거
2. **중요**: DLL 경로 캐싱 구현
3. **권장**: 재시도 로직 개선
4. **선택**: RegisterModule 반환값 로깅

## 테스트 계획

1. 수정된 코드로 HWP 초기화 1회 실행
2. 팝업 발생 여부 확인
3. 프로세스 정상 종료 확인
4. 연속 10회 초기화/종료 테스트
