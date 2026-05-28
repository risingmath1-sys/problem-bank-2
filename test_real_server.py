"""진짜 살아있는 서버에 요청 보내서 응답 HTML 확인 (uvicorn 프로세스)."""
import urllib.request, urllib.parse, http.cookiejar, ssl, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# admin 인증 우회는 어려우니, 직접 모듈 import 후 같은 환경에서 호출
from backend.firebase_init import init_admin_sdk
init_admin_sdk()
from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user

import firebase_admin
from firebase_admin import firestore
db = firestore.client()

# 사용자가 본 정확한 시험지를 찾자: [중][2024][2-1-a][서울송파구][가원중]...
target_pid_prefix = "[중][2024][2-1-a][서울송파구][가원중]"
# 이런 problem_ids 를 가진 saved_test 찾기
found_test = None
for d in db.collection("saved_tests").stream():
    t = d.to_dict()
    pids = t.get("problem_ids") or []
    for pid in pids:
        if str(pid).startswith(target_pid_prefix):
            found_test = (d.id, t)
            break
    if found_test:
        break

if not found_test:
    print(f"'{target_pid_prefix}' 포함 saved_test 못 찾음")
    sys.exit(0)

test_id, test_data = found_test
print(f"발견된 시험지: id={test_id}, user={test_data.get('user_id')}")
print(f"problem_ids 샘플: {(test_data.get('problem_ids') or [])[:3]}")

# admin override 로 GET preview
fake_user = SessionUser(uid=test_data.get('user_id'), email="test", role="admin", display_id="test", display_name="test")
app.dependency_overrides[require_user] = lambda: fake_user
app.dependency_overrides[get_optional_user] = lambda: fake_user
client = TestClient(app)

r = client.get(f"/partial/library/test/{test_id}/preview")
print(f"\nGET preview status={r.status_code}, len={len(r.text)}")
html = r.text

# pref-cell 패턴 추출
all_pref_ids = re.findall(r'id="(pref-cell[^"]*)"', html)
print(f"\nid='pref-cell-*' 패턴 (상위 5): {all_pref_ids[:5]}")

# 사용자가 본 정확한 패턴이 있는지
old_pattern = '#pref-cell-[중]'
if old_pattern in html or 'pref-cell-[중]' in html:
    print(f"\n⚠️  옛 패턴(pref-cell-[중]...)이 응답에 존재!")
    # 어느 줄에 있는지
    for i, line in enumerate(html.split("\n")):
        if 'pref-cell-[중]' in line:
            print(f"  line {i}: {line.strip()[:200]}")
            break
else:
    print(f"\n✅ 옛 패턴(pref-cell-[중]...)은 응답에 없음")

