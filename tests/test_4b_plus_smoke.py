# -*- coding: utf-8 -*-
"""
Phase 4-B+ 스모크: SQLite/Firestore 양 모드에서 admin uid 로 직접 메서드 호출 시
폴더/시험지/선호도가 정상 노출되는지 확인.

main_gui.py 의 27개 호출 사이트에 self.current_user_id 가 주입됐고,
SQLite legacy user_id 가 admin uid 로 일괄 갱신됐다는 가정.

실행:
  python tests/test_4b_plus_smoke.py
"""
import os
import sys

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


def smoke_engine(label, eng, uid):
    print(f"\n=== {label} ===")
    folders = eng.get_folders(uid)
    case(f"{label} get_folders > 0", len(folders) > 0, f"({len(folders)} folders)")

    tests_root = eng.get_tests(None, uid)
    case(f"{label} get_tests(None) shape", isinstance(tests_root, list),
         f"({len(tests_root)} root tests)")

    sorted_all = eng.get_all_tests_sorted(uid)
    case(f"{label} get_all_tests_sorted >= root", len(sorted_all) >= len(tests_root),
         f"({len(sorted_all)} total tests)")

    stats = eng.get_user_storage_stats(uid)
    case(f"{label} stats has total_tests/root_items",
         "total_tests" in stats and "root_items" in stats,
         f"(total={stats.get('total_tests')}, root={stats.get('root_items')})")

    if folders:
        f0 = folders[0]
        sub = eng.get_all_subfolder_ids(f0["id"])
        case(f"{label} get_all_subfolder_ids[{f0['id']}] non-empty",
             f0["id"] in sub, f"(sub={sub[:3]})")

        cnt = eng.get_folder_test_count(f0["id"])
        case(f"{label} get_folder_test_count[{f0['id']}] >=0", cnt >= 0,
             f"({cnt} tests)")

    # 보호 폴더 (오답)
    wrong_id = eng.get_protected_folder_id("오답", uid)
    case(f"{label} get_protected_folder_id('오답')", wrong_id is not None,
         f"(id={wrong_id})")

    # 첫 시험지 detail
    sample_test = None
    if sorted_all:
        sample_test = sorted_all[0]
    elif tests_root:
        sample_test = tests_root[0]
    if sample_test:
        d = eng.get_test_detail(sample_test["id"], uid)
        case(f"{label} get_test_detail[{sample_test['id']}] non-None",
             d is not None and d.get("title"),
             f"(title={d.get('title')!r})" if d else "(None)")

    # 선호도
    pref_uids = eng.get_all_preference_user_ids()
    case(f"{label} get_all_preference_user_ids", isinstance(pref_uids, list),
         f"({len(pref_uids)} uids)")

    # rate filter
    rate_ids = eng.get_problem_ids_by_rate(0.0, 1.0)
    case(f"{label} get_problem_ids_by_rate(0,1)", isinstance(rate_ids, list),
         f"({len(rate_ids)} ids)")


def main():
    # SQLite 모드
    os.environ["DATA_ENGINE"] = "sqlite"
    from backend.data_engine import make_engine, get_engine_mode
    print(f"DATA_ENGINE = {get_engine_mode()}")
    eng = make_engine(LOCAL_DB, verbose=False)
    smoke_engine("SQLite", eng, ADMIN_UID)

    # Firestore 모드
    os.environ["DATA_ENGINE"] = "firestore"
    # 캐시 + Firestore 클라이언트 미리 초기화
    import firebase_admin
    from firebase_admin import credentials
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SA_PATH))

    # data_engine 모듈은 이미 로드됨 → make_engine 재호출
    print(f"\nDATA_ENGINE = {get_engine_mode()}")
    eng2 = make_engine(LOCAL_DB, verbose=False)
    smoke_engine("Firestore", eng2, ADMIN_UID)

    print(f"\n{'='*40}\nPASS: {PASS}    FAIL: {FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
