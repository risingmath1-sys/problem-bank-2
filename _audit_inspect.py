import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from backend.firebase_init import init_admin_sdk
init_admin_sdk()
from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user, require_admin
fake = SessionUser(uid='admin', email='a@x', role='admin', display_id='a', display_name='a')
app.dependency_overrides[get_optional_user] = lambda: fake
app.dependency_overrides[require_user] = lambda: fake
app.dependency_overrides[require_admin] = lambda: fake
c = TestClient(app)

print("=== /random h1 + checkbox class ===")
r = c.get('/random')
m = re.search(r'<h1[^>]*>([^<]+)</h1>', r.text)
print('h1:', repr(m.group(1).strip() if m else 'none'))
m2 = re.findall(r'class="([^"]*?check[^"]*?)"', r.text)
print('checkbox-related classes (first 5):', m2[:5])

print("\n=== POST /partial/original/files NAESIN_A ===")
import urllib.parse
r = c.post('/partial/original/files',
           content=urllib.parse.urlencode([('source', 'NAESIN_A')]),
           headers={'content-type': 'application/x-www-form-urlencoded'})
print('status:', r.status_code, 'len:', len(r.text))
print('body[:300]:', r.text[:300])
