#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firestore NAESIN_A 2015교육과정 자료 일괄 변환.

정책:
  - 변환 성공: unit_code/middle_unit/large_unit = 새 코드, curriculum = '2015개정교육과정'
  - 변환 실패: unit_code/middle_unit/large_unit = '' 비움, curriculum = '2015개정교육과정'
  - subject: 변종 정규화 ('수(하)' → '수학(하)', '대수'+옛코드 → '수학1' 등)
  - mapped_unit_code: 원본 옛 코드 보존 (감사용)
"""
import os, sys, json, time
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

from mapping_2015_to_2022 import map_unit_code, SUBJECT_NORMALIZE

# unit_hierarchy 로드
with open("backend/unit_hierarchy.json", encoding="utf-8") as f:
    hier = json.load(f)
code_to_names = {}
for subj in hier.get("2022", []):
    for large in subj.get("large_units", []):
        for med in large.get("medium_units", []):
            code_to_names[med["code"]] = (large.get("name", ""), med.get("name", ""))

KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

print("=" * 80)
print("[Firestore 일괄 변환 실행]")
print("=" * 80)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

# 1단계: 변환 대상과 업데이트 내용 모으기 (메모리에)
updates = []  # [(doc_id, update_dict), ...]
stats = {
    "scanned": 0,
    "skip_2022": 0,
    "skip_already": 0,
    "convert_ok": 0,
    "convert_fail_blank": 0,
    "already_blank": 0,
}

print("\n[1단계] 변환 대상 식별 및 업데이트 계획 작성...")
for doc in q.stream():
    d = doc.to_dict()
    stats["scanned"] += 1
    cur = d.get("curriculum", "")

    if "2022" in cur:
        stats["skip_2022"] += 1
        continue
    if cur == "2015개정교육과정":
        stats["skip_already"] += 1
        continue

    subj = d.get("subject", "")
    uc = d.get("unit_code", "") or ""
    norm_subj = SUBJECT_NORMALIZE.get(subj, subj)

    new_subj, new_code = map_unit_code(subj, uc)

    if new_subj and new_code:
        # 변환 성공
        large, mid = code_to_names.get(new_code, ("", ""))
        update = {
            "subject": new_subj,
            "unit_code": new_code,
            "large_unit": large,
            "middle_unit": mid,
            "mapped_unit_code": uc,   # 원본 옛 코드 보존
            "curriculum": "2015개정교육과정",
        }
        stats["convert_ok"] += 1
    else:
        # 변환 실패
        if not uc:
            stats["already_blank"] += 1
        else:
            stats["convert_fail_blank"] += 1

        update = {
            "subject": norm_subj,   # subject만 정규화
            "unit_code": "",
            "large_unit": "",
            "middle_unit": "",
            "mapped_unit_code": uc,
            "curriculum": "2015개정교육과정",
        }

    updates.append((doc.id, update))

    if stats["scanned"] % 3000 == 0:
        print(f"    ... 스캔 {stats['scanned']}건")

print(f"\n  스캔 완료:")
print(f"    - 총 {stats['scanned']}건")
print(f"    - 2022 자료 보존: {stats['skip_2022']}")
print(f"    - 이미 변환됨 보존: {stats['skip_already']}")
print(f"    - 변환 성공: {stats['convert_ok']}")
print(f"    - 변환 실패 → 비움: {stats['convert_fail_blank']}")
print(f"    - 원래 빈 코드: {stats['already_blank']}")
print(f"    → 업데이트 대상: {len(updates)}건")

# 2단계: Firestore batch update (500개씩)
print("\n[2단계] Firestore batch update 실행...")
print("(중단하지 마세요)")

BATCH_SIZE = 400  # Firestore는 500 limit이지만 여유 두기
n_done = 0
start = time.time()

for i in range(0, len(updates), BATCH_SIZE):
    chunk = updates[i:i+BATCH_SIZE]
    batch = db.batch()
    for doc_id, update in chunk:
        ref = col.document(doc_id)
        batch.update(ref, update)
    batch.commit()
    n_done += len(chunk)

    elapsed = time.time() - start
    rate = n_done / elapsed if elapsed > 0 else 0
    eta = (len(updates) - n_done) / rate if rate > 0 else 0
    print(f"    {n_done}/{len(updates)} 완료 ({elapsed:.0f}초, {rate:.0f}건/초, ETA {eta:.0f}초)")

elapsed = time.time() - start
print(f"\n  완료: {n_done}건 갱신 ({elapsed:.0f}초)")

print("\n" + "=" * 80)
print("[변환 완료]")
print("=" * 80)
print(f"  변환 성공:  {stats['convert_ok']}건")
print(f"  비움 처리:  {stats['convert_fail_blank']}건")
print(f"  원래 빈:   {stats['already_blank']}건")
print(f"  보존:      {stats['skip_2022'] + stats['skip_already']}건")
print()
print("  다음 단계:")
print("    1. Firestore 샘플 조회로 검증")
print("    2. 캐시 DB 무효화")
print("    3. SC 에서 '경우의수' 등 단원 검색 → 정상화 확인")
