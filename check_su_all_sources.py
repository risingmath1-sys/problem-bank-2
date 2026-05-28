"""모든 소스에서 수열(J1,J2,J3) 분포."""
import sys, io
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

import firebase_admin
from firebase_admin import firestore

db = firestore.client()

# 1. 전체 problems 컬렉션에서 수열 unit_code 분포
print("=== 전체 problems 에서 J1/J2/J3 (수열) 소스별 분포 ===\n")
for code in ["J1", "J2", "J3"]:
    by_source = Counter()
    by_year_source = Counter()
    result = db.collection("problems").where("unit_code", "==", code).stream()
    for doc in result:
        d = doc.to_dict()
        src = d.get("source") or "?"
        year = str(d.get("year") or "?")
        by_source[src] += 1
        by_year_source[(src, year)] += 1
    
    print(f"{code}: 총 {sum(by_source.values())}건")
    for src, n in by_source.most_common():
        print(f"  {src}: {n}")

# 2. NAESIN_N 전체에서 unit_code 분포 (수학1/대수 단원 확인)
print("\n\n=== NAESIN_N 전체 unit_code 분포 (수학1/대수 단원) ===")
result = db.collection("problems").where("source", "==", "NAESIN_N").stream()
docs = [doc.to_dict() for doc in result]

# 수학1/대수 관련 코드들
math1_codes = ["H1","H2","H3","H4","I1","I2","I3","J1","J2","J3"]
print(f"\n전체 NAESIN_N에서 수학1/대수 코드 분포:")
for code in math1_codes:
    cnt = sum(1 for d in docs if d.get("unit_code") == code)
    grades = Counter()
    years = Counter()
    for d in docs:
        if d.get("unit_code") == code:
            grades[d.get("grade") or "?"] += 1
            years[str(d.get("year") or "?")] += 1
    if cnt > 0:
        print(f"  {code}: {cnt} - grade {dict(grades)}, year {dict(years)}")
    else:
        print(f"  {code}: 0 ❌")

# 3. NAESIN_N 고2 데이터 파일명 샘플
print("\n=== NAESIN_N 2025 고2 파일명 샘플 (수열 있는지) ===")
import re
g2_files = set()
for d in docs:
    if str(d.get("year") or "") == "2025" and d.get("grade") == "고2":
        g2_files.add(d.get("file_name") or "")

# 수열이 포함된 파일명
su_files = [f for f in g2_files if "수열" in f]
print(f"\n2025 고2 시험지 총 {len(g2_files)}개")
print(f"파일명에 '수열' 포함: {len(su_files)}개")
for f in list(su_files)[:10]:
    print(f"  {f[:120]}")

# 4. 2025 고2 unit_code 분포
print("\n=== 2025 고2 NAESIN_N unit_code 분포 ===")
g2_units = Counter()
for d in docs:
    if str(d.get("year") or "") == "2025" and d.get("grade") == "고2":
        g2_units[d.get("unit_code") or "[EMPTY]"] += 1

for u, n in g2_units.most_common():
    print(f"  {u}: {n}")

