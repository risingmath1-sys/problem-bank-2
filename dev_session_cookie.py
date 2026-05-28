"""개발용: Firestore 의 admin user 를 찾아 세션 JWT 쿠키 값 출력.

사용법:
    python dev_session_cookie.py
출력:
    eyJhbGc...  (이걸 ngwb_session 쿠키에 넣어서 curl 로 호출)
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from firebase_admin import firestore
from server.auth_dep import SessionUser, issue_session_token

db = firestore.client()
docs = list(db.collection("users").where("role", "==", "admin").limit(1).stream())
if not docs:
    raise SystemExit("admin user not found")

doc = docs[0]
data = doc.to_dict()
user = SessionUser(
    uid=doc.id,
    display_id=data.get("display_id") or "admin",
    display_name=data.get("display_name") or "",
    role="admin",
    email=data.get("email") or f"{data.get('display_id','admin')}@naegiwang.local",
)
print(issue_session_token(user))
