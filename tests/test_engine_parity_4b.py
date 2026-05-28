# -*- coding: utf-8 -*-
"""
Phase 4-B 검증 (2026-04-29 재작성): FirestoreEngine 의 개인 데이터 READ
17개 메서드가 실제 Firestore 에서 정상 동작하는지 smoke test.

배경:
  - Phase 4-B+ 에서 SQLite/Firestore 양쪽 데이터를 admin uid 로 통합.
  - 그러나 2026-04-28 Firestore 순정화 이후 모든 쓰기는 Firestore 단방향
    → SQLite 는 더 이상 동기화되지 않음 (의도된 drift).
  - 따라서 SQLite vs Firestore parity 비교는 폐기.
  - 본 테스트는 FirestoreEngine 의 메서드별 정상 동작 + 결과 shape 만 검증.

실행:
  python tests/test_engine_parity_4b.py

종료 코드:
  0 = 모든 케이스 통과
  1 = 1건 이상 실패
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import firebase_admin
from firebase_admin import credentials

SA_PATH = os.path.join(ROOT, "backend", "naegiwangbank-firebase-adminsdk-fbsvc-5e5e798b33.json")
LOCAL_DB = os.path.join(ROOT, "problem_bank.db")
ADMIN_UID = "8YrxTdZYYcYts5bm4pkOdog5Bn92"

PASS = 0
FAIL = 0


def case(name, ok, detail_pass="", detail_fail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}  {detail_pass}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail_fail}")


def init_fs():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
    from firebase_admin import firestore as _fs
    return _fs.client()


def main():
    fs = init_fs()

    os.environ["DATA_ENGINE"] = "firestore"
    from backend.firestore_engine import FirestoreEngine

    print(f"admin uid : {ADMIN_UID}")
    print("-" * 70)

    eng = FirestoreEngine(local_db_path=LOCAL_DB, firestore_client=fs, verbose=False)

    # ---- 폴더 ----------------------------------------------------------
    folders = eng.get_folders(ADMIN_UID)
    case("get_folders returns list",
         isinstance(folders, list) and len(folders) > 0,
         detail_pass=f"({len(folders)} folders)",
         detail_fail=f"got {type(folders).__name__} len={len(folders) if hasattr(folders, '__len__') else '?'}")

    case("get_folders entries have id+name",
         all(("id" in f and "name" in f) for f in folders),
         detail_pass="all entries have id/name keys")

    protected = [f for f in folders if f.get("is_protected")]
    case("at least one protected folder exists",
         len(protected) > 0,
         detail_pass=f"protected={[f['name'] for f in protected]}",
         detail_fail="no protected folder for admin uid")

    if protected:
        pid = protected[0]["id"]
        pname = protected[0]["name"]
        case(f"is_folder_protected({pid}) → True",
             eng.is_folder_protected(pid) is True,
             detail_pass="True")
        case(f"get_protected_folder_id({pname!r}, admin) → {pid}",
             eng.get_protected_folder_id(pname, ADMIN_UID) == pid,
             detail_pass=f"id={pid}",
             detail_fail=f"got {eng.get_protected_folder_id(pname, ADMIN_UID)} expected {pid}")

    nonprot = [f for f in folders if not f.get("is_protected")]
    if nonprot:
        nid = nonprot[0]["id"]
        case(f"is_folder_protected({nid}) → False",
             eng.is_folder_protected(nid) is False,
             detail_pass="False")
        case(f"get_folder_test_count({nid}) is int",
             isinstance(eng.get_folder_test_count(nid), int),
             detail_pass=f"count={eng.get_folder_test_count(nid)}")
        subs = eng.get_all_subfolder_ids(nid)
        case(f"get_all_subfolder_ids({nid}) includes self",
             nid in subs,
             detail_pass=f"sub={subs}",
             detail_fail=f"sub={subs} missing self")
        case(f"is_folder_empty({nid}) is bool",
             isinstance(eng.is_folder_empty(nid), bool),
             detail_pass=f"empty={eng.is_folder_empty(nid)}")

    # ---- 시험지 --------------------------------------------------------
    tests_root = eng.get_tests(None, ADMIN_UID)
    case("get_tests(None, admin) returns list",
         isinstance(tests_root, list),
         detail_pass=f"({len(tests_root)} root tests)")

    sample_test = tests_root[0] if tests_root else None
    if sample_test is None and folders:
        for f in folders:
            ts = eng.get_tests(f["id"], ADMIN_UID)
            if ts:
                sample_test = ts[0]; break

    case("at least one test exists for admin uid",
         sample_test is not None,
         detail_pass=f"sample_test_id={sample_test['id'] if sample_test else None}",
         detail_fail="no tests anywhere — cannot exercise read-by-id paths")

    if sample_test:
        tid = sample_test["id"]
        d = eng.get_test_detail(tid, ADMIN_UID)
        case(f"get_test_detail({tid}) returns dict",
             isinstance(d, dict),
             detail_pass=f"title={d.get('title','')[:30]!r}")
        if d:
            case(f"get_test_detail({tid}) has problems list",
                 isinstance(d.get("problems"), list),
                 detail_pass=f"({len(d.get('problems', []))} problems)")
            pids_field = d.get("problem_ids")
            pids = json.loads(pids_field) if isinstance(pids_field, str) else pids_field
            case(f"get_test_detail({tid}) problem_ids matches problems count",
                 len(pids) == len(d.get("problems", [])),
                 detail_pass=f"({len(pids)} ids)",
                 detail_fail=f"problem_ids={len(pids)} vs problems={len(d.get('problems', []))}")

    sorted_tests = eng.get_all_tests_sorted(ADMIN_UID)
    case("get_all_tests_sorted(admin) returns list",
         isinstance(sorted_tests, list),
         detail_pass=f"({len(sorted_tests)} tests)")

    stats = eng.get_user_storage_stats(ADMIN_UID)
    case("get_user_storage_stats(admin) returns dict with required keys",
         isinstance(stats, dict) and "total_tests" in stats and "root_items" in stats,
         detail_pass=f"total_tests={stats.get('total_tests')} root_items={stats.get('root_items')}",
         detail_fail=f"got {stats}")

    case("storage_stats.total_tests matches len(get_all_tests_sorted)",
         stats.get("total_tests") == len(sorted_tests),
         detail_pass=f"({stats.get('total_tests')})",
         detail_fail=f"stats={stats.get('total_tests')} sorted={len(sorted_tests)}")

    # ---- 점수 ----------------------------------------------------------
    pids_with_scores = eng.get_problem_ids_with_scores()
    case("get_problem_ids_with_scores returns iterable of unique ids",
         isinstance(pids_with_scores, (set, list)) and len(pids_with_scores) == len(set(pids_with_scores)),
         detail_pass=f"({len(pids_with_scores)} ids)",
         detail_fail=f"got {type(pids_with_scores).__name__} with dups")

    if pids_with_scores:
        sample_ids = list(pids_with_scores)[:5]
        rates = eng.get_correct_rates_bulk(sample_ids)
        case("get_correct_rates_bulk(5 sample) returns dict",
             isinstance(rates, dict) and set(rates.keys()) == set(sample_ids),
             detail_pass=f"({len(rates)} rates)",
             detail_fail=f"keys mismatch: got {set(rates.keys())} vs expected {set(sample_ids)}")
        case("get_correct_rates_bulk values are 0~1 or None",
             all(v is None or 0.0 <= v <= 1.0 for v in rates.values()),
             detail_pass="all in range",
             detail_fail=f"out of range: {[v for v in rates.values() if v is not None and (v < 0 or v > 1)]}")

    by_rate = eng.get_problem_ids_by_rate(0.0, 1.0)
    case("get_problem_ids_by_rate(0,1) returns subset of all-with-scores",
         isinstance(by_rate, (set, list)) and set(by_rate).issubset(set(pids_with_scores)),
         detail_pass=f"({len(by_rate)} ids)",
         detail_fail=f"got {len(by_rate)} ids, not subset of {len(pids_with_scores)}")

    if sample_test:
        tid = sample_test["id"]
        s = eng.get_scores_for_test(tid)
        case(f"get_scores_for_test({tid}) returns dict",
             isinstance(s, dict),
             detail_pass=f"({len(s)} entries)",
             detail_fail=f"got {type(s).__name__}")
        case(f"get_scores_for_test({tid}) values are 0/1",
             all(v in (0, 1, True, False) for v in s.values()),
             detail_pass="all 0/1",
             detail_fail=f"unexpected values: {set(s.values())}")

    # ---- 선호도 --------------------------------------------------------
    pref_uids = eng.get_all_preference_user_ids()
    case("get_all_preference_user_ids returns list",
         isinstance(pref_uids, list),
         detail_pass=f"({pref_uids})")
    case("admin uid present in preference user_ids",
         ADMIN_UID in pref_uids,
         detail_pass="found",
         detail_fail=f"admin uid not in {pref_uids}")

    case("get_preferences_bulk(empty) → empty dict",
         eng.get_preferences_bulk(ADMIN_UID, []) == {},
         detail_pass="OK")

    sample_pref_pids = []
    for d in fs.collection("problem_preferences").where("user_id", "==", ADMIN_UID).limit(5).stream():
        data = d.to_dict() or {}
        if "problem_id" in data:
            sample_pref_pids.append(data["problem_id"])

    if sample_pref_pids:
        prefs = eng.get_preferences_bulk(ADMIN_UID, sample_pref_pids)
        case("get_preferences_bulk(5 sample) returns dict",
             isinstance(prefs, dict) and len(prefs) > 0,
             detail_pass=f"({len(prefs)} entries)",
             detail_fail=f"got {prefs}")
        case("get_preferences_bulk values are valid labels",
             all(v in ("Good", "Soso", "Bad", "Excluded", None) for v in prefs.values()),
             detail_pass="all labels valid",
             detail_fail=f"unexpected: {set(prefs.values())}")

    by_pref = eng.get_problem_ids_by_preference([ADMIN_UID], ["Good"])
    case("get_problem_ids_by_preference(Good) returns set",
         isinstance(by_pref, set),
         detail_pass=f"({len(by_pref)} ids)",
         detail_fail=f"got {type(by_pref).__name__}")

    if sample_pref_pids:
        cand = sample_pref_pids + ["nonexistent_xxx"]
        by_pref_cand = eng.get_problem_ids_by_preference([ADMIN_UID], ["Good", "Soso", "Bad"], cand)
        case("get_problem_ids_by_preference(candidate) returns set ⊆ candidate",
             isinstance(by_pref_cand, set) and by_pref_cand.issubset(set(cand)),
             detail_pass=f"({len(by_pref_cand)} ids ⊆ {len(cand)} candidates)",
             detail_fail=f"not subset: extra={by_pref_cand-set(cand)}")

    print("-" * 70)
    print(f"PASS: {PASS}    FAIL: {FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
