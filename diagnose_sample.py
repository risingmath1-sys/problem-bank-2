"""2025 1G 1S NAESIN_N sample analysis."""
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

naesin_n_2025 = db.collection("problems").where("source", "==", "NAESIN_N")\
                                        .where("year", "==", "2025")\
                                        .limit(1).stream()

for doc in naesin_n_2025:
    data = doc.to_dict()
    doc_id = doc.id
    
    print(f"=== Firestore Sample Analysis ===\n")
    print(f"Document ID: {doc_id}")
    print(f"\nMain fields:")
    print(f"  source: {data.get('source')}")
    print(f"  title: {(data.get('title') or '')[:50]}")
    print(f"  year: {data.get('year')} (type={type(data.get('year')).__name__})")
    print(f"  grade: {data.get('grade')} (type={type(data.get('grade')).__name__})")
    print(f"  semester: {data.get('semester')}")
    print(f"  unit_code: {data.get('unit_code')}")
    print(f"  school_level: {data.get('school_level')}")
    print(f"  curriculum: {data.get('curriculum')}")
    print(f"  subject: {data.get('subject')}")
    print(f"  school: {data.get('school')}")
    print(f"  file_name: {(data.get('file_name') or '')[:50]}")
    
    unit = data.get('unit_code') or ''
    if unit.startswith('Z'):
        print(f"\nWARNING: unit_code='{unit}' is middle school code!")
        print(f"  expected: high school code (A1, B1, D1 etc)")

