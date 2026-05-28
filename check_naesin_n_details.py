"""NAESIN_N 메타데이터 확인."""
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

# NAESIN_N 샘플 문제 조회
print("=== NAESIN_N 샘플 문제 (10개) ===")
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").limit(10).stream()
for i, doc in enumerate(naesin_n):
    data = doc.to_dict()
    title = (data.get('title') or "")[:60]
    print(f"\n[{i+1}] {title}")
    print(f"    ID: {doc.id}")
    print(f"    year: {data.get('year')}")
    print(f"    grade: {data.get('grade')}")
    print(f"    semester: {data.get('semester')}")
    print(f"    unit_code: {data.get('unit_code')}")

# year 필드 값 분포
print("\n\n=== NAESIN_N year 필드 분포 ===")
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
year_dist = {}
grade_dist = {}
semester_dist = {}

for doc in naesin_n:
    data = doc.to_dict()
    year = data.get("year")
    grade = data.get("grade")
    semester = data.get("semester")
    
    if year is None:
        year = "[NULL]"
    if grade is None:
        grade = "[NULL]"
    if semester is None:
        semester = "[NULL]"
    
    year_dist[str(year)] = year_dist.get(str(year), 0) + 1
    grade_dist[str(grade)] = grade_dist.get(str(grade), 0) + 1
    semester_dist[str(semester)] = semester_dist.get(str(semester), 0) + 1

print("Year 분포:")
for year, count in sorted(year_dist.items(), key=lambda x: -count):
    print(f"  {year}: {count}건")

print("\nGrade 분포:")
for grade, count in sorted(grade_dist.items(), key=lambda x: -count):
    print(f"  {grade}: {count}건")

print("\nSemester 분포:")
for sem, count in sorted(semester_dist.items(), key=lambda x: -count):
    print(f"  {sem}: {count}건")

