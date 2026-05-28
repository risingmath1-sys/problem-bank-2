"""2025년 NAESIN_N 샘플 문제 상세 확인."""
import sys
from pathlib import Path
import json

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

# 2025년 NAESIN_N 문제 5개 샘플
naesin_n_2025 = db.collection("problems").where("source", "==", "NAESIN_N").where("year", "==", 2025).limit(5).stream()

print("=== 2025년 NAESIN_N 샘플 5개 ===\n")
for i, doc in enumerate(naesin_n_2025):
    data = doc.to_dict()
    print(f"[{i+1}] ID: {doc.id[:80]}")
    print(f"    title: {(data.get('title') or '')[:50]}")
    print(f"    year: {data.get('year')}")
    print(f"    grade: {data.get('grade')}")
    print(f"    semester: {data.get('semester')}")
    print(f"    unit_code: {data.get('unit_code')}")
    print(f"    school: {data.get('school')}")
    print(f"    file_name: {(data.get('file_name') or '')[:50]}")
    
    # 전체 필드 확인
    print(f"    [모든 필드]: {list(data.keys())}")
    print()

