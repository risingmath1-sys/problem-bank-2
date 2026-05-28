"""2025년 grade/semester 분포 확인."""
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

# 2025년 NAESIN_N 문제 grade/semester 분포
naesin_n_2025 = db.collection("problems").where("source", "==", "NAESIN_N").where("year", "==", 2025).stream()
grade_sem_dist = {}
unit_dist = {}

for doc in naesin_n_2025:
    data = doc.to_dict()
    grade = str(data.get("grade") or "[NULL]")
    semester = str(data.get("semester") or "[NULL]")
    unit = str(data.get("unit_code") or "[빈값]")
    
    key = f"{grade} / {semester}"
    grade_sem_dist[key] = grade_sem_dist.get(key, 0) + 1
    unit_dist[unit] = unit_dist.get(unit, 0) + 1

print("=== 2025년 NAESIN_N grade/semester 분포 ===")
for gs, count in sorted(grade_sem_dist.items(), key=lambda x: -x[1]):
    print(f"  {gs}: {count}건")

print("\n=== 2025년 NAESIN_N unit_code 분포 ===")
for unit, count in sorted(unit_dist.items(), key=lambda x: -x[1])[:15]:
    print(f"  {unit}: {count}건")

# 행렬 코드 D1 확인
d1_count = unit_dist.get("D1", 0)
print(f"\n행렬(D1): {d1_count}건")

