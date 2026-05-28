"""내신기출B 행렬 문제 확인 스크립트."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.firebase_init import init_admin_sdk
import firebase_admin
from firebase_admin import firestore

# Firebase 초기화
try:
    init_admin_sdk()
except Exception:
    pass  # 이미 초기화됨

db = firestore.client()

# 1. 전체 NAESIN_N 건수
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
naesin_n_list = list(naesin_n)
print(f"[1] 전체 NAESIN_N: {len(naesin_n_list)}건")

# 2. 행렬(matrix, 행렬, 벡터 포함) 키워드로 필터
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
matrix_keywords = ["행렬", "벡터", "matrix"]
matrix_problems = []
for doc in naesin_n:
    data = doc.to_dict()
    title = (data.get("title") or "").lower()
    unit = (data.get("unit_code") or "").lower()
    
    if any(kw.lower() in title or kw.lower() in unit for kw in matrix_keywords):
        matrix_problems.append({
            "id": doc.id,
            "title": data.get("title"),
            "unit_code": data.get("unit_code"),
            "year": data.get("year"),
            "semester": data.get("semester"),
            "grade": data.get("grade"),
            "school": data.get("school"),
        })

print(f"\n[2] 행렬/벡터 키워드 포함: {len(matrix_problems)}건")
for p in matrix_problems[:5]:
    print(f"  - {p['title'][:50]} | unit={p['unit_code']} | {p.get('year')}년 {p.get('grade')}학년 {p.get('semester')}학기")

# 3. 2025년, 1학년, 1학기 필터
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
filtered_2025 = []
for doc in naesin_n:
    data = doc.to_dict()
    year = data.get("year")
    grade = data.get("grade")
    semester = data.get("semester")
    title = (data.get("title") or "").lower()
    
    if year == 2025 and grade == 1 and semester == 1:
        filtered_2025.append({
            "id": doc.id,
            "title": data.get("title"),
            "unit_code": data.get("unit_code"),
            "school": data.get("school"),
        })
        if any(kw.lower() in title for kw in ["행렬", "벡터"]):
            print(f"  ✓ {data.get('title')} | unit={data.get('unit_code')}")

print(f"\n[3] 2025년 1학년 1학기 NAESIN_N: {len(filtered_2025)}건")

# 4. unit_code별 분포
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
unit_dist = {}
for doc in naesin_n:
    data = doc.to_dict()
    unit = data.get("unit_code") or "[빈값]"
    unit_dist[unit] = unit_dist.get(unit, 0) + 1

print(f"\n[4] unit_code 분포 (상위 10):")
for unit, count in sorted(unit_dist.items(), key=lambda x: -x[1])[:10]:
    print(f"  {unit}: {count}건")

