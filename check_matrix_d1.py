"""행렬(D1) 문제 확인."""
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

# 2025년 1학년 1학기 행렬(D1)
print("=== 2025년 1학년 1학기 행렬(D1) ===")
result = db.collection("problems").where("source", "==", "NAESIN_N")\
                                  .where("year", "==", "2025")\
                                  .where("unit_code", "==", "D1").stream()
d1_list = list(result)
print(f"개수: {len(d1_list)}건\n")

if len(d1_list) > 0:
    for i, doc in enumerate(d1_list[:5]):
        data = doc.to_dict()
        print(f"[{i+1}] ID: {doc.id[:60]}")
        print(f"    unit_code: {data.get('unit_code')}")
        print(f"    file_name: {(data.get('file_name') or '')[:50]}")
        print()

# 전체 2025년 NAESIN_N unit_code 분포
print("=== 2025년 NAESIN_N unit_code 분포 (상위 20) ===")
naesin_n_2025 = db.collection("problems").where("source", "==", "NAESIN_N").where("year", "==", "2025").stream()
unit_dist = {}

for doc in naesin_n_2025:
    data = doc.to_dict()
    unit = data.get("unit_code") or "[빈값]"
    unit_dist[unit] = unit_dist.get(unit, 0) + 1

for unit, count in sorted(unit_dist.items(), key=lambda x: -x[1])[:20]:
    print(f"  {unit}: {count}건")

print(f"\n전체: {sum(unit_dist.values())}건")
print(f"행렬(D1): {unit_dist.get('D1', 0)}건")

