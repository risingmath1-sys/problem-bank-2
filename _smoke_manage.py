"""Tab 5 (Manage) smoke test — exclusion + preference + unit_code + difficulty."""
import io
import sys
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user, require_admin
from server.services.engine import get_engine

fake_user = SessionUser(
    uid="admin", email="risingmath1@gmail.com", role="admin",
    display_id="admin", display_name="admin",
)
app.dependency_overrides[require_user] = lambda: fake_user
app.dependency_overrides[require_admin] = lambda: fake_user
app.dependency_overrides[get_optional_user] = lambda: fake_user
client = TestClient(app)


def post_form(path, fields):
    body = urllib.parse.urlencode(fields, doseq=True)
    return client.post(
        path, content=body,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


# 1) 페이지 로드
print("\n=== 1. GET /manage ===")
r = client.get("/manage")
assert r.status_code == 200, r.status_code
print("✓ manage page renders")

# 2) 파일 목록
print("\n=== 2. GET /partial/manage/files (SUNEUNG_SPECIAL) ===")
r = client.get("/partial/manage/files", params={"source": "SUNEUNG_SPECIAL"})
assert r.status_code == 200
print(f"✓ files list ({len(r.text)} bytes)")

# 3) 문제 목록 — 단원 select 포함 검증
print("\n=== 3. GET /partial/manage/problems ===")
engine = get_engine()
exams = engine.search_exams_grouped({"source": "SUNEUNG_SPECIAL"})
assert exams
file_name = exams[0]["file_name"]
r = client.get("/partial/manage/problems", params={"file_name": file_name, "view_mode": "all"})
assert r.status_code == 200
assert 'name="value"' in r.text  # difficulty + unit_code selects
assert 'field" value="unit_code"' in r.text
print("✓ problems with unit edit form")

# 4) 문제 1건에 대해 exclusion 토글
problems = engine.get_problems_by_files([file_name])
assert problems
sample = problems[0]
pid = str(sample["id"])
prev_excluded = bool(sample.get("is_excluded"))
target_excluded = 0 if prev_excluded else 1
print(f"\n=== 4. POST /api/manage/exclusion (pid={pid}, target={target_excluded}) ===")
r = post_form("/api/manage/exclusion", [
    ("problem_id", pid),
    ("excluded", str(target_excluded)),
    ("file_name", file_name),
])
assert r.status_code == 200, r.text[:200]
re_pull = next(p for p in engine.get_problems_by_files([file_name]) if str(p["id"]) == pid)
assert bool(re_pull.get("is_excluded")) == bool(target_excluded), \
    f"expected is_excluded={bool(target_excluded)}, got {bool(re_pull.get('is_excluded'))}"
print("✓ exclusion toggled")

# 복원
post_form("/api/manage/exclusion", [
    ("problem_id", pid),
    ("excluded", str(int(prev_excluded))),
    ("file_name", file_name),
])

# 5) 선호도
print("\n=== 5. POST /api/manage/preference (Good) ===")
r = post_form("/api/manage/preference", [
    ("problem_id", pid),
    ("value", "Good"),
    ("file_name", file_name),
])
assert r.status_code == 200, r.text[:200]
pref_map = engine.get_preferences_bulk(fake_user.uid, [pid]) or {}
assert pref_map.get(pid) == "Good"
print("✓ preference set Good")
# 해제
post_form("/api/manage/preference", [
    ("problem_id", pid),
    ("value", ""),
    ("file_name", file_name),
])

# 6) 난이도 변경
prev_diff = sample.get("difficulty") or "C"
new_diff = "A" if prev_diff != "A" else "B"
print(f"\n=== 6. POST /api/manage/meta (difficulty: {prev_diff} → {new_diff}) ===")
r = post_form("/api/manage/meta", [
    ("problem_id", pid),
    ("field", "difficulty"),
    ("value", new_diff),
    ("file_name", file_name),
])
assert r.status_code == 200, r.text[:200]
re_pull = next(p for p in engine.get_problems_by_files([file_name]) if str(p["id"]) == pid)
assert re_pull.get("difficulty") == new_diff, f"expected {new_diff}, got {re_pull.get('difficulty')}"
print("✓ difficulty updated")
# 복구
post_form("/api/manage/meta", [
    ("problem_id", pid), ("field", "difficulty"),
    ("value", prev_diff), ("file_name", file_name),
])

# 7) 단원 변경 (unit_code + unit_name)
prev_uc = sample.get("unit_code") or ""
prev_mn = sample.get("middle_unit") or ""
new_uc = "Z9"  # 의도적으로 안 쓰는 코드 → 복구만 확인
new_name = "테스트단원"
print(f"\n=== 7. POST /api/manage/meta (unit_code: {prev_uc} → {new_uc}) ===")
r = post_form("/api/manage/meta", [
    ("problem_id", pid),
    ("field", "unit_code"),
    ("value", new_uc),
    ("unit_name", new_name),
    ("file_name", file_name),
])
assert r.status_code == 200, r.text[:200]
# get_problems_by_files SELECT 에 unit_code 가 없으므로 SQLite 캐시 직접 조회
import sqlite3
cache_path = engine.cache.cache_path if hasattr(engine, "cache") else (
    engine.cache_engine.db_path if hasattr(engine, "cache_engine") else "problem_bank.db"
)
with sqlite3.connect(cache_path) as conn:
    row = conn.execute(
        "SELECT unit_code, middle_unit FROM problems WHERE id=?", (pid,)
    ).fetchone()
assert row, "DB row missing"
assert row[0] == new_uc, f"unit_code: expected {new_uc}, got {row[0]}"
assert row[1] == new_name, f"middle_unit: expected {new_name}, got {row[1]}"
print("✓ unit_code + middle_unit updated")
# 복구
post_form("/api/manage/meta", [
    ("problem_id", pid), ("field", "unit_code"),
    ("value", prev_uc), ("unit_name", prev_mn),
    ("file_name", file_name),
])

# 8) 파일 진단
print("\n=== 8. POST /api/manage/files/diagnose ===")
r = post_form("/api/manage/files/diagnose", [("file_names", file_name)])
assert r.status_code == 200, r.text[:200]
assert "진단 대상" in r.text, "진단 헤더 누락"
assert file_name in r.text, "파일명 누락"
print("✓ file diagnose OK")

# 9) 재인덱싱 (안내 응답)
print("\n=== 9. POST /api/manage/files/reindex ===")
r = post_form("/api/manage/files/reindex", [("file_names", file_name)])
assert r.status_code == 200, r.text[:200]
assert "재인덱싱" in r.text
print("✓ reindex notice OK")

# 10) 빈 파일명 진단 → 친절한 안내
print("\n=== 10. POST diagnose with empty list ===")
r = post_form("/api/manage/files/diagnose", [])
assert r.status_code == 200
assert "선택된 파일이 없습니다" in r.text
print("✓ empty diagnose handled")

print("\n=== MANAGE TAB SMOKE TESTS PASS ===")
