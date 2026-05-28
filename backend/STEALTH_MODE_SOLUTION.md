# HWP 스텔스 모드 완전 해결 기술 문서

> **작성일**: 2026-03-01
> **상태**: ✅ 완전 해결 (실사용 검증 완료)

---

## 1. 문제 현상

HWP 파일 인덱싱 시 다음 문제들이 발생:

1. "이 경로에 접근을 허용하시겠습니까?" 보안 팝업이 매번 등장
2. HWP 창이 화면 전면에 나타남
3. 마우스/키보드 포커스가 HWP로 강제 이동됨
4. 다른 작업을 할 수 없는 상태

---

## 2. 근본 원인 분석

### 2-1. 원인의 연쇄 구조

```
FilePathCheckerModule.dll 미설치
        ↓
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule") → FAIL (returns False)
        ↓
HWP가 보안 모듈 없음을 감지
        ↓
hwp.Open() 호출 시마다 "허용하시겠습니까?" 모달 다이얼로그 생성
        ↓
모달 다이얼로그 = 포커스 의존 창 → HWP로 포커스 강탈
        ↓
사용자 작업 방해 + 스텔스 불가
```

### 2-2. 오해하기 쉬운 포인트

| 오해 | 실제 |
|------|------|
| "watchdog이 버튼을 못 클릭해서 문제" | watchdog은 증상 완화책일 뿐, 근본 원인 아님 |
| "HWP 버전(2020) 버그" | 버전과 무관, DLL 미등록이 원인 |
| "`forceopen:true`로 팝업 우회 가능" | 이 옵션은 파일 형식 에러 무시용, 보안 팝업과 무관 |
| "레지스트리 경로가 틀렸다" | 경로 자체는 맞음. 경로 안에 값이 없는 게 문제 |

### 2-3. 진단 확인 방법

```
레지스트리: HKEY_CURRENT_USER\Software\HNC\HwpAutomation\Modules
→ 키는 존재하지만 내부에 값이 없음 (비어 있음)
→ FilePathCheckerModule.dll 파일이 PC 어디에도 없음
```

---

## 3. 해결 방법

### FilePathCheckerModule.dll이란?

- 한컴 HWP 자동화 SDK의 보안 모듈
- HWP에게 "이 경로의 파일은 신뢰된 자동화 프로그램이 여는 것"임을 알림
- 기본 HWP 설치에는 **포함되지 않음** (개발자 SDK에만 포함)
- 이 DLL이 등록되어 있으면 보안 팝업이 아예 생성되지 않음

### 해결 절차

#### Step 1: pyhwpx 패키지 설치

```bash
pip install pyhwpx
```

`pyhwpx` 패키지 안에 `FilePathCheckerModule.dll`이 포함되어 있음.

DLL 위치:
```
C:\Users\{사용자}\AppData\Local\Programs\Python\Python{버전}\Lib\site-packages\pyhwpx\FilePathCheckerModule.dll
```

#### Step 2: 레지스트리 등록

```python
import winreg, os, site

# DLL 경로 찾기
dll_path = None
for site_dir in site.getsitepackages():
    candidate = os.path.join(site_dir, "pyhwpx", "FilePathCheckerModule.dll")
    if os.path.exists(candidate):
        dll_path = candidate
        break

# 레지스트리 3곳에 등록
REG_PATHS = [
    r"Software\HNC\HwpAutomation\Modules",
    r"Software\HNC\HwpAutomation\Modules64",
    r"Software\HNC\HwpCtrl\Modules",
]
MODULE_NAME = "FilePathCheckerModule"

for reg_path in REG_PATHS:
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
    winreg.SetValueEx(key, MODULE_NAME, 0, winreg.REG_SZ, dll_path)
    winreg.CloseKey(key)
    print(f"등록 완료: HKCU\\{reg_path}")
```

#### Step 3: 등록 확인

```python
import winreg, os

key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                     r"Software\HNC\HwpAutomation\Modules", 0, winreg.KEY_READ)
val, _ = winreg.QueryValueEx(key, "FilePathCheckerModule")
winreg.CloseKey(key)
print(f"등록값: {val}")
print(f"파일 존재: {os.path.exists(val)}")
```

#### Step 4: hwp_core.py에서 RegisterModule 호출 (이미 구현됨)

```python
reg_name = HwpRegistryManager.get_registered_value_name()  # "FilePathCheckerModule"
result = hwp.RegisterModule("FilePathCheckDLL", reg_name)
# result = True → 성공, False → 실패
```

**중요**: `RegisterModule`의 두 번째 인자는 DLL 파일명이 아니라 **레지스트리 값 이름**이어야 함.

```python
# ✅ 올바른 방법
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")  # 레지스트리 키 이름

# ❌ 잘못된 방법
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule.dll")  # DLL 파일명 직접 전달
```

---

## 4. 코드 변경 사항

### hwp_registry_manager.py

`_find_hwp_dll()` 메서드에 pyhwpx 패키지 경로 탐색 추가:

```python
# 2. pyhwpx 패키지에서 탐색 (pip install pyhwpx)
try:
    import site
    for site_dir in site.getsitepackages():
        pyhwpx_dll = os.path.join(site_dir, "pyhwpx", "FilePathCheckerModule.dll")
        if os.path.exists(pyhwpx_dll):
            print(f"[Info] Found DLL in pyhwpx package: {pyhwpx_dll}")
            return pyhwpx_dll
except Exception:
    pass
```

---

## 5. 결과

| 항목 | 해결 전 | 해결 후 |
|------|---------|---------|
| 보안 팝업 | 매번 등장 | 완전히 사라짐 |
| HWP 창 | 화면에 나타남 | 보이지 않음 |
| 포커스 탈취 | 발생 | 없음 |
| 다른 작업 | 불가 | 완전 자유 |
| 인덱싱 로그 | Watchdog 메시지 | 조용히 성공 |

**인덱싱 중 아무것도 안 뜨면 정상** — 그게 진짜 스텔스.

---

## 6. 새 PC 설정 체크리스트

새 환경에서 스텔스 모드를 작동시키려면:

- [ ] `pip install pyhwpx` 실행
- [ ] `HwpRegistryManager.register_module()` 한 번 실행 (프로그램 첫 실행 시 자동 시도됨)
- [ ] 인덱싱 로그에서 `RegisterModule('FilePathCheckerModule') SUCCESS` 확인
- [ ] 파일 하나 인덱싱해서 팝업 안 뜨는지 확인

---

## 7. 관련 파일

| 파일 | 역할 |
|------|------|
| `backend/hwp_core.py` | HWP 워커 프로세스, RegisterModule 호출 (284~292줄) |
| `backend/hwp_registry_manager.py` | DLL 탐색 및 레지스트리 등록 |
| `backend/HWP_AUTOMATION_CORE_SOLUTION.md` | 프로세스 격리 방식(multiprocessing) 설계 문서 |

---

## 8. 추가 참고

- `FilePathCheckerModule.dll`이 없는 경우 watchdog으로 팝업을 클릭하는 방법도 있으나,
  Win32 모달 다이얼로그 특성상 포커스 없이 신뢰성 있는 클릭이 불가능함.
  **DLL 등록이 유일한 근본 해결책.**

- watchdog(`_popup_watchdog`)은 예상치 못한 팝업(DLL 등록 후에도 간혹 발생 가능)에 대한
  보조 방어선으로 코드에 유지해도 됨. 단, 주된 의존 수단으로 사용하면 안 됨.
