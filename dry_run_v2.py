#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRY RUN 2차 — subject 변종 추가 정규화 + 변환 실패 시 unit_code 비움 정책.

규칙:
  변환 성공: unit_code/middle_unit/large_unit = 새 코드, curriculum = '2015개정교육과정'
  변환 실패: unit_code/middle_unit/large_unit = '' 비움, curriculum = '2015개정교육과정' (재시도 방지)
  2022 자료: 건드리지 않음
  '2015개정교육과정' (이미 변환): 건드리지 않음
"""
import os, sys, json
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

from mapping_2015_to_2022 import map_unit_code, SUBJECT_NORMALIZE, OLD_SUBJECT_UNIT_MAP

# unit_hierarchy 로드 (새 코드 → 대단원/중단원)
with open("backend/unit_hierarchy.json", encoding="utf-8") as f:
    hier = json.load(f)
code_to_names = {}
for subj in hier.get("2022", []):
    for large in subj.get("large_units", []):
        large_name = large.get("name", "")
        for med in large.get("medium_units", []):
            code_to_names[med["code"]] = (large_name, med.get("name", ""))

# Firestore
KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

print("=" * 100)
print("[DRY RUN v2] subject 변종 정규화 + 실패 시 unit_code 비움")
print("=" * 100)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

stats = {
    "total": 0,
    "skip_new":  0,
    "skip_already": 0,
    "convert_ok": 0,
    "convert_fail_blank": 0,    # 실패라서 비울 자료
    "already_blank": 0,         # 원래도 빈 코드였음
}

case_old_curr = Counter()
convert_pairs = Counter()
fail_categories = Counter()    # 실패 사유 카테고리
fail_samples = defaultdict(list)
subject_normalized = Counter()   # 변종 정규화로 구제된 케이스

# 변환 결과 샘플
samples = defaultdict(list)

print("\n[1] 스트림 시작...")
for doc in q.stream():
    d = doc.to_dict()
    stats["total"] += 1

    cur = d.get("curriculum", "")
    subj = d.get("subject", "")
    uc = d.get("unit_code", "") or ""
    fname = d.get("file_name", "")
    endnote = d.get("endnote_index", "?")

    # 2022 자료는 건드리지 않음
    if "2022" in cur:
        stats["skip_new"] += 1
        continue

    # 이미 변환된 자료
    if cur == "2015개정교육과정":
        stats["skip_already"] += 1
        continue

    case_old_curr[cur] += 1

    # 변종 정규화 추적
    if subj in SUBJECT_NORMALIZE:
        subject_normalized[(subj, SUBJECT_NORMALIZE[subj])] += 1

    new_subj, new_code = map_unit_code(subj, uc)

    if new_subj and new_code:
        stats["convert_ok"] += 1
        convert_pairs[(subj, uc, new_subj, new_code)] += 1
        key = (subj, uc, new_subj, new_code)
        if len(samples[key]) < 1:
            large, mid = code_to_names.get(new_code, ("?", "?"))
            samples[key].append({
                "file": fname[:60],
                "endnote": endnote,
                "old": (subj, uc),
                "new": (new_subj, new_code, large, mid),
            })
    else:
        # 실패 — 사유 분류
        if not uc:
            stats["already_blank"] += 1
            fail_categories["빈 unit_code (원래도 비어있음)"] += 1
        elif not subj:
            stats["convert_fail_blank"] += 1
            fail_categories["빈 subject"] += 1
        elif subj not in OLD_SUBJECT_UNIT_MAP and SUBJECT_NORMALIZE.get(subj) not in OLD_SUBJECT_UNIT_MAP and subj != "대수":
            stats["convert_fail_blank"] += 1
            fail_categories[f"subject '{subj}' 매핑 없음"] += 1
        else:
            stats["convert_fail_blank"] += 1
            fail_categories[f"unit_code '{uc}' 매핑 없음 (subject={subj})"] += 1
            if len(fail_samples[(subj, uc)]) < 3:
                fail_samples[(subj, uc)].append((fname[:60], endnote))

# ─────────────────────────────────────────
print("\n" + "=" * 100)
print("[결과 요약]")
print("=" * 100)
print(f"  총 NAESIN_A: {stats['total']}건")
print(f"")
print(f"  ⏸ 건드리지 않음:")
print(f"    2022 자료: {stats['skip_new']}건")
print(f"    이미 변환됨 (2015개정교육과정): {stats['skip_already']}건")
print(f"")
print(f"  ✅ 변환 성공 (새 unit_code + curriculum '2015개정교육과정'): {stats['convert_ok']}건")
print(f"  🔲 변환 실패 → unit_code 비움 (curriculum도 '2015개정교육과정'): {stats['convert_fail_blank']}건")
print(f"  ⚪ 원래도 빈 unit_code → 그대로 빈 채로 (curriculum만 통일): {stats['already_blank']}건")
print(f"")
print(f"  → 총 갱신 예정: {stats['convert_ok'] + stats['convert_fail_blank'] + stats['already_blank']}건")

# 변종 정규화 구제 케이스
if subject_normalized:
    print("\n  [subject 변종 정규화 구제]")
    for (orig, norm), cnt in subject_normalized.most_common():
        print(f"    '{orig}' → '{norm}': {cnt}건")

# ─────────────────────────────────────────
print("\n" + "=" * 100)
print(f"[실패 사유별 분포] 총 {stats['convert_fail_blank'] + stats['already_blank']}건")
print("=" * 100)
for cat, cnt in fail_categories.most_common():
    print(f"  {cat}: {cnt}건")

# ─────────────────────────────────────────
print("\n" + "=" * 100)
print(f"[실패 샘플 — 코드 비움 처리될 것들]")
print("=" * 100)

# 상위 실패 케이스 샘플
top_fails = sorted(fail_samples.items(), key=lambda x: -len(x[1]))[:15]
for (s, c), samples_list in top_fails:
    print(f"\n  ({s}, '{c}'): {len(samples_list)}건 샘플")
    for fname, end in samples_list[:2]:
        print(f"    · 문제{end}: {fname}")

# ─────────────────────────────────────────
print("\n" + "=" * 100)
print(f"[변환 매핑 상위 30개]")
print("=" * 100)
print(f"  {'옛subject':<14} {'옛코드':<6} →  {'새subject':<14} {'새코드':<6}  {'대단원':<14} {'중단원':<22} 건수")
print("  " + "-" * 110)
for (osubj, ocode, nsubj, ncode), cnt in sorted(convert_pairs.items(), key=lambda x: -x[1])[:30]:
    large, mid = code_to_names.get(ncode, ("?", "?"))
    print(f"  {osubj:<14} {ocode:<6} →  {nsubj:<14} {ncode:<6}  {large:<14} {mid[:22]:<22} {cnt}건")

# 결과 저장
output = {
    "stats": stats,
    "fail_categories": dict(fail_categories),
    "subject_normalized_counts": {f"{k[0]}|->|{k[1]}": v for k, v in subject_normalized.items()},
    "conversion_pairs_top": {f"{k[0]}|{k[1]}|->|{k[2]}|{k[3]}": v for k, v in sorted(convert_pairs.items(), key=lambda x:-x[1])[:80]},
}
with open("dry_run_v2_result.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  → 결과 저장: dry_run_v2_result.json")
