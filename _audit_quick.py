"""Quick audit — 3 핀픽스 검증."""
import io, sys, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.firebase_init import init_admin_sdk
init_admin_sdk()
from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user

fake = SessionUser(uid='admin', email='a@x', role='admin', display_id='a', display_name='a')
app.dependency_overrides[require_user] = lambda: fake
app.dependency_overrides[get_optional_user] = lambda: fake
c = TestClient(app)

print("=== 1. Step2 우측 패널 마커 ===")
r = c.post('/partial/random/step2',
           content=urllib.parse.urlencode([('units', 'medium:A1:2022')]),
           headers={'content-type': 'application/x-www-form-urlencoded'})
print(f"  status={r.status_code}, len={len(r.text)}")
checks = [
    ("최신기출 우선선택 라벨", "최신기출 우선선택" in r.text),
    ("recent_first 체크박스", 'name="recent_first"' in r.text),
    ("제외설정 보기 버튼", "제외설정 보기" in r.text),
    ("exclusion_dialog hx-get", "exclusion_dialog" in r.text),
    ("detail-filter-toggle 버튼", "detail-filter-toggle" in r.text),
    ("detail-filter-body div", "detail-filter-body" in r.text),
]
for label, ok in checks:
    print(f"  {'✓' if ok else '❌'} {label}")

print("\n=== 2. 제외설정 다이얼로그 ===")
r = c.get('/partial/random/exclusion_dialog')
print(f"  status={r.status_code}, len={len(r.text)}")
checks2 = [
    ("다이얼로그 헤더", "일회성 출제 제외 시험지 선택" in r.text),
    ("적용 버튼", "✔ 적용" in r.text),
    ("excl_tid 체크박스 name", 'name="excl_tid"' in r.text or "저장된 시험지가 없습니다" in r.text),
]
for label, ok in checks2:
    print(f"  {'✓' if ok else '❌'} {label}")

print("\n=== 3. 제외설정 적용 ===")
r = c.post('/partial/random/exclusion_apply',
           content=urllib.parse.urlencode([]),
           headers={'content-type': 'application/x-www-form-urlencoded'})
print(f"  status={r.status_code}, body: {r.text[:120]}")

print("\n=== 결과 ===")
all_ok = all(ok for _, ok in checks + checks2)
print("🎉 모든 검수 PASS" if all_ok else "⚠ 일부 실패")
