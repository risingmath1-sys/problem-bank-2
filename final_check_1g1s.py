"""2025 1G 1S unit_code distribution."""
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

# 2025년 1학년 1학기 unit_code 정확히 매칭
print("=== 2025 G1 S1 unit_code distribution ===\n")
result = db.collection("problems").where("source", "==", "NAESIN_N")\
                                  .where("year", "==", "2025").stream()

unit_dist = {}
grade_count = {}

for doc in result:
    data = doc.to_dict()
    grade = data.get('grade')
    semester = data.get('semester')
    unit = data.get('unit_code') or '[empty]'
    
    if grade and semester:
        grade_count[f"{grade}/{semester}"] = grade_count.get(f"{grade}/{semester}", 0) + 1

for gs, count in sorted(grade_count.items(), key=lambda x: -x[1]):
    print(f"{gs}: {count}")

# 정확히 '고1'/'1학기'만 필터
print("\n\n=== Filtering by grade='고1', semester='1학기' ===\n")

# 샘플 하나로 정확한 문자열 확인
result = db.collection("problems").where("source", "==", "NAESIN_N")\
                                  .where("year", "==", "2025").limit(1).stream()
for doc in result:
    data = doc.to_dict()
    print(f"Sample grade value: '{data.get('grade')}' (repr: {repr(data.get('grade'))})")
    print(f"Sample semester value: '{data.get('semester')}' (repr: {repr(data.get('semester'))})")

