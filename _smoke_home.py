"""홈 탭 smoke test — 로고/타이틀/메뉴카드 5종/통계/폴더설정 동등성."""
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


def _set_user(role):
    user = SessionUser(uid=role, email=f"{role}@x", role=role,
                       display_id=role, display_name=role)
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    return user


client = TestClient(app)


def section(t):
    print(f"\n=== {t} ===")


# admin 로 로그인
admin = _set_user("admin")

# 1) GET / 홈 페이지 — 로고/타이틀/5개 카드/admin 카드 표시
section("1. GET / (admin) — 5 cards visible")
r = client.get("/")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "/static/logo.png" in r.text, "로고 누락"
assert "상승 Solution" in r.text, "타이틀 누락"
assert "Problem Bank Management System" in r.text, "부제 누락"
# 5개 메뉴 카드
for label in ["랜덤 출제", "원본 출제", "시험지 관리", "문제 등록", "문제 관리"]:
    assert label in r.text, f"카드 누락: {label}"
print("✓ 로고 + 타이틀 + 부제 + 5개 카드 OK")


# 2) GET / 사용자 권한 — admin 전용 카드 숨김
section("2. GET / (user) — admin cards hidden")
_set_user("user")
r = client.get("/")
assert r.status_code == 200
assert "랜덤 출제" in r.text and "원본 출제" in r.text and "시험지 관리" in r.text
# admin 전용 카드는 숨김
assert "문제 등록" not in r.text, "user 권한에 문제등록 카드 노출됨"
assert "문제 관리" not in r.text, "user 권한에 문제관리 카드 노출됨"
print("✓ user 권한 — admin 카드 숨김 OK")


# 3) /partial/stats — 5개 색상 박스 + 합계
section("3. /partial/stats — 5 colored stat boxes")
_set_user("admin")
r = client.get("/partial/stats")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
for label in ["내신기출 A", "내신기출 B", "수능특강", "수능완성", "모의고사"]:
    assert label in r.text, f"통계 라벨 누락: {label}"
assert "총 등록 문제" in r.text
# 5개 색상 코드 - 일부만 확인
assert "#f4700c" in r.text and "#3a86ff" in r.text
print("✓ 5개 통계 박스 + 색상 OK")


# 4) /partial/source_folder — admin 만 폼 표시
section("4. /partial/source_folder — admin form")
_set_user("admin")
r = client.get("/partial/source_folder")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert 'name="new_path"' in r.text, "변경 입력 누락"
print("✓ admin 폴더 폼 OK")


# 5) user 는 폴더 partial 호출 시 거부 (관리자 전용 메시지)
section("5. /partial/source_folder — user denied")
_set_user("user")
r = client.get("/partial/source_folder")
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert "관리자 전용" in r.text
print("✓ user 거부 OK")


# 6) admin 가 폴더 변경 → settings.json 갱신 + partial 재렌더
# settings.json 백업/복원 — 다른 smoke 에 영향 주지 않도록.
section("6. POST /api/source_folder (admin)")
_set_user("admin")
import os, json, pathlib
os.environ.pop("NAEGIWANGBANK_HWP_SOURCE_DIR", None)
settings_path = pathlib.Path("settings.json").resolve()
original_settings = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
try:
    test_path = str((pathlib.Path.cwd() / "exercise").resolve())
    r = client.post(
        "/api/source_folder",
        content=urllib.parse.urlencode({"new_path": test_path}),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    print("status:", r.status_code, "len:", len(r.text))
    assert r.status_code == 200
    assert 'name="new_path"' in r.text, "응답이 partial 재렌더 아님"
    print("✓ admin 폴더 변경 OK")
finally:
    # 원본 settings.json 복원 — 다른 smoke (random_step3 등) 가 의존.
    if original_settings is not None:
        settings_path.write_text(original_settings, encoding="utf-8")
        # config 의 in-memory HWP_SOURCE_ROOT 도 다시 로드
        from server import config as _cfg
        _cfg.HWP_SOURCE_ROOT = _cfg._resolve_source_root()


# 7) user 는 폴더 변경 시도 → 403
section("7. POST /api/source_folder (user) — 403")
_set_user("user")
r = client.post(
    "/api/source_folder",
    content=urllib.parse.urlencode({"new_path": "C:/somewhere"}),
    headers={"content-type": "application/x-www-form-urlencoded"},
)
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 403
print("✓ user 변경 시도 거부 OK")


print("\n=== HOME TAB SMOKE TESTS PASS ===")
