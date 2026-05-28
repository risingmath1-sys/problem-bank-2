"""/full 라우트 응답에 새 safe_id 패턴 적용됐는지 확인."""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.firebase_init import init_admin_sdk
init_admin_sdk()
from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user

import firebase_admin
from firebase_admin import firestore
db = firestore.client()

# 사용자가 본 시험지: id=203 (server5.log 에서)
test_id = 203
test_doc = db.collection("saved_tests").document(str(test_id)).get()
uid = test_doc.to_dict().get("user_id") if test_doc.exists else None
if not uid:
    print(f"test {test_id} 못 찾음")
    sys.exit(0)

fake_user = SessionUser(uid=uid, email="t", role="admin", display_id="t", display_name="t")
app.dependency_overrides[require_user] = lambda: fake_user
app.dependency_overrides[get_optional_user] = lambda: fake_user
client = TestClient(app)

r = client.get(f"/partial/library/test/{test_id}/full")
print(f"GET /full status={r.status_code}, len={len(r.text)}")
ids = re.findall(r'id="(pref-cell[^"]*)"', r.text)
targets = re.findall(r'hx-target="(#pref-cell[^"]*)"', r.text)
print(f"id 패턴 (상위 5): {ids[:5]}")
print(f"hx-target (상위 5): {targets[:5]}")
if any('[' in i or '중' in i for i in ids):
    print("\n⚠️  옛 패턴(한글/대괄호 ID) 발견")
else:
    print("\n✅ 모든 ID 안전 (CSS selector 호환)")

