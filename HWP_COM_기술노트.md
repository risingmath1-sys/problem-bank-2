# HWP COM 자동화 기술노트

> 작성일: 2026-03-02  
> 프로젝트: 문제은행2 자동 출제 시스템

---

## 1. 핵심 버그: Paste가 소스 파일에 붙여넣어지는 문제

### 증상
- 100문제 출제 실행 시, 소스 HWP 파일에 다른 학교 문제들이 1~2개씩 붙어버림
- 출력된 시험지는 소스 파일 내용 + 1문제만 있는 이상한 파일로 나옴
- 두 번째 소스 파일을 열기 시작하는 시점부터 발생 (첫 소스 파일 사용 중엔 정상)

### 근본 원인 (확정)
`hwp.Run("Paste")`는 **COM Active_XHwpDocument 기준이 아니라 Win32 UI 포커스 기준**으로 동작함.

`XHwpDocuments.Add(True)`로 새 소스 창을 열 때마다:
- `WM_ACTIVATE` / `WM_SETFOCUS` / `WM_MDIACTIVATE` 메시지가 HWP 내부 큐에 쌓임
- 이 메시지들이 **비동기**로 처리되어 SetActive(target) 이후에도 소스가 다시 active가 됨
- 결과: `COM Active_XHwpDocument.FullName` = target (정상으로 보임) / 실제 Paste 대상 = source (버그)

### 시도했으나 실패한 방법들

| 시도 | 이유 |
|------|------|
| `time.sleep(0.2)` after SetActive | WM_ACTIVATE 큐 드레인에 불충분 |
| 검증 루프 15회 × 0.1s (FullName 확인) | COM 속성은 target 반환하나 실제 UI 포커스는 source — 둘이 다름 |
| switch+paste 원자적 실행 (IPC 왕복 제거) | COM Active != Win32 UI 포커스 구조적 분리라 소용없음 |
| `SendMessage(WM_PASTE, 0, 0)` to target HWND | HWP 최상위 창이 WM_PASTE를 편집 컨트롤로 전달하지 않음 |
| `LockSetForegroundWindow` | 별도 프로세스(HWP.exe)에 무효 |

### 해결 방법: 2-인스턴스 분리 아키텍처

```
[이전] self.controller (source + target 모두)
         ↕ switch_doc 반복 ← WM_ACTIVATE 역전 발생

[현재] self.controller = source 전용 (Copy만 수행)
       target_ctrl     = target 전용 (Paste만 수행)
         → SetActive 호출 자체가 없음 → WM_ACTIVATE 역전 불가능
```

클립보드는 시스템 전체 공유이므로, 별도 프로세스 간 Copy → Paste 완벽히 동작함.

### 구현 위치
- `backend/hwp_generator.py`: `generate_exam()` 함수
  - `target_ctrl = RobustHwpController(visible=not stealth_mode)` (line ~122)
  - 소스 연산: `self.controller.XXX`
  - 타겟 연산: `target_ctrl.XXX`
  - `_remove_trailing_blank_lines(ctrl)` — ctrl 파라미터로 분기

---

## 2. HWP COM 핵심 지식

### Add(True) vs Add(False)
- `Add(True)`: 새 창으로 문서 생성 → WM_ACTIVATE 발생 (포커스 이슈 원인)
- `Add(False)`: 현재 창에서 문서 교체 → 기존 시험지 내용 날림 (절대 사용 금지)

### readonly:true 파라미터
- `hwp.Open(path, "HWP", "forceopen:true;readonly:true")` → HWP COM RPC 크래시 발생 (-2147023174)
- 항상 `"forceopen:true"` 만 사용할 것

### hwp.Run("Paste") 동작 기준
- **Win32 UI 포커스 (GetForegroundWindow)** 기준
- COM의 `Active_XHwpDocument`와 **분리될 수 있음**
- Add(True) 이후 반드시 이 분리 현상 발생

### SetActive_XHwpDocument() 한계
- UI 창 활성화 API (WM_ACTIVATE 포스팅) — 논리적 문서 전환 API가 아님
- 비동기: 호출 후 `Active_XHwpDocument.FullName` 확인 성공해도 Paste는 다른 문서로 갈 수 있음
- **Add(True) 이후에는 신뢰 불가**

### WM_ACTIVATE 큐 드레인
- Python 프로세스에서 `pythoncom.PumpWaitingMessages()` → HWP.exe 큐와 무관, 효과 없음
- HWP는 외부 메시지 펌핑 API 없음

---

## 3. 스텔스 모드 (보안 팝업 없이 백그라운드 실행)

### 해결 완료 (2026-03-01)
- **원인**: `FilePathCheckerModule.dll` 미등록 → RegisterModule 실패 → 매번 보안 팝업
- **해결**: `pip install pyhwpx` → 패키지 내 DLL 자동 포함
  - DLL 경로: `site-packages/pyhwpx/FilePathCheckerModule.dll`
  - 레지스트리 3곳 등록: `HKCU\Software\HNC\HwpAutomation\Modules`, `Modules64`, `HwpCtrl\Modules`
- **관련 파일**: `backend/hwp_registry_manager.py` (pyhwpx 경로 자동 탐색)

---

## 4. DB / 인덱싱 관련

### unit_code 규칙
- `unit_code` = 2022 교육과정 코드 (primary)
- `mapped_unit_code` = 원본 2015 코드

### DB migration 주의사항
- 반드시 `CASE WHEN` 방식 사용
- sequential UPDATE 금지 → cascade 버그 발생

### 소스 타입
| 값 | 설명 |
|----|------|
| NAESIN_ANG | 내신기출 (school != '') |
| SUNEUNG_SPECIAL | 수능특강 |
| SUNEUNG_COMPLETE | 수능완성 |
| MOCK_EXAM | 모의고사 |

---

## 5. 아키텍처 다이어그램

```
[main_gui.py]
    │
    ├─ HWPGenerator.generate_exam()
    │       │
    │       ├─ self.controller (RobustHwpController) ← source 전용
    │       │       └─ hwp_core.py Worker subprocess
    │       │               └─ HWP.exe (소스 파일 읽기 전용)
    │       │
    │       ├─ target_ctrl (RobustHwpController) ← target 전용 ★NEW
    │       │       └─ hwp_core.py Worker subprocess
    │       │               └─ HWP.exe (시험지 작성 전용)
    │       │
    │       └─ buffer_ctrl (RobustHwpController) ← 높이 측정 전용
    │               └─ hwp_core.py Worker subprocess
    │                       └─ HWP.exe (보이지 않는 버퍼)
    │
    └─ [클립보드] Copy(source) → Paste(target) 시스템 공유
```
