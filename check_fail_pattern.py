#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""변환 실패 케이스가 파일 단위인지 문제 단위인지 확인."""
import os, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

from mapping_2015_to_2022 import map_unit_code

KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

# file_name 별로 분류
file_stats = defaultdict(lambda: {"ok":0, "fail":0, "fail_codes": []})

for doc in q.stream():
    d = doc.to_dict()
    cur = d.get("curriculum", "")
    if "2022" in cur or cur == "2015개정교육과정":
        continue

    subj = d.get("subject", "")
    uc = d.get("unit_code", "")
    fname = d.get("file_name", "(?)")
    endnote = d.get("endnote_index", "?")

    if not subj:
        continue

    new_subj, new_code = map_unit_code(subj, uc)
    if new_subj and new_code:
        file_stats[fname]["ok"] += 1
    else:
        file_stats[fname]["fail"] += 1
        file_stats[fname]["fail_codes"].append((endnote, uc))

# 분석
files_all_ok = 0
files_all_fail = 0
files_mixed = 0
fail_only_files = []
mixed_files = []

for fname, st in file_stats.items():
    if st["fail"] == 0:
        files_all_ok += 1
    elif st["ok"] == 0:
        files_all_fail += 1
        fail_only_files.append((fname, st["fail"]))
    else:
        files_mixed += 1
        mixed_files.append((fname, st["ok"], st["fail"], st["fail_codes"][:5]))

print("=" * 90)
print("[변환 실패 패턴 분석]")
print("=" * 90)
print(f"\n  변환 대상 파일 (2015교육과정): {len(file_stats)}개")
print(f"    전부 OK (실패 0): {files_all_ok}개")
print(f"    전부 실패: {files_all_fail}개")
print(f"    섞임 (OK + 실패): {files_mixed}개  ← 같은 파일에 변환 성공/실패가 같이 있는 케이스")

# 섞임 케이스 샘플 10개
print("\n" + "=" * 90)
print(f"[섞임 케이스 샘플 — 변환 OK/실패가 같은 파일에 공존, 총 {files_mixed}개 중 15개]")
print("=" * 90)

# 실패가 적은 순으로 정렬 (1~2개만 실패하는 케이스가 흥미)
mixed_files.sort(key=lambda x: x[2])
for fname, ok, fail, samples in mixed_files[:15]:
    print(f"\n  📄 {fname[:80]}")
    print(f"     변환 OK: {ok}문제 / 실패: {fail}문제")
    print(f"     실패 문제: {[(f'문제{e}', f'코드={c}') for e, c in samples]}")

# 전부 실패 케이스 샘플
print("\n" + "=" * 90)
print(f"[전부 실패 파일 샘플 — 총 {files_all_fail}개 중 10개]")
print("=" * 90)
for fname, n in fail_only_files[:10]:
    print(f"  {n}문제 모두 실패: {fname[:80]}")

# 실패 총 카운트 검증
total_fail = sum(s["fail"] for s in file_stats.values())
print(f"\n  ※ 실패 총 문제 수 = {total_fail}건 (이전 DRY RUN 628과 일치해야)")
