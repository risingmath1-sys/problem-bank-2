"""2025 1G 1S matrix problem check."""
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

#2025 all NAESIN_N
result = db.collection("problems").where("source", "==", "NAESIN_N")\
                                  .where("year", "==", "2025").stream()

g1s1_units = {}
all_units = {}

for doc in result:
    data = doc.to_dict()
    grade = data.get('grade') or ''
    semester = data.get('semester') or ''
    unit = data.get('unit_code') or '[empty]'
    
    # all
    all_units[unit] = all_units.get(unit, 0) + 1
    
    # 1G 1S only - match by numeric pattern
    if grade and semester:
        grade_num = ''.join(c for c in grade if c.isdigit())
        sem_num = semester.split('학기')[0].strip()
        if grade_num == '1' and sem_num == '1':
            g1s1_units[unit] = g1s1_units.get(unit, 0) + 1

print("=== 2025 G1 S1 unit_code ===")
print(f"Total: {sum(g1s1_units.values())}")
for unit, count in sorted(g1s1_units.items(), key=lambda x: -x[1])[:20]:
    print(f"  {unit}: {count}")

print(f"\n행렬(D1): {g1s1_units.get('D1', 0)}개")

