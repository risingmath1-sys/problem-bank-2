"""R-8 smoke test — rate filter + exclude_tags + auto-unit + skipped detail."""
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


# 1) rate filter UI rendered in initial Step 2
print("\n=== 1. initial Step2 has rate filter widget ===")
r = post_form("/partial/random/step2", [("units", "large:A:2022")])
assert r.status_code == 200
assert 'name="rate_use"' in r.text and 'name="rate_min"' in r.text
print("✓ rate widgets present")

# 2) rate filter applied
print("\n=== 2. rate filter (50% ~ 100%) ===")
r = post_form("/partial/random/step2_table", [
    ("filter_panel", "1"),
    ("rate_use", "1"),
    ("rate_min", "50"),
    ("rate_max", "100"),
    ("units", "medium:A1:2022"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ rate filter accepted")

# 3) random_multi with rate + exclude_tags + auto-unit
print("\n=== 3. random_multi w/ rate + exclude_tags ===")
r = post_form("/api/exam/random_multi", [
    ("filter_panel", "1"),
    ("rate_use", "1"),
    ("rate_min", "0"),
    ("rate_max", "100"),
    ("exclude_tags", "1"),
    ("exam_title", "rate-test"),
    ("units", "medium:A1:2022"),
    ("alloc_medium_A1_2022____", "2"),
])
print("status:", r.status_code, "len:", len(r.text))
print("first 300:", r.text[:300])
assert r.status_code == 200

print("\n=== R-8 SMOKE TESTS PASS ===")
