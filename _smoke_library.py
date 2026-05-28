"""Library (Tab 3) smoke test — folder CRUD + test rename/move/delete + save_random_job."""
import io
import sys
import urllib.parse
import uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from backend.firebase_init import init_admin_sdk
init_admin_sdk()

from fastapi.testclient import TestClient
from server.main import app
from server.auth_dep import SessionUser, get_optional_user, require_user
from server.services.engine import get_engine
from server.workers.job_queue import get_queue, Job

fake_user = SessionUser(
    uid="admin", email="risingmath1@gmail.com", role="admin",
    display_id="admin", display_name="admin",
)
app.dependency_overrides[require_user] = lambda: fake_user
app.dependency_overrides[get_optional_user] = lambda: fake_user

client = TestClient(app)


def post_form(path, fields):
    body = urllib.parse.urlencode(fields, doseq=True)
    return client.post(
        path, content=body,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


engine = get_engine()
suffix = uuid.uuid4().hex[:6]


# 1) 폴더 생성
print("\n=== 1. POST /api/library/folder (root) ===")
r = post_form("/api/library/folder", [("name", f"smoke-{suffix}"), ("parent_id", "root")])
print("status:", r.status_code, "len:", len(r.text))
assert r.status_code == 200
assert f"smoke-{suffix}" in r.text
folders = engine.get_folders(fake_user.uid)
parent = next(f for f in folders if f["name"] == f"smoke-{suffix}")
print(f"✓ created parent folder id={parent['id']}")

# 2) 하위 폴더
print("\n=== 2. POST /api/library/folder (child) ===")
r = post_form("/api/library/folder", [("name", f"child-{suffix}"), ("parent_id", str(parent["id"]))])
assert r.status_code == 200
folders = engine.get_folders(fake_user.uid)
child = next(f for f in folders if f["name"] == f"child-{suffix}")
print(f"✓ created child folder id={child['id']} parent={child.get('parent_id')}")
assert child.get("parent_id") == parent["id"]

# 3) 폴더 이름 변경
print("\n=== 3. PATCH /api/library/folder/{id} ===")
new_name = f"renamed-{suffix}"
r = client.patch(
    f"/api/library/folder/{child['id']}",
    content=urllib.parse.urlencode([("name", new_name)]),
    headers={"content-type": "application/x-www-form-urlencoded"},
)
print("status:", r.status_code)
assert r.status_code == 200
assert new_name in r.text
print(f"✓ renamed child → {new_name}")

# 4) 시험지 생성 (engine 직접) — 테스트 대상 확보
print("\n=== 4. seed test via engine.save_test ===")
res = engine.save_test({
    "title": f"smoketest-{suffix}",
    "unit_summary": "단원요약",
    "directory_id": None,
    "problem_ids": [],
    "metadata": {},
}, fake_user.uid)
assert res.get("success"), res
test_id = res["id"]
print(f"✓ created test id={test_id}")

# 5) 시험지 이름 변경
print("\n=== 5. POST /api/library/test/{id}/rename ===")
r = post_form(f"/api/library/test/{test_id}/rename", [
    ("title", f"renamed-test-{suffix}"),
    ("unit_summary", "변경된요약"),
])
print("status:", r.status_code)
assert r.status_code == 200
detail = engine.get_test_detail(test_id, fake_user.uid)
assert detail["title"] == f"renamed-test-{suffix}"
assert detail["unit_summary"] == "변경된요약"
print("✓ test renamed")

# 6) 시험지 폴더 이동
print("\n=== 6. POST /api/library/test/{id}/move ===")
r = post_form(f"/api/library/test/{test_id}/move", [("folder_id", str(child["id"]))])
print("status:", r.status_code)
assert r.status_code == 200
detail = engine.get_test_detail(test_id, fake_user.uid)
assert detail.get("directory_id") == child["id"], f"expected {child['id']} got {detail.get('directory_id')}"
print(f"✓ moved test → folder {child['id']}")

# 6b) 루트로 이동
r = post_form(f"/api/library/test/{test_id}/move", [("folder_id", "root")])
assert r.status_code == 200
detail = engine.get_test_detail(test_id, fake_user.uid)
assert detail.get("directory_id") in (None, "", 0) or not detail.get("directory_id")
print("✓ moved test back to root")

# 7) 시험지 삭제
print("\n=== 7. DELETE /api/library/test/{id} ===")
r = client.delete(f"/api/library/test/{test_id}")
print("status:", r.status_code)
assert r.status_code == 200
assert engine.get_test_detail(test_id, fake_user.uid) is None
print("✓ test deleted")

# 8) save_random_job — fake job 등록 후 저장
print("\n=== 8. POST /api/library/save_random_job/{job_id} ===")
queue = get_queue()
fake_problems = []
# 실제 문제 id 1건 확보 (engine 으로 검색)
try:
    sample = engine.fetch_random_problems([{
        "source": "SUNEUNG_SPECIAL", "count": 1,
    }], exclude_ids=[], include_excluded=False)
    if sample:
        fake_problems = [{"id": sample[0]["id"]}]
except Exception as e:
    print(f"(fetch sample failed: {e})")
if not fake_problems:
    # fallback — engine.search_problems 로 1건
    try:
        rs = engine.search_problems({"source": "SUNEUNG_SPECIAL"}, limit=1)
        if rs:
            fake_problems = [{"id": rs[0]["id"]}]
    except Exception:
        pass

if fake_problems:
    job = Job(
        id=f"smoke-job-{suffix}",
        user_id=fake_user.uid,
        problems=fake_problems,
        options={"exam_unit": "단원자동", "exam_title": "테스트"},
        state="done",
    )
    queue.jobs[job.id] = job
    r = post_form(f"/api/library/save_random_job/{job.id}", [
        ("title", f"saved-from-job-{suffix}"),
        ("unit_summary", ""),
        ("folder_id", str(parent["id"])),
    ])
    print("status:", r.status_code, "snippet:", r.text[:200])
    assert r.status_code == 200
    assert "id=" in r.text
    # cleanup: 새로 만든 시험지 삭제
    import re
    m = re.search(r"id=(\d+)", r.text)
    if m:
        new_tid = int(m.group(1))
        engine.delete_test(new_tid)
        print(f"✓ save_random_job — created tid={new_tid} (cleaned up)")
else:
    print("(skipped — no sample problem available)")

# 9) 채점 (오답 만들기) — fake test 만든 후 GET /scoring + POST /save_wrong
print("\n=== 9. GET/POST /api/library/test/{id}/scoring + save_wrong ===")
problems_seed = engine.search_problems({}, limit=3) if hasattr(engine, "search_problems") else []
if problems_seed:
    pids = [p.get("id") for p in problems_seed if p.get("id")]
    res = engine.save_test({
        "title": f"scoring-{suffix}",
        "unit_summary": "",
        "directory_id": parent["id"],
        "problem_ids": pids,
        "metadata": {},
    }, fake_user.uid) or {}
    if res.get("success"):
        sc_tid = res.get("id")
        # 채점 화면 GET
        r = client.get(f"/api/library/test/{sc_tid}/scoring")
        assert r.status_code == 200, f"scoring GET failed: {r.status_code}"
        assert "채점" in r.text, "scoring partial 마커 누락"
        print(f"✓ scoring page loaded (tid={sc_tid})")
        # save_wrong: 첫 문제 X, 나머지 O
        fields = [(f"score_{pids[0]}", "0")]
        for pid in pids[1:]:
            fields.append((f"score_{pid}", "1"))
        r = post_form(f"/api/library/test/{sc_tid}/save_wrong", fields)
        assert r.status_code == 200, f"save_wrong failed: {r.status_code}"
        # 오답 시험지가 생성됐어야 함
        assert "오답" in r.text or "id=" in r.text
        print("✓ save_wrong OK")
        # cleanup
        engine.delete_test(sc_tid)
        # 새로 만든 오답 시험지도 정리
        import re
        m = re.search(r"id=(\d+)", r.text)
        if m:
            engine.delete_test(int(m.group(1)))
else:
    print("(skipped — no sample problems for scoring)")


# 10) 폴더 삭제 (자식 → 부모 순)
print("\n=== 10. DELETE /api/library/folder/{id} ===")
r = client.delete(f"/api/library/folder/{child['id']}")
print("child status:", r.status_code)
assert r.status_code == 200
r = client.delete(f"/api/library/folder/{parent['id']}")
print("parent status:", r.status_code)
assert r.status_code == 200
folders = engine.get_folders(fake_user.uid)
assert not any(f["id"] in (parent["id"], child["id"]) for f in folders)
print("✓ folders deleted")

print("\n=== LIBRARY SMOKE TESTS PASS ===")
