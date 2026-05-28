"""ZL1 unit_code 가진 NAESIN_N 문제 확인."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

import firebase_admin
from firebase_admin import firestore

db = firestore.client()

# ZL1 unit_code 가진 NAESIN_N 문제
print("=== ZL1 unit_code NAESIN_N problems ===\n")
result = db.collection("problems").where("source", "==", "NAESIN_N")\
                                  .where("unit_code", "==", "ZL1").limit(3).stream()

for i, doc in enumerate(result):
    data = doc.to_dict()
    print(f"[{i+1}] year={data.get('year')}, grade={data.get('grade')}, semester={data.get('semester')}")
    print(f"    curriculum={data.get('curriculum')}")
    print(f"    school_level={data.get('school_level')}")
    print(f"    file_name={(data.get('file_name') or '')[:70]}")
    print()

# ZL1 의 year 분포
print("\n=== ZL1 unit_code distribution by year ===")
result = db.collection("problems").where("source", "==", "NAESIN_N")\
                                  .where("unit_code", "==", "ZL1").stream()
year_dist = {}
for doc in result:
    data = doc.to_dict()
    year = data.get('year') or '[NULL]'
    year_dist[str(year)] = year_dist.get(str(year), 0) + 1

for year, count in sorted(year_dist.items()):
    print(f"  {year}: {count}건")

