"""NAESIN_N year 분포 확인."""
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

# year 필드 값 분포
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
year_dist = {}

for doc in naesin_n:
    data = doc.to_dict()
    year = data.get("year")
    year_str = str(year) if year is not None else "[NULL]"
    year_dist[year_str] = year_dist.get(year_str, 0) + 1

print("=== NAESIN_N year 분포 ===")
try:
    for year, count in sorted([(y, c) for y, c in year_dist.items()], 
                             key=lambda x: -int(x[0]) if x[0] != "[NULL]" else 0):
        print(f"  {year}: {count}건")
except Exception as e:
    for year, count in sorted(year_dist.items(), key=lambda x: -x[1]):
        print(f"  {year}: {count}건")

print(f"\nTotal NAESIN_N: {sum(year_dist.values())}건")
print(f"2025년 NAESIN_N: {year_dist.get('2025', 0)}건")
print(f"2023년 NAESIN_N: {year_dist.get('2023', 0)}건")

