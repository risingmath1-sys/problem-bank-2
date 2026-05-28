"""대수/수열 단원 unit_code 확인."""
import sys, io
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

import firebase_admin
from firebase_admin import firestore
import json

db = firestore.client()

# unit_hierarchy.json 에서 "대수" 와 "수열" 의 unit_code 찾기
hier_path = PROJECT_ROOT / "backend" / "unit_hierarchy.json"
with hier_path.open(encoding="utf-8") as f:
    hier = json.load(f)

print("=== unit_hierarchy.json 에서 대수/수열 검색 ===\n")
for version in ["2022", "2015"]:
    print(f"--- {version} ---")
    for subj in hier.get(version, []):
        subj_name = subj.get("subject")
        for large in subj.get("large_units", []):
            for medium in large.get("medium_units", []):
                name = medium.get("name", "")
                code = medium.get("code", "")
                if any(k in name for k in ["대수", "수열", "지수", "로그", "삼각"]):
                    print(f"  [{version}] {subj_name} > {large.get('name')} > {name} (code={code})")
    print()

# Firestore의 NAESIN_N 중 J1, J2, J3 (수열) 데이터
print("=== NAESIN_N 수열 unit_code 분포 ===")
result = db.collection("problems").where("source", "==", "NAESIN_N").stream()
docs = [doc.to_dict() for doc in result]

su_codes = ["J1", "J2", "J3"]
for code in su_codes:
    by_year = Counter()
    by_grade = Counter()
    total = 0
    for d in docs:
        if d.get("unit_code") == code:
            total += 1
            by_year[str(d.get("year") or "?")] += 1
            by_grade[str(d.get("grade") or "?")] += 1
    print(f"\n{code}: 총 {total}건")
    if total:
        print(f"  Year: {dict(by_year)}")
        print(f"  Grade: {dict(by_grade)}")

# "수학1" 또는 "대수" subject 분포
print("\n=== NAESIN_N subject 분포 (2025) ===")
subj_dist = Counter()
for d in docs:
    if str(d.get("year") or "") == "2025":
        subj_dist[d.get("subject") or "[NULL]"] += 1
for s, n in subj_dist.most_common():
    print(f"  '{s}': {n}건")

# 2025년 NAESIN_N 에서 수열 관련 단원
print("\n=== 2025 NAESIN_N 에서 수열/지수/로그 unit_code ===")
target_codes = ["H1", "H2", "H3", "H4", "I1", "I2", "I3", "J1", "J2", "J3"]
for code in target_codes:
    cnt = sum(1 for d in docs if str(d.get("year") or "") == "2025" and d.get("unit_code") == code)
    if cnt > 0:
        # 어느 학년인지
        grades = Counter()
        for d in docs:
            if str(d.get("year") or "") == "2025" and d.get("unit_code") == code:
                grades[d.get("grade") or "?"] += 1
        print(f"  {code}: {cnt}건 - grade {dict(grades)}")

