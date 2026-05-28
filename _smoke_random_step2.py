"""R-3/R-4/R-5 smoke test — preference, year, exclusion filters via TestClient."""
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


def has(text, marker):
    return marker in text


def section(title):
    print(f"\n=== {title} ===")


# 1) Step 1 → 2 transition (no filter_panel marker → defaults)
section("1. Step1→2 (initial)")
r = post_form(
    "/partial/random/step2",
    [("units", "large:A:2022"), ("units", "large:B:2022")],
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
# Check default state in rendered HTML — source filter ON
assert 'name="source_filter_on" value="1"' in r.text
assert 'checked' in r.text
print("✓ defaults rendered (source filter ON, etc.)")

# 2) Table-only re-render with view_level + view_type ON, A only, 객관식 only
section("2. table re-render: view_level=A, view_type=객관식")
r = post_form(
    "/partial/random/step2_table",
    [
        ("filter_panel", "1"),
        ("source_filter_on", "1"),
        *[("sources", s) for s in ["NAESIN_A", "NAESIN_N", "SUNEUNG_SPECIAL", "SUNEUNG_COMPLETE", "MOCK_EXAM"]],
        ("view_level", "1"),
        ("difficulties", "A"),
        ("view_type", "1"),
        ("types", "0"),
        ("units", "large:A:2022"),
    ],
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ table re-render OK")

# 3) Year filter — exclude 2024
section("3. year filter exclude 2024")
r = post_form(
    "/partial/random/step2_table",
    [
        ("filter_panel", "1"),
        ("year_filter_on", "1"),
        ("year_mode", "exclude"),
        ("years", "2024"),
        ("units", "medium:A1:2022"),
    ],
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ year filter (exclude) OK")

# 4) Year filter — include only 2024
section("4. year filter include 2024")
r = post_form(
    "/partial/random/step2_table",
    [
        ("filter_panel", "1"),
        ("year_filter_on", "1"),
        ("year_mode", "include"),
        ("years", "2024"),
        ("units", "medium:A1:2022"),
    ],
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ year filter (include) OK")

# 5) Preference filter — Good only, mine
section("5. preference filter (Good, mine)")
r = post_form(
    "/partial/random/step2_table",
    [
        ("filter_panel", "1"),
        ("pref_filter_on", "1"),
        ("prefs", "Good"),
        ("pref_scope", "mine"),
        ("units", "medium:A1:2022"),
    ],
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ pref filter (mine) OK")

# 6) Preference filter — Soso, all
section("6. preference filter (Soso, all)")
r = post_form(
    "/partial/random/step2_table",
    [
        ("filter_panel", "1"),
        ("pref_filter_on", "1"),
        ("prefs", "Soso"),
        ("pref_scope", "all"),
        ("units", "medium:A1:2022"),
    ],
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ pref filter (all) OK")

# 7) include_excluded toggle
section("7. include_excluded ON")
r = post_form(
    "/partial/random/step2_table",
    [
        ("filter_panel", "1"),
        ("include_excluded", "1"),
        ("units", "medium:A1:2022"),
    ],
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
print("✓ include_excluded OK")

# 8) /api/exam/random_multi with new filters (include + exclusion)
section("8. random_multi w/ year include + include_excluded")
r = post_form(
    "/api/exam/random_multi",
    [
        ("filter_panel", "1"),
        ("year_filter_on", "1"),
        ("year_mode", "include"),
        ("years", "2024"),
        ("include_excluded", "1"),
        ("units", "medium:A1:2022"),
        ("alloc_medium_A1_2022___", "2"),
        ("exam_title", "smoke test"),
    ],
)
print("status:", r.status_code, "len:", len(r.text))
print("first 500:", r.text[:500])
assert r.status_code == 200
print("✓ random_multi with R-3/4/5 filters OK")

print("\n=== ALL R-3/R-4/R-5 SMOKE TESTS PASS ===")
