"""2025 G1 S1 empty unit_code samples."""
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

print("=== 2025 G1 S1 empty unit_code (10 samples) ===\n")

result = db.collection("problems").where("source", "==", "NAESIN_N")\
                                  .where("year", "==", "2025")\
                                  .where("unit_code", "==", "").limit(10).stream()

for i, doc in enumerate(result):
    data = doc.to_dict()
    print(f"[{i+1}] file_name: {(data.get('file_name') or '')[:60]}")
    grade = data.get('grade') or ''
    semester = data.get('semester') or ''
    grade_num = ''.join(c for c in grade if c.isdigit())
    sem_num = semester.split('학기')[0].strip() if semester else ''
    print(f"    grade={grade} ({grade_num}), semester={semester} ({sem_num})")

