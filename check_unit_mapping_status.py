#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

cache_path = os.path.join(os.environ.get("APPDATA", ""), "naegiwangbank", "problems_cache.sqlite")
print(f"DB: {cache_path}\n")

conn = sqlite3.connect(cache_path)
cursor = conn.cursor()

# 1. 전체 unit_code 빈값 현황
print("=" * 80)
print("[1] 소스별 unit_code 빈값 현황")
print("=" * 80)

cursor.execute("""
    SELECT source,
           COUNT(*) as total,
           SUM(CASE WHEN unit_code IS NULL OR unit_code = '' THEN 1 ELSE 0 END) as empty
    FROM problems
    GROUP BY source
    ORDER BY source
""")
for row in cursor.fetchall():
    src, total, empty = row
    print(f"  {src}: 총 {total}건 / unit_code 빈값 {empty}건 ({empty/total*100:.1f}%)")

# 2. middle_unit / large_unit 빈값
print("\n" + "=" * 80)
print("[2] middle_unit / large_unit 빈값 현황")
print("=" * 80)

cursor.execute("""
    SELECT source,
           SUM(CASE WHEN middle_unit IS NULL OR middle_unit = '' THEN 1 ELSE 0 END) as mid_empty,
           SUM(CASE WHEN large_unit IS NULL OR large_unit = '' THEN 1 ELSE 0 END) as large_empty,
           COUNT(*) as total
    FROM problems
    GROUP BY source
    ORDER BY source
""")
for row in cursor.fetchall():
    src, mid, large, total = row
    print(f"  {src}: middle 빈값 {mid}/{total} | large 빈값 {large}/{total}")

# 3. unit_code 와 middle_unit/large_unit 매칭 안 되는 경우
print("\n" + "=" * 80)
print("[3] unit_code 있는데 middle/large 비어있음 — 매핑 누락")
print("=" * 80)

cursor.execute("""
    SELECT source, COUNT(*) as cnt
    FROM problems
    WHERE unit_code IS NOT NULL AND unit_code != ''
      AND (middle_unit IS NULL OR middle_unit = ''
           OR large_unit IS NULL OR large_unit = '')
    GROUP BY source
    ORDER BY cnt DESC
""")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"  {row[0]}: {row[1]}건")
else:
    print("  (없음)")

# 4. unit_code 별 분포 (NAESIN_A, NAESIN_N) — 비정상 코드 탐지
print("\n" + "=" * 80)
print("[4] unit_code 분포 (NAESIN_A + NAESIN_N) — 빈도순")
print("=" * 80)

cursor.execute("""
    SELECT unit_code, COUNT(*) as cnt
    FROM problems
    WHERE source IN ('NAESIN_A', 'NAESIN_N')
    GROUP BY unit_code
    ORDER BY cnt DESC
    LIMIT 50
""")
for row in cursor.fetchall():
    uc = row[0] or "(빈값)"
    print(f"  {uc}: {row[1]}건")

# 5. 의심: unit_code 형식이 이상한 것 (정상 패턴: [A-Z][0-9])
print("\n" + "=" * 80)
print("[5] 비정상 unit_code (정상 패턴이 아닌 것)")
print("=" * 80)

cursor.execute("""
    SELECT unit_code, source, COUNT(*) as cnt
    FROM problems
    WHERE unit_code IS NOT NULL AND unit_code != ''
      AND unit_code NOT GLOB '[A-Z][0-9]'
      AND unit_code NOT GLOB '[A-Z][0-9][0-9]'
    GROUP BY unit_code, source
    ORDER BY cnt DESC
    LIMIT 30
""")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"  '{row[0]}' [{row[1]}]: {row[2]}건")
else:
    print("  (없음)")

# 6. middle_unit 값 종류 (이상 값 탐지)
print("\n" + "=" * 80)
print("[6] middle_unit unique 값 (NAESIN_A + NAESIN_N) — 빈도순 상위 30")
print("=" * 80)

cursor.execute("""
    SELECT middle_unit, COUNT(*) as cnt
    FROM problems
    WHERE source IN ('NAESIN_A', 'NAESIN_N')
      AND middle_unit IS NOT NULL AND middle_unit != ''
    GROUP BY middle_unit
    ORDER BY cnt DESC
    LIMIT 30
""")
for row in cursor.fetchall():
    print(f"  '{row[0]}': {row[1]}건")

conn.close()
