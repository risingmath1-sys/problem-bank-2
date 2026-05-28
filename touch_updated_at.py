#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firestore 변환된 자료의 updated_at 을 강제 갱신.
→ 캐시 sync가 변경 감지하여 새 데이터 받아오게 함.
"""
import os, sys, time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

print("=" * 80)
print("[updated_at 강제 갱신] NAESIN_A + curriculum='2015개정교육과정' 변환된 자료")
print("=" * 80)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

# updates 모으기 — 변환된 자료(2015개정교육과정 + mapped_unit_code 가 채워진 것)
print("\n[1] 변환된 자료 식별...")
target_ids = []
total = 0
for doc in q.stream():
    d = doc.to_dict()
    total += 1
    cur = d.get("curriculum", "")
    if cur != "2015개정교육과정":
        continue
    # 단순히 2015개정교육과정인 자료 전부 → 17329건
    target_ids.append(doc.id)
    if total % 5000 == 0:
        print(f"    ... 스캔 {total}건, 대상 {len(target_ids)}건")

print(f"\n  스캔 완료: {total}건 중 {len(target_ids)}건이 updated_at 갱신 대상")

# 2) Firestore 의 SERVER_TIMESTAMP 사용
print("\n[2] updated_at 일괄 갱신 (400개씩 batch)...")
BATCH = 400
done = 0
start = time.time()

for i in range(0, len(target_ids), BATCH):
    chunk = target_ids[i:i+BATCH]
    batch = db.batch()
    for doc_id in chunk:
        ref = col.document(doc_id)
        batch.update(ref, {"updated_at": firestore.SERVER_TIMESTAMP})
    batch.commit()
    done += len(chunk)
    elapsed = time.time() - start
    rate = done / elapsed if elapsed > 0 else 0
    eta = (len(target_ids) - done) / rate if rate > 0 else 0
    print(f"    {done}/{len(target_ids)} ({elapsed:.0f}s, {rate:.0f}/s, ETA {eta:.0f}s)")

print(f"\n[완료] {done}건 updated_at 갱신")
print("→ 다음 캐시 sync에서 변경 감지하여 새 데이터 받아옴")
