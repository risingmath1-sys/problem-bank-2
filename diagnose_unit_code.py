"""문제의 단원명 → unit_code 매핑 오류 진단."""
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

# 2025년 1학년 1학기 NAESIN_N 의 특정 문제
print("=== 문제 분석 (ID로 직접 조회) ===\n")
problem_id = "[고][2025][1-1-a][경기][경기고][공수1][다항식의연산-이차함수]_1"

try:
    doc = db.collection("problems").document(problem_id).get()
    if doc.exists:
        data = doc.to_dict()
        print(f"ID: {problem_id}")
        print(f"title: {data.get('title')}")
        print(f"unit_code: {data.get('unit_code')}")
        print(f"school_level: {data.get('school_level')}")
        print(f"year: {data.get('year')}")
        print(f"grade: {data.get('grade')}")
        print(f"semester: {data.get('semester')}")
        print(f"curriculum: {data.get('curriculum')}")
        print(f"\n모든 필드:")
        for k, v in data.items():
            print(f"  {k}: {v}")
    else:
        print(f"문제를 찾을 수 없습니다: {problem_id}")
except Exception as e:
    print(f"에러: {e}")

