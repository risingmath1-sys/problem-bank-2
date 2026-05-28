# 🔍 전수 점검 보고서 (2026-05-02)

**대상**: `backend/main_gui.py` (6,902줄, 7개 탭)
**방법**: 6개 Agent 병렬 코드 정독
**총 발견 이슈**: 50건+

---

## 🔴 CRITICAL — 데이터 정합성 / 시스템 안정성 (즉시 수정 권장)

| # | 탭 | 함수 / 위치 | 이슈 | 영향 |
|---|-----|------------|------|------|
| **1** | 사용자관리 | `_users_change_role`, `_users_delete`, `_users_toggle_active` | **마지막 admin 보호 부재** — UI 본인 가드만 있음. 다른 admin이 본인 외 admin을 강등/삭제 가능 | 🚨 **시스템 잠김** |
| **2** | 시험지관리 | `_lib_edit_info` (~6692) | raw SQL UPDATE → **Firestore 미동기화** | 양쪽 DB 불일치 (정책 위배) |
| **3** | 시험지관리 | `_lib_show_problem_view` 인라인 삭제 (~6423) | sqlite3 직접 → **Firestore 미동기화** | 양쪽 DB 불일치 |
| **4** | 문제관리 | `_mgr_delete_files`, `_mgr_restore_all_excluded` | **권한 체크 전무** — 일반 user도 영구 삭제/일괄 해제 가능 | 데이터 손실 |
| **5** | 문제관리 | 파괴적 작업 전반 | Firestore 동기화 호출 미확인 (db_engine 검증 필요) | 양쪽 DB 불일치 |
| **6** | 문제등록 | `start_scan.run()` 백그라운드 스레드 | tkinter 위젯에 직접 접근 (`self.log`, `status_label.config`, `_update_stats`) | 비결정적 크래시 |

---

## 🟠 HIGH — 사용자 직접 영향 (이번 주 수정 권장)

| # | 탭 | 함수 / 위치 | 이슈 |
|---|-----|------------|------|
| **7** | 랜덤출제 | `_go_to_step_2` (2119, 3940) | **메서드 중복 정의** → 두 번째가 덮어씀 (`next_step3_mode="new"` 누락) |
| **8** | 랜덤출제 | `var_recent_first` (최신기출 우선) | **dead UI** — 어디서도 안 읽음 (체크박스 무효) |
| **9** | 랜덤출제 | `_run_hwp_thread` `progress_var` | **진행률 게이지 안 차오름** (라벨만 변경) |
| **10** | 시험지관리 | `_lib_move_test`, `_lib_copy_test` | **이동/복사 실패 시 messagebox 누락** ← "안 먹는다" 증상의 진짜 원인 |
| **11** | 원본출제 | `_orig_save_to_db` | DB 예외 미처리 (`res['success']` KeyError 가능) |
| **12** | 홈 | `_update_home_stats` (333) | **silent fail** (`except: cnt=0`) → DB 단절 시 "총 0문제"로 표시 |
| **13** | 문제등록 | `self.progress` 위젯 | 정의됐지만 **미사용** → 사용자 입장 정지 상태처럼 보임 |
| **14** | 랜덤출제 | `_distribute_evenly`/`_distribute_ratio`/`_collect_selected_units` | **메서드 중복 정의** 다수 (유지보수 위험) |
| **15** | 랜덤출제 | 4715줄 안내 문자열 | `guiـdebug.log` (ARABIC TATWEEL `ـ` 포함) → `gui_debug.log` 정정 필요 |

---

## 🟡 MEDIUM — UX / 성능 / 메모리 (시간 되면)

| # | 탭 | 이슈 |
|---|-----|------|
| 16 | 원본출제 | `_orig_search` 매번 더미 `tk.Entry()` 생성 → 메모리 누수 |
| 17 | 시험지관리 | `_lib_show_problem_view` `bind_all("<MouseWheel>")` → 전역 가로채기 |
| 18 | 사용자관리 | 본인 비활성화/삭제 시 즉시 로그아웃 미구현 |
| 19 | 사용자관리 | 마우스 휠 스크롤 미바인딩 (사용자 많아지면 UX 저하) |
| 20 | 문제등록 | 취소 버튼 없음 (장시간 스캔 중단 불가) |
| 21 | 문제등록 | `check_duplicate_exam` 실패 시 `start_btn` 잠김 |
| 22 | 문제관리 | 무필터 NAESIN_A 진입 시 6,500건 즉시 그룹핑 → 체감 지연 |
| 23 | 랜덤출제 | 트리/리스트 N+1 DB 호출 (단원당 query_counts) |
| 24 | 랜덤출제 | `_apply_sort` 후 batch 통합 → 이전(undo) 단위 깨짐 |
| 25 | 랜덤출제 | 문항번호 필터 켜고 미입력 시 silent ignore |
| 26 | 랜덤출제 | Step3 삭제 시 `p['id']` 타입 불일치 가능 (string vs int) |
| 27 | 원본출제 | 학교노드 클릭 시 카운트 라벨 미갱신 |
| 28 | 원본출제 | 소스 전환 시 입력값 잔존 (UX 혼란) |
| 29 | 원본출제 | 비-내신 소스에서 `diff_level` 무시 |
| 30 | 시험지관리 | `_lib_refresh_tests` `created_at` None 시 TypeError 가능 |
| 31 | 시험지관리 | 이동 시 폴더 트리 미새로고침 |
| 32 | 홈 | 폴더 경로 Entry `state="readonly"` 미적용 (직접 타이핑 가능) |
| 33 | 홈 | `_on_tab_changed` silent fail |
| 34 | 문제관리 | `_mgr_load_excluded_only` GROUP BY 비표준 (school 임의값) |
| 35 | 문제관리 | `_mgr_edit_cell` 빈 unit_code 복원 불가 (MOCK_EXAM 정책 충돌) |
| 36 | 문제관리 | `_backend_dir` NameError 위험 |
| 37 | 문제관리 | 우측 상태 다중 선택 토글 미지원 |

---

## 🟢 LOW — 미세 개선

- 원본출제: `_orig_finish` UX/표현 불일치
- 원본출제: `_orig_add_all` 데드코드
- 원본출제: 다중 선택 시 첫 매칭만 처리 (안내 없음)
- 사용자관리: 임시 비밀번호 평문 표시 (의도된 듯)
- 사용자관리: 다이얼로그 위치 계산 (`winfo_width()=1` 가능)

---

## 📊 통계

| 우선순위 | 개수 |
|---------|------|
| 🔴 CRITICAL | 6 |
| 🟠 HIGH | 9 |
| 🟡 MEDIUM | 22 |
| 🟢 LOW | 5 |
| **합계** | **42+** |

---

## 🚀 권장 수정 순서

### 1단계 (오늘) — Critical 6건
- 마지막 admin 보호 (#1)
- Firestore 동기화 누락 2곳 (#2, #3)
- 권한 체크 추가 (#4, #5)
- 스레드 안전성 (#6)

### 2단계 (이번 주) — High 9건
- 랜덤출제 중복 메서드 정리 (#7, #14)
- 죽은 UI 정리 (#8, #15)
- 진행률 표시 (#9, #13)
- 사용자 피드백 (#10, #11, #12)

### 3단계 (시간 되면) — Medium 22건
- 메모리/성능 최적화
- UX 개선

### 4단계 (백로그) — Low 5건

---

**다음 단계**: 사용자 승인 후 Critical 6건부터 수정 시작
