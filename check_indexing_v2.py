#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# 서버가 실제로 보는 캐시 DB
cache_path = os.path.join(os.environ.get("APPDATA", ""), "naegiwangbank", "problems_cache.sqlite")
print(f"DB: {cache_path}")

conn = sqlite3.connect(cache_path)
cursor = conn.cursor()

base_path = Path("G:/문제은행/문제들/10내신기출A")
folders = sorted([d for d in base_path.iterdir() if d.is_dir()])

print("=" * 100)
print("[내신기출A 폴더별 인덱싱 현황 — 캐시 DB 기준]")
print("=" * 100)

unindexed_folders = []
partial_folders = []
total_files = 0
total_indexed = 0

for folder in folders:
    folder_name = folder.name
    hwp_files = list(folder.glob("**/*.hwp")) + list(folder.glob("**/*.hwpx"))
    file_count = len(hwp_files)

    indexed_count = 0
    for f in hwp_files:
        cursor.execute("SELECT COUNT(*) FROM problems WHERE file_name = ?", (f.name,))
        if cursor.fetchone()[0] > 0:
            indexed_count += 1

    total_files += file_count
    total_indexed += indexed_count

    if file_count > 0:
        pct = (indexed_count / file_count) * 100
        if indexed_count == 0:
            status = "[NOT INDEXED 0%]"
            unindexed_folders.append((folder_name, file_count))
        elif pct < 100:
            status = f"[{pct:.0f}%]"
            partial_folders.append((folder_name, file_count, indexed_count))
        else:
            status = "[100%]"
    else:
        status = "[EMPTY]"

    print(f"{folder_name}")
    print(f"  파일 {file_count}개, 인덱싱 {indexed_count}개  {status}")

print("=" * 100)
print(f"TOTAL: {total_files}개 파일, {total_indexed}개 인덱싱 ({(total_indexed/total_files*100):.1f}%)")
print("=" * 100)

if unindexed_folders:
    print("\n[❌ 통채로 빈 폴더 (0%)]:")
    for name, cnt in unindexed_folders:
        print(f"  - {name} ({cnt}개)")
else:
    print("\n[✓] 통채로 빈 폴더 없음")

if partial_folders:
    print("\n[⚠ 부분 인덱싱 폴더]:")
    for name, cnt, idx in partial_folders:
        miss = cnt - idx
        print(f"  - {name}: {idx}/{cnt} (미인덱싱 {miss}개)")

conn.close()
