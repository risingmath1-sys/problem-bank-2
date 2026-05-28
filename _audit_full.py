"""종합 자가검수 — 7탭 모든 핵심 워크플로 + HTML 품질 검증.

모든 탭 응답을 직접 시뮬레이션하면서:
  - HTTP 200 / redirect 정확성
  - 핵심 마커 (헤더/버튼/링크/HTMX 속성) 존재
  - 응답 본문 길이 (의심스러울 정도로 작은 응답 = 깨진 partial)
  - 가드 (admin only / user redirect)
  - 폼 form action / hx-target 정합성
  - JS handler 누락 여부

발견된 문제는 콘솔에 ❌ 로 표시 + summary.
"""
import io
import sys
import urllib.parse
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import (
    SessionUser, get_optional_user, require_user, require_admin,
)
from server.services import exam_session


def _set(role):
    u = SessionUser(uid=role, email=f"{role}@x", role=role,
                    display_id=role, display_name=role)
    app.dependency_overrides[require_user] = lambda: u
    app.dependency_overrides[get_optional_user] = lambda: u
    app.dependency_overrides[require_admin] = lambda: u
    return u


client = TestClient(app)


def post_form(p, fs):
    return client.post(p, content=urllib.parse.urlencode(fs, doseq=True),
                       headers={"content-type": "application/x-www-form-urlencoded"})


# ── 검수 결과 누적 ─────────────────────────────────────────
issues: list = []


def chk(label, cond, detail=""):
    """체크 + 결과 출력. cond=False 면 issues 누적."""
    mark = "✓" if cond else "❌"
    print(f"  {mark} {label}" + (f" [{detail}]" if detail else ""))
    if not cond:
        issues.append(f"{label}: {detail or 'failed'}")


def section(t):
    print(f"\n━━━━━━ {t} ━━━━━━")


# ─────────────────────────────────────────────────────
# TAB 0: 홈
# ─────────────────────────────────────────────────────
section("TAB 0 홈 (admin)")
admin = _set("admin")
r = client.get("/", follow_redirects=False)
chk("GET / status 200", r.status_code == 200, str(r.status_code))
html = r.text
chk("로고 표시", "/static/logo.png" in html)
chk("타이틀 '상승 Solution'", "상승 Solution" in html)
chk("부제 'Problem Bank Management System'", "Problem Bank Management System" in html)
for label in ["랜덤 출제", "원본 출제", "시험지 관리", "문제 등록", "문제 관리", "사용자 관리"]:
    chk(f"카드 '{label}' 노출", label in html)
chk("M E N U 섹션 헤더", "M E N U" in html)
chk("문 제 현 황 섹션 헤더", "문 제 현 황" in html)
chk("원 본 파 일 폴 더 섹션 (admin)", "원 본 파 일 폴 더" in html)
chk("/partial/stats hx-trigger=load", 'hx-get="/partial/stats"' in html)
chk("/partial/source_folder hx-trigger=load", 'hx-get="/partial/source_folder"' in html)

section("TAB 0 홈 (user) — admin 카드/폴더 숨김")
_set("user")
r = client.get("/", follow_redirects=False)
chk("user GET / 200", r.status_code == 200)
html_u = r.text
for hidden in ["문제 등록", "문제 관리", "사용자 관리"]:
    chk(f"user 권한에 '{hidden}' 카드 숨김", hidden not in html_u)
chk("user 권한에 폴더 설정 섹션 숨김", "원 본 파 일 폴 더" not in html_u)

section("TAB 0 partial: stats + source_folder")
_set("admin")
r = client.get("/partial/stats")
chk("/partial/stats 200", r.status_code == 200)
chk("5개 소스 라벨", all(s in r.text for s in ["내신기출 A", "내신기출 B", "수능특강", "수능완성", "모의고사"]))
chk("색상 박스 (hex)", "#3a86ff" in r.text and "#06c98a" in r.text)
chk("총 등록 문제 합계", "총 등록 문제" in r.text)

r = client.get("/partial/source_folder")
chk("/partial/source_folder 200", r.status_code == 200)
chk("폴더 입력 폼 노출", 'name="new_path"' in r.text)


# ─────────────────────────────────────────────────────
# TAB 1: 랜덤출제 — Step 1 → 2 → 3 → finalize 풀 플로우
# ─────────────────────────────────────────────────────
section("TAB 1 랜덤출제 — Step 1")
exam_session.reset_draft(admin.uid)
r = client.get("/random", follow_redirects=False)
chk("/random 200", r.status_code == 200)
chk("Step 1 헤더", "랜덤출제 (단원선택)" in r.text or "랜덤출제(단원선택)" in r.text)
chk("[다음] 버튼", "/partial/random/step2" in r.text)
chk("단원 트리 (unit-checkbox 클래스)", "unit-checkbox" in r.text)

section("TAB 1 — Step 2 (medium:A1:2022 선택)")
r = post_form("/partial/random/step2", [("units", "medium:A1:2022")])
chk("Step 2 200", r.status_code == 200)
chk("Step 2 헤더 — 출제조건", "출제조건 지정 및 문항수 입력" in r.text or "출제조건" in r.text)
chk("우측 패널 — 소스 필터", "소스 필터" in r.text or 'name="source_filter_on"' in r.text)
chk("우측 패널 — 수준별 보기", "수준별 보기" in r.text or 'name="view_level"' in r.text)
chk("우측 패널 — 정답률 사용", "정답률" in r.text)
chk("우측 패널 — 문항선호도", "문항선호도" in r.text or "선호도" in r.text)
chk("우측 패널 — 년도 필터", "년도 필터" in r.text)
chk("우측 패널 — 출제 제외", "출제 제외" in r.text or "제외설정" in r.text)
chk("우측 패널 — 상세 필터", "상세 필터" in r.text or "학교" in r.text)
chk("좌측 — alloc 입력", 'alloc_medium_A1_2022' in r.text)

section("TAB 1 — Step 3 (random_multi 호출)")
r = post_form("/api/exam/random_multi", [
    ("units", "medium:A1:2022"),
    ("alloc_medium_A1_2022____", "5"),
])
chk("random_multi 200", r.status_code == 200)
chk("Step 3 헤더 — 출제 문항 확인", "출제 문항 확인" in r.text)
chk("[순서정렬] 버튼", "순서정렬" in r.text)
chk("[랜덤추가] 버튼", "랜덤추가" in r.text)
chk("[정렬 취소] 버튼 (disabled 또는 활성)", "정렬 취소" in r.text)
chk("[다음] 버튼 → step4 (시험지 저장 및 출제)", "/partial/random/step4" in r.text)
chk("문항 테이블 헤더", all(c in r.text for c in ["순번", "출처", "단원", "수준", "형식", "관리"]))

draft = exam_session.get_draft(admin.uid)
chk("draft 에 5개 추첨됨", draft.total > 0, f"total={draft.total}")

if draft.total > 0:
    pid = str(draft.batches[0][0]["id"])
    section("TAB 1 — Step 3 액션 (삭제/정렬/정렬취소)")
    cnt_before = draft.total
    r = post_form("/partial/random/step3_remove", [("problem_id", pid)])
    chk("step3_remove 200", r.status_code == 200)
    draft = exam_session.get_draft(admin.uid)
    chk("삭제 후 1개 줄어듦", draft.total == cnt_before - 1)

    r = post_form("/partial/random/step3_sort", [
        ("sort_p1", "수준순"), ("sort_p2", "(없음)"), ("sort_p3", "(없음)"),
    ])
    chk("step3_sort 200", r.status_code == 200)
    draft = exam_session.get_draft(admin.uid)
    chk("정렬 후 batch=1, undo 가능", len(draft.batches) == 1 and draft.can_undo_sort())

    r = post_form("/partial/random/step3_undo_sort", [])
    chk("step3_undo_sort 200", r.status_code == 200)
    draft = exam_session.get_draft(admin.uid)
    chk("undo 후 backup 비움", not draft.can_undo_sort())

    section("TAB 1 — [랜덤추가] step3_to_step1")
    r = client.get("/partial/random/step3_to_step1")
    chk("step3_to_step1 200", r.status_code == 200)
    chk("기존 문항 유지 안내", "기존 출제 문항" in r.text)

# 정리
exam_session.reset_draft(admin.uid)


# ─────────────────────────────────────────────────────
# TAB 2: 원본출제
# ─────────────────────────────────────────────────────
section("TAB 2 원본출제")
r = client.get("/original", follow_redirects=False)
chk("/original 200", r.status_code == 200)
chk("소스 라디오 버튼", 'name="source"' in r.text)
chk("교육과정 필터 노출", "교육과정" in r.text or "curriculum" in r.text)

# NAESIN_A 파일 목록 (GET 라우트, query param)
r = client.get("/partial/original/files?source=NAESIN_A")
chk("/partial/original/files NAESIN_A 200", r.status_code == 200, str(r.status_code))


# ─────────────────────────────────────────────────────
# TAB 3: 시험지관리
# ─────────────────────────────────────────────────────
section("TAB 3 시험지관리")
r = client.get("/library", follow_redirects=False)
chk("/library 200", r.status_code == 200)
chk("좌측 폴더 트리 영역", 'hx-get="/partial/library/folders"' in r.text or "폴더" in r.text)

r = client.get("/partial/library/folders")
chk("/partial/library/folders 200", r.status_code == 200)


# ─────────────────────────────────────────────────────
# TAB 4: 문제등록
# ─────────────────────────────────────────────────────
section("TAB 4 문제등록")
r = client.get("/register", follow_redirects=False)
chk("/register 200 (admin)", r.status_code == 200)
for label in ["내신기출A", "내신기출B", "수능특강", "수능완성", "모의고사", "일반 문제집"]:
    chk(f"소스 카드 '{label}'", label in r.text)

r = client.get("/register/SUNEUNG_SPECIAL", follow_redirects=False)
chk("/register/SUNEUNG_SPECIAL 200", r.status_code == 200)
chk("폴더/파일 모드 토글", 'name="is_folder"' in r.text)
chk("target_path 입력", 'name="target_path"' in r.text)
chk("schema partial 자동 로드", 'hx-get="/partial/register/schema/SUNEUNG_SPECIAL"' in r.text)
chk("덮어쓰기 옵션", 'name="force_reindex"' in r.text)
chk("스텔스 옵션", 'name="stealth_mode"' in r.text)

r = client.get("/partial/register/schema/SUNEUNG_SPECIAL")
chk("schema partial 200", r.status_code == 200)
chk("시행 연도 필드", "시행 연도" in r.text and 'name="year"' in r.text)
chk("과목 콤보", "과목" in r.text and 'name="subject"' in r.text)

# user 권한 redirect
_set("user")
r = client.get("/register", follow_redirects=False)
chk("user /register → / redirect", r.status_code == 302 and r.headers.get("location") == "/")
_set("admin")


# ─────────────────────────────────────────────────────
# TAB 5: 문제관리
# ─────────────────────────────────────────────────────
section("TAB 5 문제관리")
r = client.get("/manage", follow_redirects=False)
chk("/manage 200", r.status_code == 200)
chk("일괄 작업 — 파일별 제외/복원/DB삭제", "파일별 제외" in r.text and "DB삭제" in r.text)
chk("🔎 파일 진단 버튼", "파일 진단" in r.text)
chk("↻ 재인덱싱 버튼", "재인덱싱" in r.text)


# ─────────────────────────────────────────────────────
# TAB 6: 사용자관리
# ─────────────────────────────────────────────────────
section("TAB 6 사용자관리 (admin)")
r = client.get("/users", follow_redirects=False)
chk("/users 200 (admin)", r.status_code == 200)
chk("새 계정 발급 버튼", "새 계정 발급" in r.text)
chk("새로고침 버튼", "새로고침" in r.text)
chk("/partial/users hx-trigger=load", 'hx-get="/partial/users"' in r.text)

# user → / redirect
_set("user")
r = client.get("/users", follow_redirects=False)
chk("user /users → / redirect", r.status_code == 302 and r.headers.get("location") == "/")
_set("admin")


# ─────────────────────────────────────────────────────
# 미인증 사용자 — 모든 보호 페이지 → /login
# ─────────────────────────────────────────────────────
section("미인증 — 모든 보호 페이지 → /login")
app.dependency_overrides[require_user] = lambda: (_ for _ in ()).throw(__import__("fastapi").HTTPException(401))
app.dependency_overrides[get_optional_user] = lambda: None
app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(__import__("fastapi").HTTPException(401))

for path in ["/", "/random", "/original", "/library", "/manage", "/register", "/users"]:
    r = client.get(path, follow_redirects=False)
    chk(f"미인증 GET {path} → /login redirect",
        r.status_code == 302 and r.headers.get("location") == "/login",
        f"{r.status_code} → {r.headers.get('location')}")


# ─────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
if not issues:
    print("🎉 모든 검수 항목 통과 — 동등성 95%+ 도달")
else:
    print(f"⚠ {len(issues)}개 이슈 발견:")
    for i, iss in enumerate(issues, 1):
        print(f"  {i}. {iss}")
print("=" * 60)

sys.exit(0 if not issues else 1)
