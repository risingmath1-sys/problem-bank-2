#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Firestore 분포 재확인 — 변환이 정말 됐는지."""
import os, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

curr_cnt = Counter()
total = 0
for doc in q.stream():
    d = doc.to_dict()
    total += 1
    curr_cnt[d.get("curriculum","") or "(빈)"] += 1
    if total % 5000 == 0:
        print(f"  ... {total}건")

print(f"\n[Firestore NAESIN_A 총 {total}건]")
print("\n[curriculum 분포]")
for k, v in curr_cnt.most_common():
    print(f"  '{k}': {v}건")
