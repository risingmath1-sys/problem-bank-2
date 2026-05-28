"""행렬 문제 상세 확인."""
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

# NAESIN_N에서 "행렬" 포함 문제 찾기
print("=== NAESIN_N에서 '행렬' 포함 문제 ===")
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
matrix_count = 0
matrix_units = {}
for doc in naesin_n:
    data = doc.to_dict()
    title = data.get("title") or ""
    
    if "행렬" in title:
        matrix_count += 1
        unit = data.get("unit_code") or "[빈값]"
        matrix_units[unit] = matrix_units.get(unit, 0) + 1
        
        if matrix_count <= 15:
            print(f"[{matrix_count}] {title[:60]}")
            print(f"    ID: {doc.id}")
            print(f"    unit_code: {unit}")
            print(f"    year: {data.get('year')}, grade: {data.get('grade')}, semester: {data.get('semester')}")
            print(f"    school: {data.get('school')}")
            print()

print(f"총 행렬 문제: {matrix_count}건")
print(f"\n행렬 문제의 unit_code 분포:")
for unit, count in sorted(matrix_units.items(), key=lambda x: -x[1]):
    print(f"  {unit}: {count}건")

