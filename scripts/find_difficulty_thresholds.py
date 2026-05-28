"""NAESIN_A + NAESIN_N (내신기출A+B) 고등 시험지 전수조사로 상위 10/30/60% 경계 산출.
시험지 점수 = (A난이도 × 2) + (B난이도 × 1).
"""
import sqlite3
import os
import sys
from statistics import median

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "problem_bank.db"


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB 없음: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # NAESIN_A + NAESIN_N 합쳐 / 고등만 / file_name 별 adv_score 합산
    cur.execute("""
        SELECT
            file_name,
            source,
            SUM(CASE WHEN difficulty='A' THEN 2
                     WHEN difficulty='B' THEN 1 ELSE 0 END) AS adv_score,
            COUNT(*) AS n_problems
        FROM problems
        WHERE source IN ('NAESIN_A', 'NAESIN_N')
          AND grade IN ('고1', '고2', '고3')
        GROUP BY file_name
        ORDER BY adv_score DESC
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("[ERROR] 해당 조건의 시험지 없음")
        return

    n = len(rows)
    scores = [r[2] or 0 for r in rows]

    # 소스별 통계
    src_counts = {"NAESIN_A": 0, "NAESIN_N": 0}
    for _fn, src, _s, _np in rows:
        src_counts[src] = src_counts.get(src, 0) + 1

    print("=" * 78)
    print("[NAESIN_A + NAESIN_N 고등 시험지 전수조사]")
    print("=" * 78)
    print(f"  총 시험지 수: {n:,}")
    print(f"    - NAESIN_A: {src_counts['NAESIN_A']:,}")
    print(f"    - NAESIN_N: {src_counts['NAESIN_N']:,}")
    print(f"  점수 분포:")
    print(f"    최댓값: {max(scores)}")
    print(f"    중앙값: {median(scores)}")
    print(f"    최솟값: {min(scores)}")
    print(f"    평균   : {sum(scores)/n:.2f}")
    print()

    # 경계선 계산 — DESC 정렬이라 index 가 작을수록 높은 점수
    def _score_at(pct):
        idx = max(0, min(n - 1, int(n * pct) - 1))
        return scores[idx]

    th10 = _score_at(0.10)
    th30 = _score_at(0.30)
    th60 = _score_at(0.60)

    print("=" * 78)
    print("[경계선]")
    print("=" * 78)
    print(f"  상위 10% 경계 (th10): {th10}점 이상 → 최상")
    print(f"  상위 30% 경계 (th30): {th30}점 이상 → 상")
    print(f"  상위 60% 경계 (th60): {th60}점 이상 → 중")
    print(f"                       나머지       → 하")
    print()

    # 검증: 각 구간에 몇 개씩 들어가나
    cnt = {"최상": 0, "상": 0, "중": 0, "하": 0}
    for s in scores:
        if s >= th10:
            cnt["최상"] += 1
        elif s >= th30:
            cnt["상"] += 1
        elif s >= th60:
            cnt["중"] += 1
        else:
            cnt["하"] += 1
    print("[구간별 시험지 수]")
    for k, v in cnt.items():
        print(f"  {k}: {v:,}건 ({v/n*100:.1f}%)")
    print()

    # 점수 분포 히스토그램 (요약)
    print("[점수 히스토그램 (10점 단위)]")
    buckets = {}
    for s in scores:
        b = (s // 10) * 10
        buckets[b] = buckets.get(b, 0) + 1
    for b in sorted(buckets.keys(), reverse=True):
        bar = "#" * min(60, buckets[b])
        print(f"  {b:>3}+: {buckets[b]:>4}  {bar}")


if __name__ == "__main__":
    main()
