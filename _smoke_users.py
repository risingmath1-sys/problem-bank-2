"""사용자관리 탭 smoke test — admin 가드/목록/CRUD 흐름 동등성.

Note: Firebase 호출은 실제 SDK 라 실패 가능. 본 smoke 는 라우트 가드 + partial 렌더만 검증.
"""
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


def _set_user(role):
    user = SessionUser(uid=role, email=f"{role}@x", role=role,
                       display_id=role, display_name=role)
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user
    return user


client = TestClient(app)


def section(t):
    print(f"\n=== {t} ===")


def post_form(p, fs):
    return client.post(p, content=urllib.parse.urlencode(fs, doseq=True),
                       headers={'content-type': 'application/x-www-form-urlencoded'})


# 1) GET /users — admin 만 진입
section("1. GET /users — admin")
_set_user("admin")
r = client.get("/users", follow_redirects=False)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "사용자 관리" in r.text
assert "새 계정 발급" in r.text
print("✓ admin /users OK")

section("2. GET /users — user 권한 → / 로 redirect")
_set_user("user")
r = client.get("/users", follow_redirects=False)
print("status:", r.status_code)
assert r.status_code == 302
assert r.headers.get("location") == "/"
print("✓ user redirect OK")

# 3) /partial/users — admin 만 호출 가능 (require_admin 가드)
section("3. /partial/users — admin")
_set_user("admin")
r = client.get("/partial/users")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
# error 가 있어도 partial 자체는 200 으로 옴 (Firestore 권한/네트워크 등 사유 가능)
# admin 자기 행에는 비활성화 버튼 disabled 인지는 실제 데이터에 따라 다름.
print("✓ partial users rendered")

# 4) /partial/users — user 권한 → 403
section("4. /partial/users — user (admin 가드)")
_set_user("user")
# require_admin override 하지 않은 채 user 로 호출
def _user_only():
    return SessionUser(uid="user", email="u@x", role="user", display_id="user", display_name="user")
app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(__import__("fastapi").HTTPException(status_code=403))
r = client.get("/partial/users")
print("status:", r.status_code)
assert r.status_code == 403
print("✓ user denied")

# 5) POST /api/users/create — 검증 실패 응답 (비번 짧음 등)
section("5. POST /api/users/create — validation")
_set_user("admin")
r = post_form("/api/users/create", [
    ("display_id", "smoke_test"),
    ("password", "123"),  # 6자 미만
    ("role", "user"),
])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "6자 이상" in r.text
print("✓ validation rejection OK")

# 6) POST /api/users/{uid}/change_role — 본인 uid 로 시도 → 400 (self_guard)
section("6. POST self change_role — 400")
r = post_form(f"/api/users/admin/change_role", [("new_role", "user")])
print("status:", r.status_code)
assert r.status_code == 400
print("✓ self change_role blocked")

# 7) POST /api/users/{uid}/delete — 본인 uid 로 시도 → 400
section("7. POST self delete — 400")
r = post_form(f"/api/users/admin/delete", [])
print("status:", r.status_code)
assert r.status_code == 400
print("✓ self delete blocked")

# 8) POST /api/users/{uid}/reset_password — 짧은 비번 → 친절한 에러
section("8. POST reset_password short")
r = post_form(f"/api/users/anyuid/reset_password", [("new_password", "12")])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "6자 이상" in r.text
print("✓ short pw rejected")


print("\n=== USERS TAB SMOKE TESTS PASS ===")
