#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# 서버가 실제로 보는 캐시 DB
cache_path = os.path.join(os.environ.get("APPDATA", ""), "naegiwangbank", "problems_cache.sqlite")

print(f"Cache DB path: {cache_path}")
print(f"Exists: {os.path.exists(cache_path)}")

if not os.path.exists(cache_path):
    print("캐시 DB 없음!")
    sys.exit(1)

conn = sqlite3.connect(cache_path)
cursor = conn.cursor()

# 전체 건수
cursor.execute("SELECT COUNT(*) FROM problems")
total = cursor.fetchone()[0]
print(f"\n캐시 DB 총 문제: {total}건")

# 2025-1-1-F 파일 검색
print("\n" + "=" * 80)
print("[2025-1-1-F 파일 검색 (캐시 DB)]")
print("=" * 80)

cursor.execute("""
    SELECT DISTINCT file_name, source, COUNT(*) as cnt
    FROM problems
    WHERE file_name LIKE '%2025-1-1-F%'
    GROUP BY file_name, source
    ORDER BY file_name
""")
rows = cursor.fetchall()
print(f"\n[검색 결과: {len(rows)} 개 파일]")
for row in rows:
    print(f"  {row[0]} | source={row[1]} | {row[2]}문제")

# 104 폴더 모든 파일 매칭
print("\n" + "=" * 80)
print("[104 폴더 파일별 인덱싱 현황 (캐시 DB)]")
print("=" * 80)

base_path = Path("G:/문제은행/문제들/10내신기출A/104-2025년 1학기 기말 학교별")
hwp_files = list(base_path.glob("**/*.hwp")) + list(base_path.glob("**/*.hwpx"))

indexed = 0
not_indexed = 0
for f in sorted(hwp_files):
    cursor.execute("SELECT COUNT(*) FROM problems WHERE file_name = ?", (f.name,))
    cnt = cursor.fetchone()[0]
    if cnt > 0:
        indexed += 1
        print(f"  O {f.name} ({cnt}문제)")
    else:
        not_indexed += 1
        print(f"  X {f.name}")

print(f"\n총 {len(hwp_files)}개 / 인덱싱 {indexed}개 / 미인덱싱 {not_indexed}개")

conn.close()
