# -*- coding: utf-8 -*-
"""
Phase 4-A 검증: SQLite (LocalDBEngine) 와 Firestore 캐시 기반
LocalDBEngine 이 problems READ 메서드 14개에서 동일 결과를 반환하는지 확인.

원리:
  - 캐시는 problems 컬렉션의 byte-for-byte 미러여야 함.
  - 두 엔진에 같은 입력을 주고 결과를 diff.
  - RANDOM() 의존 (fetch_random_problems) 은 카운트만 비교.

실행:
  python tests/test_engine_parity.py

종료 코드:
  0 = 모든 케이스 일치
  1 = 1건 이상 불일치
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

from backend.db_engine import LocalDBEngine

LOCAL_DB = os.path.join(ROOT, "problem_bank.db")
CACHE_DB = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "naegiwangbank", "problems_cache.sqlite",
)

PASS = 0
FAIL = 0
RESULTS = []


def _normalize_dict(d):
    """비결정적 GROUP_CONCAT 정렬, 캐시 전용 updated_at 컬럼 제거."""
    out = {}
    for k, v in d.items():
        if k == "updated_at":
            continue  # 캐시 메타 — 원본에는 없음
        if isinstance(v, str) and "," in v and k in ("units_concat",):
            out[k] = ",".join(sorted(v.split(",")))
        else:
            out[k] = v
    return out


def _eq(a, b):
    """딕셔너리·리스트·기본형 비교. 리스트는 set 비교 (순서 무시)."""
    if isinstance(a, list) and isinstance(b, list):
        if a and isinstance(a[0], dict):
            na = [_normalize_dict(d) for d in a]
            nb = [_normalize_dict(d) for d in b]
            return sorted(na, key=lambda d: json.dumps(d, sort_keys=True, default=str)) == \
                   sorted(nb, key=lambda d: json.dumps(d, sort_keys=True, default=str))
        return sorted(a, key=lambda x: (x is None, str(x))) == \
               sorted(b, key=lambda x: (x is None, str(x)))
    return a == b


def case(name, sqlite_val, firestore_val, mode="full"):
    """mode: full | count | type"""
    global PASS, FAIL
    if mode == "count":
        ok = (len(sqlite_val) if hasattr(sqlite_val, "__len__") else sqlite_val) == \
             (len(firestore_val) if hasattr(firestore_val, "__len__") else firestore_val)
        s_repr = f"len={len(sqlite_val) if hasattr(sqlite_val,'__len__') else sqlite_val}"
        f_repr = f"len={len(firestore_val) if hasattr(firestore_val,'__len__') else firestore_val}"
    else:
        ok = _eq(sqlite_val, firestore_val)
        s_repr = repr(sqlite_val)[:80]
        f_repr = repr(firestore_val)[:80]

    if ok:
        PASS += 1
        RESULTS.append(("PASS", name, s_repr, f_repr))
    else:
        FAIL += 1
        RESULTS.append(("FAIL", name, s_repr, f_repr))
        print(f"  [FAIL] {name}")
        print(f"     sqlite : {s_repr}")
        print(f"     cache  : {f_repr}")


def main():
    if not os.path.exists(LOCAL_DB):
        print(f"[!] 로컬 DB 없음: {LOCAL_DB}"); sys.exit(2)
    if not os.path.exists(CACHE_DB):
        print(f"[!] 캐시 DB 없음: {CACHE_DB}")
        print("    backfill 후 ProblemsCache.ensure_synced() 먼저 실행하세요.")
        sys.exit(2)

    print(f"local  : {LOCAL_DB}")
    print(f"cache  : {CACHE_DB}")
    print("-" * 70)

    s = LocalDBEngine(LOCAL_DB)   # 원본
    f = LocalDBEngine(CACHE_DB)   # 캐시 (Firestore 미러)

    # 1) get_all_problem_ids: 전수 비교
    case("get_all_problem_ids",
         s.get_all_problem_ids(),
         f.get_all_problem_ids())

    # 2) query_counts: 다양한 필터
    case("query_counts(no filter)",
         s.query_counts(), f.query_counts())
    case("query_counts(no filter, include_excluded)",
         s.query_counts(include_excluded=True),
         f.query_counts(include_excluded=True))
    case("query_counts(source=SUNEUNG_SPECIAL)",
         s.query_counts({"source": "SUNEUNG_SPECIAL"}),
         f.query_counts({"source": "SUNEUNG_SPECIAL"}))
    case("query_counts(difficulty in [A,B])",
         s.query_counts({"difficulty": ["A", "B"]}),
         f.query_counts({"difficulty": ["A", "B"]}))
    case("query_counts(year ne 2024)",
         s.query_counts({"year": {"ne": "2024"}}),
         f.query_counts({"year": {"ne": "2024"}}))
    case("query_counts(school like %고%)",
         s.query_counts({"school": {"like": "%고%"}}),
         f.query_counts({"school": {"like": "%고%"}}))

    # 3) search_schools — LIMIT 충분히 크게 (없는 것 까지)
    case("search_schools(고, limit=999)",
         s.search_schools("고", limit=999),
         f.search_schools("고", limit=999))

    # 4) search_mock_exam_brands
    case("search_mock_exam_brands(평가원)",
         s.search_mock_exam_brands("평가원"),
         f.search_mock_exam_brands("평가원"))
    case("search_mock_exam_brands(빈값)",
         s.search_mock_exam_brands(""),
         f.search_mock_exam_brands(""))

    # 5) get_unique_years
    case("get_unique_years",
         s.get_unique_years(),
         f.get_unique_years())

    # 6) search_problems — limit 매우 크게 → 동일 set 보장
    case("search_problems(source=NAESIN_A, limit=99999)",
         s.search_problems({"source": "NAESIN_A"}, limit=99999),
         f.search_problems({"source": "NAESIN_A"}, limit=99999))

    # 7) search_exams_grouped
    case("search_exams_grouped(source=MOCK_EXAM)",
         s.search_exams_grouped({"source": "MOCK_EXAM"}),
         f.search_exams_grouped({"source": "MOCK_EXAM"}))

    # 8) get_naesin_score_thresholds
    case("get_naesin_score_thresholds",
         s.get_naesin_score_thresholds(),
         f.get_naesin_score_thresholds())

    # 9) get_subject_unit_codes
    case("get_subject_unit_codes(수학)",
         s.get_subject_unit_codes("수학"),
         f.get_subject_unit_codes("수학"))

    # 10) get_problems_by_files (샘플 파일 1개)
    s_years = s.get_unique_years()
    rows = s.search_problems({"source": "MOCK_EXAM"}, limit=1)
    sample_file = rows[0]["file_name"] if rows else None
    if sample_file:
        case(f"get_problems_by_files([{sample_file}])",
             s.get_problems_by_files([sample_file]),
             f.get_problems_by_files([sample_file]))
        case(f"get_unit_stats([{sample_file}])",
             s.get_unit_stats([sample_file]),
             f.get_unit_stats([sample_file]))

    # 11) get_ids_by_mock_brands
    brands = s.search_mock_exam_brands("")
    if brands:
        case(f"get_ids_by_mock_brands([{brands[0]}])",
             s.get_ids_by_mock_brands([brands[0]]),
             f.get_ids_by_mock_brands([brands[0]]))

    # 12) check_duplicate_exam
    sample_meta = {"source": "MOCK_EXAM", "year": "2024",
                   "month": "06", "subject": "수학"}
    case("check_duplicate_exam(MOCK_EXAM 2024-06)",
         s.check_duplicate_exam(sample_meta),
         f.check_duplicate_exam(sample_meta))

    # 13) fetch_random_problems — RANDOM() 의존 → 카운트만 일치 확인
    crit = [{"filters": {"source": "SUNEUNG_SPECIAL", "difficulty": "C"}, "count": 5}]
    case("fetch_random_problems (count match)",
         s.fetch_random_problems(crit),
         f.fetch_random_problems(crit),
         mode="count")

    # ----- 보고 -----
    print("-" * 70)
    print(f"PASS: {PASS}    FAIL: {FAIL}")
    if FAIL == 0:
        print("✅  모든 케이스 일치")
        sys.exit(0)
    else:
        print("❌  불일치 발생 — 위 로그 확인")
        sys.exit(1)


if __name__ == "__main__":
    main()
