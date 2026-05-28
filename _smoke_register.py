"""문제 등록 탭 smoke test — 6개 소스 카드 + 라우트 가드."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user, require_admin


def _set(role):
    u = SessionUser(uid=role, email=f"{role}@x", role=role,
                    display_id=role, display_name=role)
    app.dependency_overrides[require_user] = lambda: u
    app.dependency_overrides[get_optional_user] = lambda: u
    app.dependency_overrides[require_admin] = lambda: u
    return u


client = TestClient(app)


def section(t):
    print(f"\n=== {t} ===")


# 1) /register — admin 진입
section("1. GET /register — admin")
_set("admin")
r = client.get("/register", follow_redirects=False)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
for label in ["내신기출A", "내신기출B", "수능특강", "수능완성", "모의고사", "일반 문제집"]:
    assert label in r.text, f"카드 누락: {label}"
print("✓ 6개 소스 카드 OK")

# 2) user 권한 → / 로 redirect
section("2. GET /register — user → redirect /")
_set("user")
r = client.get("/register", follow_redirects=False)
assert r.status_code == 302 and r.headers.get("location") == "/"
print("✓ user redirect OK")

# 3) 각 소스별 폼 페이지
section("3. GET /register/{source} — admin")
_set("admin")
for src in ["NAESIN_A", "NAESIN_N", "SUNEUNG_SPECIAL", "SUNEUNG_COMPLETE", "MOCK_EXAM", "TEXTBOOK"]:
    r = client.get(f"/register/{src}", follow_redirects=False)
    assert r.status_code == 200, f"{src}: {r.status_code}"
    assert src in r.text, f"{src} 코드 표시 누락"
print("✓ 6개 소스 폼 OK")

# 4) 잘못된 소스 → /register 로 redirect
section("4. GET /register/INVALID — redirect")
r = client.get("/register/INVALID", follow_redirects=False)
assert r.status_code == 302
assert r.headers.get("location") == "/register"
print("✓ invalid source redirect OK")

# 5) /partial/register/schema/{source} — fields 없는 소스 (NAESIN_A)
import urllib.parse
def post_form(p, fs):
    return client.post(p, content=urllib.parse.urlencode(fs, doseq=True),
                       headers={'content-type': 'application/x-www-form-urlencoded'})

section("5. GET /partial/register/schema/NAESIN_A — no fields")
r = client.get("/partial/register/schema/NAESIN_A")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "폼 입력 없음" in r.text or "자동 파싱" in r.text
print("✓ NAESIN_A schema (auto-parse) OK")

# 6) /partial/register/schema/SUNEUNG_SPECIAL — 시행연도 + 과목
section("6. GET /partial/register/schema/SUNEUNG_SPECIAL")
r = client.get("/partial/register/schema/SUNEUNG_SPECIAL")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "시행 연도" in r.text and "과목" in r.text
assert 'name="year"' in r.text and 'name="subject"' in r.text
print("✓ SUNEUNG_SPECIAL schema OK")

# 7) /partial/register/schema/TEXTBOOK — 미구현 인덱서 안내
section("7. GET /partial/register/schema/TEXTBOOK — not implemented")
r = client.get("/partial/register/schema/TEXTBOOK")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "미구현" in r.text
print("✓ TEXTBOOK 안내 OK")

# 8) POST /api/register/start — 잘못된 경로 → 친절한 에러
section("8. POST /api/register/start — invalid path")
r = post_form("/api/register/start", [
    ("source", "NAESIN_A"),
    ("target_path", "Z:/nonexistent/path"),
    ("is_folder", "1"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "찾을 수 없습니다" in r.text
print("✓ invalid path rejected")

# 9) POST /api/register/start — source 누락
section("9. POST /api/register/start — missing source")
r = post_form("/api/register/start", [
    ("source", "INVALID_SRC"),
    ("target_path", "."),
])
print("status:", r.status_code)
assert r.status_code == 200
assert "잘못된 소스" in r.text
print("✓ invalid source rejected")

# 10) /partial/register/subjects?curriculum=...
section("10. GET /partial/register/subjects?curriculum=2022개정교육과정")
r = client.get("/partial/register/subjects?curriculum=2022%EA%B0%9C%EC%A0%95%EA%B5%90%EC%9C%A1%EA%B3%BC%EC%A0%95")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
# 옵션이 비어있을 수도 있지만 200 + <option> 태그는 있어야 함
assert "<option" in r.text
print("✓ subjects partial OK")


print("\n=== REGISTER TAB SMOKE TESTS PASS ===")
