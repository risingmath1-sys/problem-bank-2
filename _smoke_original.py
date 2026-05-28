"""Tab 2 (Original) smoke test — filters + partial selection + save_original."""
import io
import sys
import urllib.parse
import uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user
from server.services.engine import get_engine

fake_user = SessionUser(
    uid="admin", email="risingmath1@gmail.com", role="admin",
    display_id="admin", display_name="admin",
)
app.dependency_overrides[require_user] = lambda: fake_user
app.dependency_overrides[get_optional_user] = lambda: fake_user
client = TestClient(app)


def get(path, params):
    return client.get(path, params=params)


# 1) 페이지 로드 — 교육과정 dropdown 데이터 포함
print("\n=== 1. GET /original ===")
r = client.get("/original")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert 'name="curriculum"' in r.text
assert 'name="diff_level"' in r.text
assert 'name="unit_like"' in r.text
print("✓ original page renders")

# 2) NAESIN_A 파일 목록 (난이도 뱃지 계산)
print("\n=== 2. GET /partial/original/files (NAESIN_A) ===")
r = get("/partial/original/files", {"source": "NAESIN_A"})
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ NAESIN_A list rendered")

# 3) NAESIN_A + 난이도 필터
print("\n=== 3. NAESIN_A + diff_level=상 ===")
r = get("/partial/original/files", {"source": "NAESIN_A", "diff_level": "상"})
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ diff filter accepted")

# 4) 비-내신 (수능특강)
print("\n=== 4. SUNEUNG_SPECIAL ===")
r = get("/partial/original/files", {"source": "SUNEUNG_SPECIAL"})
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ SUNEUNG_SPECIAL list rendered")

# 5) 파일 선택 → 문제 목록 (DB에서 첫 파일 추출)
print("\n=== 5. GET /partial/original/problems ===")
engine = get_engine()
exams = engine.search_exams_grouped({"source": "SUNEUNG_SPECIAL"})
assert exams, "no exam files in DB"
file_name = exams[0]["file_name"]
print(f"using file: {file_name}")
r = get("/partial/original/problems", {"file_name": file_name})
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert 'orig-prob-cb' in r.text
assert 'orig-save-form' in r.text
print("✓ problems with checkboxes + save form")

# 6) save_original — 부분 선택
print("\n=== 6. POST /api/library/save_original ===")
problems = engine.get_problems_by_files([file_name])
assert problems
selected_ids = [str(p["id"]) for p in problems[:3]]
suffix = uuid.uuid4().hex[:6]
fields = [
    ("file_name", file_name),
    ("title", f"orig-save-{suffix}"),
    ("unit_summary", "원본저장 테스트"),
]
for pid in selected_ids:
    fields.append(("problem_ids", pid))
body = urllib.parse.urlencode(fields, doseq=True)
r = client.post(
    "/api/library/save_original",
    content=body,
    headers={"content-type": "application/x-www-form-urlencoded"},
)
print("status:", r.status_code, "snippet:", r.text[:200])
assert r.status_code == 200
assert "id=" in r.text
import re
m = re.search(r"id=(\d+)", r.text)
assert m
new_tid = int(m.group(1))
detail = engine.get_test_detail(new_tid, fake_user.uid)
assert detail, "saved test not retrievable"
assert len(detail.get("problems") or []) == 3, f"expected 3 problems, got {len(detail.get('problems') or [])}"
engine.delete_test(new_tid)
print("✓ save_original — 3 selected problems saved & cleaned up")

print("\n=== ORIGINAL TAB SMOKE TESTS PASS ===")
