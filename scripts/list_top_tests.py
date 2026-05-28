"""12점 이상 (최상) 시험지 리스트."""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = sqlite3.connect("problem_bank.db")
cur = conn.cursor()
cur.execute("""
    SELECT file_name, source, school, year,
        SUM(CASE WHEN difficulty='A' THEN 2 WHEN difficulty='B' THEN 1 ELSE 0 END) AS adv_score,
        COUNT(*) AS n
    FROM problems
    WHERE source IN ('NAESIN_A', 'NAESIN_N')
      AND grade IN ('고1', '고2', '고3')
    GROUP BY file_name
    HAVING adv_score >= 12
    ORDER BY adv_score DESC
""")
rows = cur.fetchall()

print(f"[최상 {len(rows)}건 — 12점 이상]")
print()
for fn, src, school, year, score, n in rows:
    src_tag = "A" if src == "NAESIN_A" else "B"
    print(f"  [{src_tag}] {score:>3}점 ({n:>2}문항)  {(school or '-'):>10}  {year or '-':>4}  {fn}")
