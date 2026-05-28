#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""변환 직후 Firestore 검증."""
import os, sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

print("=" * 90)
print("[변환 직후 검증]")
print("=" * 90)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

total = 0
curr_cnt = Counter()
subj_curr = defaultdict(Counter)
empty_uc = Counter()      # 빈 unit_code 분포
uc_dist_new = Counter()   # 새 unit_code 분포 (전체)

# '경우의수' 검색 — 옛 잔재 있나
keyword_results = {
    "C1_경우의수": [],   # 새 C1 = 경우의수, 옛 자료 잔재면 노이즈
    "E1_점과좌표": [],   # 새 E1 = 점과 좌표
    "M1_부정적분": [],   # 새 M1 = 부정적분
    "K1_함수의극한": [], # 새 K1 = 함수의 극한
}

for doc in q.stream():
    d = doc.to_dict()
    total += 1
    cur = d.get("curriculum", "") or "(빈)"
    s = d.get("subject", "") or "(빈)"
    uc = d.get("unit_code", "") or ""
    mid = d.get("middle_unit", "") or ""

    curr_cnt[cur] += 1
    subj_curr[s][cur] += 1
    if not uc:
        empty_uc[s] += 1
    uc_dist_new[uc or "(빈)"] += 1

    # 단원별 샘플 5건만
    if uc == "C1" and len(keyword_results["C1_경우의수"]) < 8:
        keyword_results["C1_경우의수"].append((s, mid, d.get("file_name", "")[:50]))
    if uc == "E1" and len(keyword_results["E1_점과좌표"]) < 8:
        keyword_results["E1_점과좌표"].append((s, mid, d.get("file_name", "")[:50]))
    if uc == "M1" and len(keyword_results["M1_부정적분"]) < 8:
        keyword_results["M1_부정적분"].append((s, mid, d.get("file_name", "")[:50]))
    if uc == "K1" and len(keyword_results["K1_함수의극한"]) < 8:
        keyword_results["K1_함수의극한"].append((s, mid, d.get("file_name", "")[:50]))

print(f"\n[1] 총 {total}건")

# curriculum 분포
print("\n[2] curriculum 분포 (변환 후)")
for cur, cnt in curr_cnt.most_common():
    print(f"    '{cur}': {cnt}건")

# subject × curriculum
print("\n[3] subject × curriculum")
for s in sorted(subj_curr.keys()):
    print(f"\n    '{s}'")
    for cur, cnt in subj_curr[s].most_common():
        print(f"      curriculum='{cur}': {cnt}건")

# 빈 unit_code 분포
print("\n[4] 빈 unit_code 분포 (subject별)")
for s, cnt in empty_uc.most_common():
    print(f"    '{s}': {cnt}건")

# unit_code 분포 상위 30
print("\n[5] unit_code 분포 상위 30")
for uc, cnt in uc_dist_new.most_common(30):
    print(f"    {uc}: {cnt}건")

# 단원 키워드 검증
print("\n[6] 핵심 단원 샘플 — 옛 자료 노이즈 없는지 확인")
for key, samples in keyword_results.items():
    print(f"\n  ▶ unit_code={key} 샘플 (최대 8건):")
    for s, mid, fname in samples:
        marker = "  ⚠" if (key.startswith("C1") and ("도형" in fname or "좌표" in mid)) else "  ✓"
        print(f"  {marker} subject={s:<14} middle={mid:<22} | {fname}")

print("\n" + "=" * 90)
print("[검증 완료]")
print("=" * 90)
