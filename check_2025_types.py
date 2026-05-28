"""2025년 year 필드 타입 확인."""
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

# year 필드 값 샘플
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").limit(10).stream()

print("=== NAESIN_N 샘플 year 필드 타입 ===\n")
for i, doc in enumerate(naesin_n):
    data = doc.to_dict()
    year = data.get("year")
    print(f"[{i+1}] year={year} (type={type(year).__name__})")

# 숫자 2025 vs 문자 "2025" 모두 시도
print("\n\n=== 숫자 2025로 조회 ===")
result1 = db.collection("problems").where("source", "==", "NAESIN_N").where("year", "==", 2025).stream()
count1 = len(list(result1))
print(f"결과: {count1}건")

print("\n=== 문자 '2025'로 조회 ===")
result2 = db.collection("problems").where("source", "==", "NAESIN_N").where("year", "==", "2025").stream()
count2 = len(list(result2))
print(f"결과: {count2}건")

