#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firestore NAESIN_A 변환 대상(curriculum=2015교육과정) 백업 → JSON
롤백용. 변환 작업 전 반드시 실행.
"""
import os, sys, json
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

KEY = "G:/문제은행/문제은행2/firebase-key.json"
from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

print("=" * 80)
print("[Firestore 백업] NAESIN_A + curriculum='2015교육과정'")
print("=" * 80)

col = db.collection("problems")
q = col.where("source", "==", "NAESIN_A")

backup = []
total = 0

print("\n[1] 스트림 시작...")
for doc in q.stream():
    d = doc.to_dict()
    cur = d.get("curriculum", "")

    # 변환 대상만 백업 (2022 자료, 이미 변환된 자료는 제외)
    if "2022" in cur or cur == "2015개정교육과정":
        continue

    total += 1
    rec = {
        "doc_id": doc.id,
        "data": d,
    }
    backup.append(rec)

    if total % 2000 == 0:
        print(f"    ... {total}건 백업됨")

print(f"  완료: {total}건")

# 타임스탬프 포함된 파일명
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_path = f"backup_naesin_a_2015_{ts}.json"
def _json_default(o):
    # Firestore의 DatetimeWithNanoseconds 등은 isoformat 으로
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(backup, f, ensure_ascii=False, indent=1, default=_json_default)

size_mb = os.path.getsize(out_path) / 1024 / 1024
print(f"\n  → 백업 파일: {out_path}")
print(f"  → 크기: {size_mb:.1f} MB")
print(f"  → 레코드 수: {total}건")

print("\n" + "=" * 80)
print("백업 완료 — 변환 작업 진행 가능")
print("=" * 80)
