"""R-6/R-7 smoke test — 배분 + 상세필터(school/brand/pnum) 라우트 동작 확인."""
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

fake_user = SessionUser(
    uid="admin", email="risingmath1@gmail.com", role="admin",
    display_id="admin", display_name="admin",
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


# 1) school search endpoint
print("\n=== 1. /partial/random/school_search?q=대 ===")
r = client.get("/partial/random/school_search", params={"q": "대"})
print("status:", r.status_code, "len:", len(r.text))
print("first 200:", r.text[:200])
assert r.status_code == 200

# 2) school search empty
print("\n=== 2. school_search empty ===")
r = client.get("/partial/random/school_search", params={"q": ""})
print("status:", r.status_code, "body:", r.text[:100])
assert r.status_code == 200
assert "검색어를" in r.text

# 3) Step1→2 default → detail filter UI 부분 확인
print("\n=== 3. Step1→2 (initial) — detail filter section present ===")
r = post_form("/partial/random/step2", [("units", "large:A:2022")])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "상세 필터" in r.text
assert "균등" in r.text and "비율" in r.text  # 배분 버튼
print("✓ detail filter section + alloc buttons present")

# 4) school_option_on=1 + schools=대원외고
print("\n=== 4. table re-render w/ school option ===")
r = post_form("/partial/random/step2_table", [
    ("filter_panel", "1"),
    ("school_option_on", "1"),
    ("schools", "대원외국어고등학교"),
    ("units", "medium:A1:2022"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ school filter applied")

# 5) brand_option_on=1 + brands=비상
print("\n=== 5. brand filter ===")
r = post_form("/partial/random/step2_table", [
    ("filter_panel", "1"),
    ("brand_option_on", "1"),
    ("brands", "비상"),
    ("units", "medium:A1:2022"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ brand filter applied (no crash)")

# 6) pnum filter
print("\n=== 6. pnum filter ===")
r = post_form("/partial/random/step2_table", [
    ("filter_panel", "1"),
    ("pnum_option_on", "1"),
    ("pnum_text", "30, 45, 46"),
    ("units", "medium:A1:2022"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ pnum filter applied")

# 7) random_multi w/ pnum filter
print("\n=== 7. random_multi w/ pnum filter ===")
r = post_form("/api/exam/random_multi", [
    ("filter_panel", "1"),
    ("pnum_option_on", "1"),
    ("pnum_text", "1, 2, 3, 4, 5"),
    ("units", "medium:A1:2022"),
    ("alloc_medium_A1_2022____", "2"),
])
print("status:", r.status_code, "len:", len(r.text))
print("first 300:", r.text[:300])
assert r.status_code == 200

print("\n=== ALL R-6/R-7 SMOKE TESTS PASS ===")
