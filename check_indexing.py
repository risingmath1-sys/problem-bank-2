#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from pathlib import Path

db_path = "problem_bank.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 내신기출A 폴더 경로
base_path = Path("G:/문제은행/문제들/10내신기출A")

# 각 폴더의 파일 목록
folders = sorted([d for d in base_path.iterdir() if d.is_dir()])

print("=" * 100)
print("[내신기출A 폴더별 인덱싱 현황]")
print("=" * 100)

unindexed_folders = []
total_files = 0
total_indexed = 0

for folder in folders:
    folder_name = folder.name

    # 폴더의 모든 HWP 파일
    hwp_files = list(folder.glob("**/*.hwp")) + list(folder.glob("**/*.hwpx"))
    file_count = len(hwp_files)

    # DB에서 해당 파일명들의 인덱싱 건수 조회
    indexed_count = 0
    file_names = [f.name for f in hwp_files]

    if file_names:
        # source = 'NAESIN_A'이고 file_name이 해당 파일 중 하나인 레코드 개수
        for file_name in file_names:
            cursor.execute(
                "SELECT COUNT(*) FROM problems WHERE file_name = ? AND source = 'NAESIN_A'",
                (file_name,)
            )
            count = cursor.fetchone()[0]
            if count > 0:
                indexed_count += 1

    total_files += file_count
    total_indexed += indexed_count

    # 상태 표시
    if file_count > 0:
        percentage = (indexed_count / file_count) * 100
        if indexed_count == 0:
            status = "[NOT INDEXED]"
            unindexed_folders.append(folder_name)
        elif percentage < 50:
            status = "[{:.0f}%]".format(percentage)
        else:
            status = "[{:.0f}%]".format(percentage)
    else:
        status = "[EMPTY]"

    print("{}: {} files, {} indexed {}".format(folder_name, file_count, indexed_count, status))

print("=" * 100)
print("TOTAL: {} files, {} indexed ({:.1f}%)".format(total_files, total_indexed, (total_indexed/total_files*100)))
print("=" * 100)

if unindexed_folders:
    print("\n[UNINDEXED FOLDERS - 0% (통채로 빈 것)]:")
    for f in unindexed_folders:
        print("  - {}".format(f))
else:
    print("\n모든 폴더가 인덱싱되어 있습니다.")

conn.close()
