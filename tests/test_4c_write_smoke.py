# -*- coding: utf-8 -*-
"""
Phase 4-C 스모크: SQLite/Firestore 양 모드에서 7개 WRITE 메서드를 직접 호출.

각 케이스 = create → read-back → update/cleanup. 영구 부작용 없도록
스크립트가 만든 도큐먼트는 같은 스크립트가 정리한다.

실행:
  python tests/test_4c_write_smoke.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ADMIN_UID = "8YrxTdZYYcYts5bm4pkOdog5Bn92"
LOCAL_DB = os.path.join(ROOT, "problem_bank.db")
SA_PATH = os.path.join(ROOT, "backend", "naegiwangbank-firebase-adminsdk-fbsvc-5e5e798b33.json")

PASS = 0
FAIL = 0


def case(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}  {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def smoke_writes(label, eng, uid):
    print(f"\n=== {label} ===")
    tag = f"_4Csmoke_{int(time.time())}"

    # ────────── 1) create_folder ──────────
    res = eng.create_folder(f"테스트폴더{tag}", uid)
    case(f"{label} create_folder root", res.get("success") and res.get("id") is not None,
         f"(id={res.get('id')})")
    folder_id = res.get("id")

    # 자식 폴더
    res2 = eng.create_folder(f"하위{tag}", uid, parent_id=folder_id)
    case(f"{label} create_folder child", res2.get("success"),
         f"(id={res2.get('id')})")
    child_id = res2.get("id")

    # ────────── 2) rename_folder ──────────
    ok = eng.rename_folder(folder_id, f"개명폴더{tag}")
    case(f"{label} rename_folder", ok)
    # read-back
    folders = {f["id"]: f["name"] for f in eng.get_folders(uid)}
    case(f"{label} rename verify", folders.get(folder_id) == f"개명폴더{tag}",
         f"(name={folders.get(folder_id)})")

    # ────────── 3) save_test (insert) ──────────
    fake_problem_ids = ["dummy_pid_1", "dummy_pid_2"]
    test_data = {
        "title": f"테스트시험지{tag}",
        "unit_summary": "스모크",
        "directory_id": child_id,
        "problem_ids": fake_problem_ids,
        "metadata": {"source": "smoke", "tag": tag},
    }
    sres = eng.save_test(test_data, uid)
    case(f"{label} save_test insert", sres.get("success") and sres.get("id"),
         f"(id={sres.get('id')})")
    test_id = sres.get("id")

    # ────────── 4) save_test (update) ──────────
    test_data2 = dict(test_data, id=test_id, title=f"갱신{tag}")
    ures = eng.save_test(test_data2, uid)
    case(f"{label} save_test update", ures.get("success") and ures.get("id") == test_id)

    # 시험지 detail read-back (problems JOIN 은 캐시에 의존해서 dummy id 일 땐 비어있어도 OK)
    detail = eng.get_test_detail(test_id, uid)
    case(f"{label} save_test detail title",
         detail and detail.get("title") == f"갱신{tag}",
         f"(title={detail.get('title') if detail else None})")

    # ────────── 5) set_preference ──────────
    ok_p = eng.set_preference(uid, "smoke_pref_pid", "Good")
    case(f"{label} set_preference Good", ok_p)
    prefs = eng.get_preferences_bulk(uid, ["smoke_pref_pid"])
    case(f"{label} preference verify", prefs.get("smoke_pref_pid") == "Good",
         f"(map={prefs})")
    ok_p2 = eng.set_preference(uid, "smoke_pref_pid", None)  # 삭제
    case(f"{label} set_preference delete", ok_p2)
    prefs2 = eng.get_preferences_bulk(uid, ["smoke_pref_pid"])
    case(f"{label} preference deleted", "smoke_pref_pid" not in prefs2)

    # ────────── 6) save_scores ──────────
    scores = {"dummy_pid_1": 1, "dummy_pid_2": 0}
    ok_s = eng.save_scores(test_id, scores)
    case(f"{label} save_scores", ok_s)
    got = eng.get_scores_for_test(test_id)
    case(f"{label} scores verify",
         got.get("dummy_pid_1") == 1 and got.get("dummy_pid_2") == 0,
         f"(got={got})")

    # ────────── 7) delete_test ──────────
    ok_d = eng.delete_test(test_id)
    case(f"{label} delete_test", ok_d)
    detail2 = eng.get_test_detail(test_id, uid)
    case(f"{label} delete_test verify", detail2 is None)
    # 점수 정리도 확인
    got2 = eng.get_scores_for_test(test_id)
    case(f"{label} delete_test scores cleared", len(got2) == 0)

    # ────────── 8) delete_folder (보호 / 비어있지 않음 / 정상) ──────────
    # 보호 폴더 보호 — 오답 폴더 (Phase 3 마이그레이션 데이터)
    wrong_id = eng.get_protected_folder_id("오답", uid)
    if wrong_id is not None:
        rprot = eng.delete_folder(wrong_id)
        case(f"{label} delete_folder protected denied",
             not rprot.get("success"),
             f"(msg={rprot.get('message')})")

    # 정상 삭제 (자식 → 부모 순)
    rc = eng.delete_folder(child_id)
    case(f"{label} delete_folder child", rc.get("success"),
         f"(msg={rc.get('message')})")
    rp = eng.delete_folder(folder_id)
    case(f"{label} delete_folder parent", rp.get("success"),
         f"(msg={rp.get('message')})")

    # 사후 검증
    folders_after = {f["id"] for f in eng.get_folders(uid)}
    case(f"{label} delete_folder gone",
         folder_id not in folders_after and child_id not in folders_after)


def main():
    # SQLite 모드
    os.environ["DATA_ENGINE"] = "sqlite"
    from backend.data_engine import make_engine, get_engine_mode
    print(f"DATA_ENGINE = {get_engine_mode()}")
    eng = make_engine(LOCAL_DB, verbose=False)
    smoke_writes("SQLite", eng, ADMIN_UID)

    # Firestore 모드
    os.environ["DATA_ENGINE"] = "firestore"
    import firebase_admin
    from firebase_admin import credentials
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SA_PATH))

    print(f"\nDATA_ENGINE = {get_engine_mode()}")
    eng2 = make_engine(LOCAL_DB, verbose=False)
    smoke_writes("Firestore", eng2, ADMIN_UID)

    print(f"\n{'='*40}\nPASS: {PASS}    FAIL: {FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
