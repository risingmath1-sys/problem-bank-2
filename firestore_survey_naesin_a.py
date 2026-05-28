#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firestore에서 NAESIN_A 자료 현황 조사 — DRY RUN (수정 안 함)
"""
import os, sys, json
from collections import Counter
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# 키 파일로 직접 연결
KEY = "G:/문제은행/문제은행2/firebase-key.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY

from google.cloud import firestore
db = firestore.Client.from_service_account_json(KEY)

print("[Firestore 연결] OK")
print()

# NAESIN_A 전체 가져오기 (스트림)
print("=" * 90)
print("[1] NAESIN_A 전체 카운트 진행 중...")
print("=" * 90)

col = db.collection("problems")

# Firestore는 source 인덱스 있다고 가정 (이미 잘 쿼리됨)
q = col.where("source", "==", "NAESIN_A")

# 일괄 가져오기 (스트림 방식)
total = 0
subj_cnt = Counter()
curr_cnt = Counter()
subj_curr_uc = {}  # {(subject, curriculum): Counter(unit_code)}
indexed_day_cnt = Counter()

print("  스트림 시작 (수 분 소요 가능)...")
start_ts = datetime.now()

for doc in q.stream():
    d = doc.to_dict()
    total += 1
    s = d.get("subject", "") or "(빈)"
    cur = d.get("curriculum", "") or "(빈)"
    uc = d.get("unit_code", "") or "(빈)"

    subj_cnt[s] += 1
    curr_cnt[cur] += 1

    key = (s, cur)
    if key not in subj_curr_uc:
        subj_curr_uc[key] = Counter()
    subj_curr_uc[key][uc] += 1

    # indexed_at (epoch sec)
    ts = d.get("indexed_at")
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            indexed_day_cnt[day] += 1
        except Exception:
            pass

    if total % 2000 == 0:
        elapsed = (datetime.now() - start_ts).total_seconds()
        print(f"    ... {total}건 ({elapsed:.0f}초 경과)")

elapsed = (datetime.now() - start_ts).total_seconds()
print(f"  스트림 완료: {total}건 ({elapsed:.0f}초)")

# ─────────────────────────────────────────
print("\n" + "=" * 90)
print(f"[2] NAESIN_A 총 {total}건 — Firestore 진본 기준")
print("=" * 90)

# subject 분포
print("\n  [subject 분포]")
for s, cnt in subj_cnt.most_common():
    print(f"    '{s}': {cnt}건")

# curriculum 분포
print("\n  [curriculum 분포]")
for cur, cnt in curr_cnt.most_common():
    print(f"    '{cur}': {cnt}건")

# 최근 인덱싱 일별 (7일)
print("\n  [최근 7일 인덱싱]")
recent_days = sorted(indexed_day_cnt.keys())[-10:]
for day in recent_days:
    print(f"    {day}: {indexed_day_cnt[day]}건")

# ─────────────────────────────────────────
print("\n" + "=" * 90)
print("[3] subject × curriculum × unit_code (상위 코드)")
print("=" * 90)

for (s, cur) in sorted(subj_curr_uc.keys()):
    n_total = sum(subj_curr_uc[(s, cur)].values())
    print(f"\n  '{s}' / curriculum='{cur}' : {n_total}건")
    top = subj_curr_uc[(s, cur)].most_common(12)
    codes_str = ", ".join(f"{c}({n})" for c, n in top if c != "(빈)")
    print(f"    상위 코드: {codes_str}")
    if "(빈)" in subj_curr_uc[(s, cur)]:
        print(f"    [빈 unit_code]: {subj_curr_uc[(s, cur)]['(빈)']}건")

# 결과를 파일로도 저장
output = {
    "total": total,
    "subject_counts": dict(subj_cnt),
    "curriculum_counts": dict(curr_cnt),
    "subject_curriculum_unit_code": {
        f"{k[0]}|{k[1]}": dict(v) for k, v in subj_curr_uc.items()
    },
    "recent_indexing_days": dict(sorted(indexed_day_cnt.items())[-30:]),
}
with open("firestore_naesin_a_survey.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  → 결과 저장: firestore_naesin_a_survey.json")
