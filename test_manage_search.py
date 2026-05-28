"""문제관리 검색 라우트 검증 — 새 필터들이 다 동작하는지."""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.firebase_init import init_admin_sdk
init_admin_sdk()
from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user, require_admin

fake_admin = SessionUser(uid="admin", email="t", role="admin", display_id="a", display_name="a")
app.dependency_overrides[require_user] = lambda: fake_admin
app.dependency_overrides[get_optional_user] = lambda: fake_admin
app.dependency_overrides[require_admin] = lambda: fake_admin
client = TestClient(app)

# 1. /manage GET (페이지 로드)
r = client.get("/manage")
print(f"[GET /manage] status={r.status_code}, len={len(r.text)}")
# 폼에 새 필드들 있는지 확인
new_fields = ['mng-curriculum', 'mng-subject', 'mng-unit-start', 'mng-unit-end',
              'mng-source-radio', 'mng-naesin-only', 'unit_like', 'diff_level',
              'mngRefreshSubjects', 'mngRefreshUnits', 'mngToggleNaesinFields']
missing = [f for f in new_fields if f not in r.text]
print(f"  새 필드/JS 누락: {missing}")
print(f"  ✅ 모든 새 필드 존재" if not missing else "  ⚠️ 누락 있음")

# 2. /partial/manage/files 호출 — 새 파라미터 전달
r = client.get("/partial/manage/files", params={
    "source": "NAESIN_N",
    "year": "2025", "grade": "고1", "semester": "1학기", "exam_type": "기말고사"
})
print(f"\n[GET /partial/manage/files NAESIN_N + 필터] status={r.status_code}, len={len(r.text)}")
# 검색 결과에 시험지 수 표시 있는지
files_count = len(re.findall(r'file_names', r.text))
print(f"  응답에 'file_names' 출현 수: {files_count}")

