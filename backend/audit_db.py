"""DB 정합성 자가검증 (재발 방지).

언제 돌리나:
  - 새 시험지 다수 인덱싱 직후
  - Firestore 데이터 의심될 때 정기 점검

검사 항목:
  1. unit_code ↔ subject 일관성 (예: 수학1 시험에 P/O/V 코드 = 오류)
  2. 빈 unit_code 비율
  3. 중학교 코드(Z*)가 [고] 시험지에 있는지
  4. mapped_unit_code != unit_code 인 잔재 (이번 사고처럼 잘못된 매핑 적용)

실행:
  python backend/audit_db.py
  python backend/audit_db.py --source NAESIN_N
  python backend/audit_db.py --year 2025
"""
import sys, io, argparse
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# subject → 허용 unit_code 접두사
# (unit_hierarchy.json 의 2022/2015 코드 체계 기준)
SUBJECT_EXPECTED = {
    # 공통수학1
    "공통수학1":   {"A","B","C","D"},
    "수학(상)":     {"A","B","E","F"},          # 2015 수학(상): A,B,E,F
    "수학(하)":     {"C","G"},                  # 2015 수학(하): C,G
    # 공통수학2 (2022만)
    "공통수학2":   {"E","F","G"},
    # 대수 (2022) / 수학1 (2015)
    "대수":         {"H","I","J"},
    "수학1":        {"H","I","J"},
    # 미적분I (2022) / 수학2 (2015)
    "미적분I":      {"K","L","M"},
    "수학2":        {"K","L","M"},
    # 확률과 통계
    "확률과통계":   {"N","O","P"},
    "확률과 통계":  {"N","O","P"},
    # 미적분II (2022) / 미적분 (2015)
    "미적분II":     {"Q","R","S"},
    "미적분":       {"Q","R","S"},
    # 기하
    "기하":         {"T","U","V"},
}


def _load_code_truth():
    """unit_hierarchy.json 에서 code → (middle_unit, large_unit) 정답표 로드.
    2022 우선 (2015 와 동일 코드면 2022 가 우선)."""
    import json
    path = PROJECT_ROOT / "backend" / "unit_hierarchy.json"
    with path.open(encoding="utf-8") as f:
        hier = json.load(f)
    out = {}
    for version in ["2022", "2015"]:
        for subj in hier.get(version, []):
            for large in subj.get("large_units", []):
                l_name = large.get("name", "")
                for med in large.get("medium_units", []):
                    code = med["code"]
                    if code not in out:
                        out[code] = (med.get("name", ""), l_name)
    return out


def audit(source: str = "", year: str = ""):
    from backend.firebase_init import init_admin_sdk
    try:
        init_admin_sdk()
    except Exception:
        pass
    import firebase_admin
    from firebase_admin import firestore
    db = firestore.client()

    print(f"=== DB 정합성 검증 (source={source or 'ALL'}, year={year or 'ALL'}) ===\n")
    CODE_TRUTH = _load_code_truth()

    q = db.collection("problems")
    if source:
        q = q.where("source", "==", source)
    if year:
        q = q.where("year", "==", year)

    docs = list(q.stream())
    print(f"검사 대상: {len(docs)}건\n")

    # 1. unit_code ↔ subject 일관성
    inconsistent = []      # (doc_id, subject, unit_code, expected_prefixes)
    empty_unit = 0
    z_in_high = []         # ([고] 파일인데 Z 코드) — 정상이긴 한데 의심
    mapped_diff = 0        # mapped_unit_code != unit_code AND mapped 가 있음

    for doc in docs:
        d = doc.to_dict()
        uc = d.get("unit_code") or ""
        mc = d.get("mapped_unit_code") or ""
        subj = (d.get("subject") or "").strip()
        fname = d.get("file_name") or ""

        if not uc:
            empty_unit += 1
            continue

        if mc and uc != mc:
            mapped_diff += 1

        # 학교급 추정: 파일명 [고]/[중]
        is_high_school = fname.startswith("[고]")
        is_middle_school = fname.startswith("[중]")

        # Z 코드는 중학교 코드. 고 파일에 있으면 이상.
        if uc.startswith("Z") and is_high_school:
            z_in_high.append((doc.id, subj, uc, fname[:80]))

        # subject ↔ unit_code 접두사 일관성
        if subj in SUBJECT_EXPECTED:
            expected = SUBJECT_EXPECTED[subj]
            prefix = uc[0] if uc else ""
            if prefix and prefix not in expected and not uc.startswith("Z"):
                inconsistent.append((doc.id, subj, uc, expected, fname[:80]))

    print(f"[1] subject ↔ unit_code 불일치: {len(inconsistent)}건")
    if inconsistent:
        # subject별로 패턴 집계
        by_pattern = Counter()
        for _, subj, uc, expected, _ in inconsistent:
            by_pattern[(subj, uc[0] if uc else "")] += 1
        print(f"  패턴 (subject, 잘못된 접두사):")
        for (subj, p), n in by_pattern.most_common(10):
            exp = SUBJECT_EXPECTED.get(subj, set())
            print(f"    {subj} subject 에 '{p}' 코드 = {n}건  (정상: {sorted(exp)})")
        print(f"  샘플 5건:")
        for doc_id, subj, uc, expected, fname in inconsistent[:5]:
            print(f"    {doc_id[:50]}: subject='{subj}', unit_code='{uc}' (정상: {sorted(expected)})")
            print(f"      file: {fname}")

    print(f"\n[2] unit_code 빈값: {empty_unit}건")

    print(f"\n[3] [고] 파일에 Z 코드 (중학교 코드): {len(z_in_high)}건")
    if z_in_high:
        for doc_id, subj, uc, fname in z_in_high[:5]:
            print(f"    {doc_id[:50]}: {uc}, subject='{subj}'")
            print(f"      file: {fname}")

    print(f"\n[4] mapped_unit_code != unit_code 잔재: {mapped_diff}건")
    print(f"    (2026-05-23 일괄복구 후 0 이어야 정상. 0 아니면 신규 인덱싱에서 또 잘못된 매핑이 적용됨!)")

    # 6. unit_code vs middle_unit / large_unit 정합성 (파생값 어긋남)
    print(f"\n[6] unit_code vs middle_unit / large_unit 정합성")
    mu_mismatch = 0
    lu_mismatch = 0
    mu_samples = []
    for doc in docs:
        d = doc.to_dict()
        uc = d.get("unit_code") or ""
        if not uc:
            continue
        truth = CODE_TRUTH.get(uc)
        if not truth:
            continue
        truth_mu, truth_lu = truth
        cur_mu = d.get("middle_unit") or ""
        cur_lu = d.get("large_unit") or ""
        if cur_mu != truth_mu:
            mu_mismatch += 1
            if len(mu_samples) < 5:
                mu_samples.append((doc.id, uc, cur_mu, truth_mu))
        if cur_lu != truth_lu:
            lu_mismatch += 1
    print(f"  middle_unit 어긋남: {mu_mismatch}건")
    print(f"  large_unit 어긋남: {lu_mismatch}건")
    if mu_samples:
        print(f"  샘플:")
        for did, uc, cur, truth in mu_samples:
            print(f"    {did[:50]}: unit_code='{uc}' middle_unit='{cur}' (정상: '{truth}')")
    if mu_mismatch or lu_mismatch:
        print(f"  → `python backend/fix_middle_unit.py` 같은 일괄 정상화 권장")

    # 5. 캐시 vs Firestore 카운트 비교
    print(f"\n[5] 캐시 vs Firestore 정합성 (Firestore = SSOT)")
    cache_mismatch = 0
    try:
        from server.services.engine import get_engine
        engine = get_engine()
        cache_count_q = "SELECT COUNT(*) FROM problems"
        params = []
        wheres = []
        if source:
            wheres.append("source=?")
            params.append(source)
        if year:
            wheres.append("year=?")
            params.append(year)
        if wheres:
            cache_count_q += " WHERE " + " AND ".join(wheres)
        with engine.cache.connect() as conn:
            cache_count = conn.execute(cache_count_q, params).fetchone()[0]
        fs_count = len(docs)
        diff = abs(fs_count - cache_count)
        print(f"  Firestore: {fs_count}건 / 캐시: {cache_count}건 / 차이: {diff}")
        if diff > 0:
            cache_mismatch = diff
            print(f"  ⚠️  캐시 stale → `python backend/resync_all.py` 권장")
    except Exception as e:
        print(f"  검사 실패: {e}")

    # 종합 등급
    total_issues = len(inconsistent) + len(z_in_high) + mapped_diff + cache_mismatch + mu_mismatch + lu_mismatch
    print(f"\n{'='*60}")
    if total_issues == 0:
        print(f"✅ 정합성 OK (검사 {len(docs)}건 / 빈값 {empty_unit}건)")
    else:
        print(f"⚠️  의심 {total_issues}건 / 빈값 {empty_unit}건 — 위 항목 확인 필요")
    print(f"{'='*60}")
    return total_issues


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="", help="NAESIN_A / NAESIN_N / SUNEUNG_SPECIAL ...")
    parser.add_argument("--year", default="", help="2025 / 2024 ...")
    args = parser.parse_args()
    sys.exit(0 if audit(args.source, args.year) == 0 else 1)
