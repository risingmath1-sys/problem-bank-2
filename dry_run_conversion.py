#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRY RUN — 변환 대상 식별 + 결과 미리보기.
Firestore 는 절대 수정하지 않음. 결과만 출력.
"""
import os, sys, json
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# 매핑 import
from mapping_2015_to_2022 import OLD_SUBJECT_UNIT_MAP, normalize_subject, map_unit_code

# unit_hierarchy 로드 (새 코드 → 대단원/중단원)
with open("backend/unit_hierarchy.json", encoding="utf-8") as f:
    hier = json.load(f)

code_to_names = {}  # {new_code: (large_name, middle_name)}
for subj in hier.get("2022", []):
    for large in subj.get("large_units", []):
        large_name = large.get("name", "")
        for med in large.get("medium_units", []):
            code = med["code"]
            mname = med.get("name", "")
            code_to_names[code] = (large_name, mname)

# Firestore 연결
KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

print("=" * 100)
print("[DRY RUN] NAESIN_A 변환 시뮬레이션 (Firestore 수정 안 함)")
print("=" * 100)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

stats = {
    "total": 0,
    "skip_new":  0,    # 2022 자료, 변환 안 함
    "skip_already": 0, # 2015개정교육과정 (이미 변환됨)
    "convert_ok": 0,
    "convert_fail": 0,
    "empty_subject": 0,
}

# 케이스별 카운터
case_old_curr = Counter()         # curriculum별
convert_pairs = Counter()         # (old_subject, old_code) → (new_subject, new_code) 카운트
fail_pairs = Counter()            # 변환 실패 (subject, code)
empty_subject_codes = Counter()   # 빈 subject의 unit_code 분포

# 변환 결과 샘플 (각 케이스 2건씩)
samples = defaultdict(list)

print("\n[1] 스트림 시작...")
for doc in q.stream():
    d = doc.to_dict()
    stats["total"] += 1

    cur = d.get("curriculum", "")
    subj = d.get("subject", "")
    uc = d.get("unit_code", "")
    fname = d.get("file_name", "")

    # 2022 자료는 건드리지 않음
    if "2022" in cur:
        stats["skip_new"] += 1
        continue

    # 이미 변환된 자료 (2015개정교육과정) — 건드리지 않음
    if cur == "2015개정교육과정":
        stats["skip_already"] += 1
        continue

    # curriculum 이 "2015교육과정" 인 자료가 변환 대상
    case_old_curr[cur] += 1

    if not subj:
        stats["empty_subject"] += 1
        empty_subject_codes[uc or "(빈)"] += 1
        # file_name 으로 추정 시도 — 일단 별도 처리
        continue

    new_subj, new_code = map_unit_code(subj, uc)
    if new_subj and new_code:
        stats["convert_ok"] += 1
        convert_pairs[(subj, uc, new_subj, new_code)] += 1

        # 샘플 5건만 저장
        key = (subj, uc, new_subj, new_code)
        if len(samples[key]) < 2:
            large, mid = code_to_names.get(new_code, ("?", "?"))
            samples[key].append({
                "file": fname[:60],
                "old": (subj, uc),
                "new": (new_subj, new_code, large, mid),
            })
    else:
        stats["convert_fail"] += 1
        fail_pairs[(subj, uc)] += 1

# ─────────────────────────────────────────
print("\n" + "=" * 100)
print("[결과 요약]")
print("=" * 100)
print(f"  총 NAESIN_A: {stats['total']}건")
print(f"    2022 자료 (건드리지 않음): {stats['skip_new']}건")
print(f"    이미 변환됨 (2015개정교육과정): {stats['skip_already']}건")
print(f"    변환 성공: {stats['convert_ok']}건  ✅")
print(f"    변환 실패: {stats['convert_fail']}건  ❌")
print(f"    빈 subject: {stats['empty_subject']}건  ⚠")

print("\n  [변환 대상 curriculum 표기]")
for cur, cnt in case_old_curr.most_common():
    print(f"    '{cur}': {cnt}건")

# 변환 매핑별 카운트
print("\n" + "=" * 100)
print("[변환 매핑별 카운트] (옛subject, 옛코드) → (새subject, 새코드)")
print("=" * 100)
print(f"  {'옛subject':<14} {'옛코드':<6} →  {'새subject':<14} {'새코드':<6}  {'대단원':<14} {'중단원':<22} 건수")
print("  " + "-" * 110)
for (osubj, ocode, nsubj, ncode), cnt in sorted(convert_pairs.items(), key=lambda x: -x[1]):
    large, mid = code_to_names.get(ncode, ("?", "?"))
    print(f"  {osubj:<14} {ocode:<6} →  {nsubj:<14} {ncode:<6}  {large:<14} {mid[:22]:<22} {cnt}건")

# 변환 실패 케이스
if fail_pairs:
    print("\n" + "=" * 100)
    print("[변환 실패] (옛subject, 옛코드) — 매핑표에 없음")
    print("=" * 100)
    for (s, c), cnt in fail_pairs.most_common():
        print(f"  ({s}, {c}): {cnt}건")

# 빈 subject
if empty_subject_codes:
    print("\n" + "=" * 100)
    print("[빈 subject] unit_code 분포 — 후속 추정 처리 필요")
    print("=" * 100)
    for uc, cnt in empty_subject_codes.most_common():
        print(f"  {uc}: {cnt}건")

# 샘플 출력 (변환 매핑별 2건씩)
print("\n" + "=" * 100)
print("[샘플] 변환 매핑별 첫 2건 (총 {}개 매핑 케이스 중 상위 10개)".format(len(samples)))
print("=" * 100)

top_keys = sorted(convert_pairs.keys(), key=lambda k: -convert_pairs[k])[:10]
for key in top_keys:
    osubj, ocode, nsubj, ncode = key
    print(f"\n  ▶ ({osubj}, {ocode}) → ({nsubj}, {ncode})  [총 {convert_pairs[key]}건]")
    for s in samples[key]:
        old = s["old"]
        new = s["new"]
        print(f"     · {s['file']}")
        print(f"       OLD: subject='{old[0]}', unit_code='{old[1]}'")
        print(f"       NEW: subject='{new[0]}', unit_code='{new[1]}', large='{new[2]}', middle='{new[3]}'")

# 결과 저장
output = {
    "stats": stats,
    "curriculum_old_dist": dict(case_old_curr),
    "conversion_pairs": {f"{k[0]}|{k[1]}|->|{k[2]}|{k[3]}": v for k, v in convert_pairs.items()},
    "failed_pairs": {f"{k[0]}|{k[1]}": v for k, v in fail_pairs.items()},
    "empty_subject_codes": dict(empty_subject_codes),
}
with open("dry_run_result.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  → 결과 저장: dry_run_result.json")
