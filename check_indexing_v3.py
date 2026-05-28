#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

cache_path = os.path.join(os.environ.get("APPDATA", ""), "naegiwangbank", "problems_cache.sqlite")
print(f"DB: {cache_path}\n")

conn = sqlite3.connect(cache_path)
cursor = conn.cursor()

base_path = Path("G:/문제은행/문제들/10내신기출A")
year_folders = sorted([d for d in base_path.iterdir() if d.is_dir()])

print("=" * 100)
print("[내신기출A — 년도/시험 폴더 안의 과목별 하위 폴더 인덱싱 현황]")
print("=" * 100)

zero_subjects = []   # 통채로 빈 과목 폴더
partial_subjects = []  # 부분 인덱싱 과목 폴더

for year_folder in year_folders:
    year_name = year_folder.name
    # 하위 폴더(과목별) 탐색
    sub_folders = sorted([d for d in year_folder.iterdir() if d.is_dir()])

    if not sub_folders:
        # 하위 폴더가 없으면 폴더 자체를 1단위로
        hwp_files = list(year_folder.glob("*.hwp")) + list(year_folder.glob("*.hwpx"))
        if hwp_files:
            sub_folders = [year_folder]  # 자신을 단일 단위로

    print(f"\n┌─ {year_name}")
    for sub in sub_folders:
        rel = sub.relative_to(base_path)
        hwp_files = list(sub.glob("**/*.hwp")) + list(sub.glob("**/*.hwpx"))
        file_count = len(hwp_files)

        indexed_count = 0
        for f in hwp_files:
            cursor.execute("SELECT COUNT(*) FROM problems WHERE file_name = ?", (f.name,))
            if cursor.fetchone()[0] > 0:
                indexed_count += 1

        if file_count == 0:
            status = "[EMPTY]"
        elif indexed_count == 0:
            status = "[❌ 0%]"
            zero_subjects.append(str(rel))
        else:
            pct = (indexed_count / file_count) * 100
            if pct < 100:
                status = f"[{pct:.0f}%]"
                partial_subjects.append((str(rel), file_count, indexed_count))
            else:
                status = "[100%]"

        print(f"│  └─ {sub.name}: {file_count}개 / 인덱싱 {indexed_count}개 {status}")

print("\n" + "=" * 100)
print("[결과 요약]")
print("=" * 100)

if zero_subjects:
    print(f"\n❌ 통채로 빈 과목 폴더 ({len(zero_subjects)}개):")
    for p in zero_subjects:
        print(f"  - {p}")
else:
    print("\n✓ 통채로 빈 과목 폴더 없음")

if partial_subjects:
    print(f"\n⚠ 부분 인덱싱 과목 폴더 ({len(partial_subjects)}개):")
    # 가장 적게 인덱싱된 것부터
    partial_subjects.sort(key=lambda x: x[2]/x[1] if x[1] else 1)
    for path, cnt, idx in partial_subjects:
        pct = idx/cnt*100
        miss = cnt - idx
        print(f"  - [{pct:.0f}%] {path}: {idx}/{cnt} (미인덱싱 {miss}개)")

conn.close()
