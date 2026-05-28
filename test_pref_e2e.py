"""선호도 버튼 E2E 테스트 (인증 우회)."""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user

# admin user 로 우회 — 다만 test 는 그 user 의 것이어야 함
import firebase_admin
from firebase_admin import firestore
db = firestore.client()
test_doc = next(iter(db.collection("saved_tests").limit(1).stream()))
test = test_doc.to_dict()
real_uid = test.get("user_id")
test_id = int(test_doc.id)

print(f"테스트 시험지 ID={test_id}, owner uid={real_uid}")

fake_user = SessionUser(
    uid=real_uid, email="test@test", role="admin",
    display_id="test", display_name="test",
)
app.dependency_overrides[require_user] = lambda: fake_user
app.dependency_overrides[get_optional_user] = lambda: fake_user

client = TestClient(app)

# 1. preview 페이지 GET — 새 safe_id 가 렌더되는지 확인
r = client.get(f"/partial/library/test/{test_id}/preview")
print(f"\n[GET preview] status={r.status_code}, length={len(r.text)}")

if r.status_code == 200:
    html = r.text
    # hx-target / id 패턴 추출
    ids = re.findall(r'id="(pref-cell[^"]*)"', html)
    targets = re.findall(r'hx-target="(#pref-cell[^"]*)"', html)
    posts = re.findall(r'hx-post="(/api/library/problem/[^"]*)"', html)
    safe_ids = re.findall(r'"_safe_id":\s*"([^"]+)"', html)
    
    print(f"\nid 패턴 (상위 3): {ids[:3]}")
    print(f"hx-target 패턴 (상위 3): {targets[:3]}")
    print(f"hx-post 패턴 (상위 3): {posts[:3]}")
    print(f"_safe_id 값 (상위 3): {safe_ids[:3]}")

# 2. POST preference - 한 문제의 ID 로
pids = test.get('problem_ids') or []
if pids:
    test_pid = pids[0]
    r = client.post(f"/api/library/problem/{test_pid}/preference",
                    data={"preference": "Good", "safe_id": "pref-cell-1"})
    print(f"\n[POST preference] status={r.status_code}")
    print(f"응답 길이: {len(r.text)}")
    if r.status_code == 200:
        print(f"응답 (앞 200자): {r.text[:300]}")

