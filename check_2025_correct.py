"""2025년(문자열) NAESIN_N 상세 확인."""
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

# 2025년(문자열) NAESIN_N
print("=== 2025년(문자열) NAESIN_N 샘플 10개 ===\n")
naesin_n_2025 = db.collection("problems").where("source", "==", "NAESIN_N").where("year", "==", "2025").limit(10).stream()

for i, doc in enumerate(naesin_n_2025):
    data = doc.to_dict()
    print(f"[{i+1}] ID: {doc.id[:60]}")
    print(f"    title: {(data.get('title') or '')[:50]}")
    print(f"    year: {data.get('year')} (type={type(data.get('year')).__name__})")
    print(f"    grade: {data.get('grade')} (type={type(data.get('grade')).__name__ if data.get('grade') else 'None'})")
    print(f"    semester: {data.get('semester')} (type={type(data.get('semester')).__name__ if data.get('semester') else 'None'})")
    print(f"    unit_code: {data.get('unit_code')}")
    print()

# grade/semester 분포 (문자열 2025)
print("\n=== 2025년(문자열) NAESIN_N grade/semester 분포 ===")
naesin_n_2025 = db.collection("problems").where("source", "==", "NAESIN_N").where("year", "==", "2025").stream()
grade_dist = {}
semester_dist = {}
grade_sem_dist = {}

for doc in naesin_n_2025:
    data = doc.to_dict()
    grade = data.get("grade")
    semester = data.get("semester")
    
    if grade:
        grade_dist[str(grade)] = grade_dist.get(str(grade), 0) + 1
    if semester:
        semester_dist[str(semester)] = semester_dist.get(str(semester), 0) + 1
    
    if grade and semester:
        key = f"{grade} / {semester}"
        grade_sem_dist[key] = grade_sem_dist.get(key, 0) + 1

print(f"Grade 분포: {len(grade_dist)}개 타입")
for g, c in sorted(grade_dist.items(), key=lambda x: -x[1])[:10]:
    print(f"  {g}: {c}건")

print(f"\nSemester 분포: {len(semester_dist)}개 타입")
for s, c in sorted(semester_dist.items(), key=lambda x: -x[1])[:10]:
    print(f"  {s}: {c}건")

print(f"\nGrade/Semester 조합: {len(grade_sem_dist)}개 조합")
for gs, c in sorted(grade_sem_dist.items(), key=lambda x: -x[1])[:10]:
    print(f"  {gs}: {c}건")

