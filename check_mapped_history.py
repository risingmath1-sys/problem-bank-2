#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

cache_path = os.path.join(os.environ.get("APPDATA", ""), "naegiwangbank", "problems_cache.sqlite")
print(f"DB: {cache_path}\n")

conn = sqlite3.connect(f"file:{cache_path}?mode=ro", uri=True)
cursor = conn.cursor()

# 1. mapped_unit_code 컬럼이 존재하는지 + 값 분포
print("=" * 90)
print("[1] mapped_unit_code 분포 (source별)")
print("=" * 90)

cursor.execute("""
    SELECT source,
           COUNT(*) as total,
           SUM(CASE WHEN mapped_unit_code IS NULL OR mapped_unit_code = '' THEN 1 ELSE 0 END) as empty,
           SUM(CASE WHEN mapped_unit_code IS NOT NULL AND mapped_unit_code != '' THEN 1 ELSE 0 END) as filled
    FROM problems
    GROUP BY source
    ORDER BY source
""")
for row in cursor.fetchall():
    src, total, empty, filled = row
    pct = filled/total*100 if total else 0
    print(f"  {src}: 총 {total}건 | mapped_unit_code 채워진 것 {filled}건 ({pct:.1f}%) | 빈 것 {empty}건")

# 2. mapped_unit_code 값들의 분포 (NAESIN_A + NAESIN_N, 채워진 것만)
print("\n" + "=" * 90)
print("[2] mapped_unit_code 값 분포 (NAESIN_A + NAESIN_N, 채워진 것)")
print("=" * 90)

cursor.execute("""
    SELECT mapped_unit_code, COUNT(*) as cnt
    FROM problems
    WHERE source IN ('NAESIN_A', 'NAESIN_N')
      AND mapped_unit_code IS NOT NULL AND mapped_unit_code != ''
    GROUP BY mapped_unit_code
    ORDER BY cnt DESC
    LIMIT 40
""")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"  '{row[0]}': {row[1]}건")
else:
    print("  (mapped_unit_code 채워진 레코드 없음)")

# 3. NAESIN_A — curriculum + unit_code 매트릭스 (어느 교과정의 자료가 어떤 코드로 들어가있는가)
print("\n" + "=" * 90)
print("[3] NAESIN_A — curriculum별 unit_code 분포 (상위 20)")
print("=" * 90)

cursor.execute("""
    SELECT curriculum, COUNT(*) as cnt
    FROM problems
    WHERE source = 'NAESIN_A'
    GROUP BY curriculum
    ORDER BY cnt DESC
""")
for row in cursor.fetchall():
    print(f"  curriculum='{row[0]}': {row[1]}건")

# 4. NAESIN_A — 2015 시기(year - grade < 2024)와 2022 시기 자료의 unit_code 분포 차이
print("\n" + "=" * 90)
print("[4] NAESIN_A — 2015 시기(year<2024 또는 year-grade<2024) 자료의 unit_code 분포")
print("=" * 90)
print("    [기준: year=2020, 즉 확실한 2015 시기 자료]")
print()

cursor.execute("""
    SELECT unit_code, COUNT(*) as cnt
    FROM problems
    WHERE source = 'NAESIN_A' AND year = '2020'
    GROUP BY unit_code
    ORDER BY cnt DESC
    LIMIT 30
""")
for row in cursor.fetchall():
    uc = row[0] or "(빈값)"
    print(f"  {uc}: {row[1]}건")

# 5. NAESIN_A year별 unit_code 분포 — 코드 변동 추이
print("\n" + "=" * 90)
print("[5] NAESIN_A — year별 unit_code 'C1'~'C4' 분포 (도형의 방정식 vs 경우의수 충돌 영역)")
print("=" * 90)
print()

cursor.execute("""
    SELECT year, unit_code, COUNT(*) as cnt
    FROM problems
    WHERE source = 'NAESIN_A' AND unit_code IN ('C1','C2','C3','C4','E1','E2','E3','E4')
    GROUP BY year, unit_code
    ORDER BY year, unit_code
""")
rows = cursor.fetchall()
by_year = {}
for year, uc, cnt in rows:
    by_year.setdefault(year, {})[uc] = cnt

print(f"  {'year':<6} | {'C1':<5} {'C2':<5} {'C3':<5} {'C4':<5} | {'E1':<5} {'E2':<5} {'E3':<5} {'E4':<5}")
print("  " + "-" * 78)
for year in sorted(by_year.keys()):
    d = by_year[year]
    print(f"  {year:<6} | {d.get('C1',0):<5} {d.get('C2',0):<5} {d.get('C3',0):<5} {d.get('C4',0):<5} | "
          f"{d.get('E1',0):<5} {d.get('E2',0):<5} {d.get('E3',0):<5} {d.get('E4',0):<5}")

# 6. mapped_unit_code 값이 있는 샘플 확인 (있다면 그게 5-23 이전 흔적)
print("\n" + "=" * 90)
print("[6] mapped_unit_code 값이 있는 샘플 5개 (5-23 이전 변환 흔적)")
print("=" * 90)

cursor.execute("""
    SELECT file_name, year, grade, subject, curriculum, unit_code, mapped_unit_code, indexed_at
    FROM problems
    WHERE mapped_unit_code IS NOT NULL AND mapped_unit_code != ''
    LIMIT 10
""")
rows = cursor.fetchall()
if rows:
    for r in rows:
        ts = datetime.fromtimestamp(r[7]).strftime("%Y-%m-%d") if r[7] else "?"
        print(f"  {r[0][:50]:<50} | y={r[1]} g={r[2]} | uc={r[5]} mapped={r[6]} | indexed={ts}")
else:
    print("  (mapped_unit_code가 채워진 레코드 0건)")

# 7. NAESIN_A — indexed_at 별 mapped_unit_code 분포
print("\n" + "=" * 90)
print("[7] NAESIN_A indexed_at 월별 — mapped_unit_code 채워진 비율")
print("=" * 90)

cursor.execute("""
    SELECT strftime('%Y-%m', datetime(indexed_at, 'unixepoch')) as ym,
           COUNT(*) as total,
           SUM(CASE WHEN mapped_unit_code IS NOT NULL AND mapped_unit_code != '' THEN 1 ELSE 0 END) as filled
    FROM problems
    WHERE source = 'NAESIN_A' AND indexed_at IS NOT NULL
    GROUP BY ym
    ORDER BY ym
""")
for row in cursor.fetchall():
    ym, total, filled = row
    pct = filled/total*100 if total else 0
    print(f"  {ym}: 총 {total}건 / mapped 채워진 것 {filled}건 ({pct:.1f}%)")

conn.close()
