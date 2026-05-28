"""Random Step 3 (출제 문항 확인) smoke test — 큐 등록 X, draft 저장/조작 검증."""
import io
import sys
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user
from server.services import exam_session

fake_user = SessionUser(
    uid="admin",
    email="risingmath1@gmail.com",
    role="admin",
    display_id="admin",
    display_name="admin",
)
app.dependency_overrides[require_user] = lambda: fake_user
app.dependency_overrides[get_optional_user] = lambda: fake_user
client = TestClient(app)


def post_form(path, fields):
    body = urllib.parse.urlencode(fields, doseq=True)
    return client.post(
        path,
        content=body,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


def section(t):
    print(f"\n=== {t} ===")


# Clean up any stale draft from previous runs.
exam_session.reset_draft("admin")


# 1) Step 1 → Step 2 → multi → step3_preview (NOT exam_progress.html anymore)
section("1. random_multi → step3_preview (NOT queue)")
fields = [
    ("units", "medium:A1:2022"),
    # alloc_<utype>_<code>_<version>_<lvl>_<type> 키로 수량 지정 (lvl/type 미지정→"_")
    ("alloc_medium_A1_2022____", "5"),
]
r = post_form("/api/exam/random_multi", fields)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
# 큐 등록되면 random_step3.html 의 "출제 진행 중" 마커 — 우리 변경 후엔 step3_preview 마커이어야 함.
if "출제 문항 확인" in r.text:
    print("✓ step3_preview rendered (no queue submit)")
elif "출제 진행 중" in r.text:
    raise AssertionError("OLD path: queue submitted directly. step3 preview missing.")
elif "조건에 맞는 문항을 찾을 수 없습니다" in r.text or "추첨된" in r.text or "원본 HWP" in r.text:
    print("⚠ no problems matched filter — adjust unit code if needed.")
elif "수량을 1개 이상" in r.text:
    raise AssertionError("alloc key parsing fail — total_qty=0")
else:
    print("first 400:", r.text[:400])
    raise AssertionError("unexpected response")

# Verify draft is populated
draft = exam_session.get_draft("admin")
print(f"draft.total = {draft.total}, batches = {len(draft.batches)}")
assert draft.total > 0, "draft 가 비어 있음 — random_multi 가 세션에 저장 못함"


# 2) step3_remove — 1개 줄어드는지
section("2. step3_remove")
first_pid = str(draft.batches[0][0]["id"])
print(f"removing pid={first_pid}")
total_before = draft.total
r = post_form("/partial/random/step3_remove", [("problem_id", first_pid)])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
draft = exam_session.get_draft("admin")
assert draft.total == total_before - 1, f"remove 실패: {total_before} → {draft.total}"
print(f"✓ removed: {total_before} → {draft.total}")


# 3) step3_sort — 적용 후 batches 길이 1, can_undo_sort = True
section("3. step3_sort (수준순)")
total_before = draft.total
r = post_form("/partial/random/step3_sort", [
    ("sort_p1", "수준순"),
    ("sort_p2", "(없음)"),
    ("sort_p3", "(없음)"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
draft = exam_session.get_draft("admin")
assert draft.total == total_before, f"sort 가 개수 바꿈: {total_before} → {draft.total}"
assert len(draft.batches) == 1, f"sort 후 batches 통합 실패: {len(draft.batches)}"
assert draft.can_undo_sort(), "정렬 직후 undo 가능해야 함"
print(f"✓ sorted: batches={len(draft.batches)}, undo_available={draft.can_undo_sort()}")


# 4) step3_undo_sort — 백업 복원
section("4. step3_undo_sort")
r = post_form("/partial/random/step3_undo_sort", [])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
draft = exam_session.get_draft("admin")
assert not draft.can_undo_sort(), "undo 직후엔 backup 비어있어야 함"
print(f"✓ undo OK, undo_available now = {draft.can_undo_sort()}")


# 5) step3_to_step1 — random_exam.html 반환, append_existing_count 표시
section("5. step3_to_step1 (랜덤추가)")
r = client.get("/partial/random/step3_to_step1")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "기존 출제 문항" in r.text, "append_existing_count 안내 누락"
assert f"<b>{draft.total}개</b>" in r.text, "기존 문항 수 표시 누락"
print(f"✓ step1 with notice (count={draft.total})")


# 6) random_finalize — 큐 등록 + draft 비워짐 + step3.html (진행 화면) 반환
section("6. random_finalize")
total_before = draft.total
r = post_form("/api/exam/random_finalize", [
    ("exam_title", "smoke-test-step3"),
    ("exclude_tags", "1"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "출제 진행 중" in r.text, "진행 화면(step3.html) 마커 누락"
draft = exam_session.get_draft("admin")
assert draft.total == 0, f"finalize 후 draft 가 비어야 함: {draft.total}"
print(f"✓ queue submitted + draft reset (had {total_before} problems)")


# 7) step3_pop_last — 빈 draft 에서 pop → step1 redirect
section("7. step3_pop_last with empty draft")
r = post_form("/partial/random/step3_pop_last", [])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
# 빈 draft 에서 pop_last → /random 으로 hx-trigger=load redirect
assert 'hx-get="/random"' in r.text or "랜덤출제" in r.text
print("✓ pop_last on empty → step1 redirect")


print("\n=== STEP3 SMOKE TESTS PASS ===")
