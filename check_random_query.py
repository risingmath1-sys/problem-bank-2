"""사용자 검색 조건 시뮬레이션."""
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

print("=== 사용자 검색 시뮬레이션 ===\n")

# 시나리오 1: source=NAESIN_N, unit_code in [J1,J2,J3]
print("[1] NAESIN_N + 수열(J1/J2/J3) 전체 (year 무관)")
total = 0
for code in ["J1","J2","J3"]:
    cnt = sum(1 for _ in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).stream())
    print(f"  {code}: {cnt}건")
    total += cnt
print(f"  합: {total}건")

# 시나리오 2: + year=2025 (정수)
print("\n[2] + year==2025 (정수)")
total = 0
for code in ["J1","J2","J3"]:
    cnt = sum(1 for _ in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).where("year","==",2025).stream())
    print(f"  {code}: {cnt}건")
    total += cnt
print(f"  합: {total}건")

# 시나리오 3: + year="2025" (문자열)
print("\n[3] + year=='2025' (문자열)")
total = 0
for code in ["J1","J2","J3"]:
    cnt = sum(1 for _ in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).where("year","==","2025").stream())
    print(f"  {code}: {cnt}건")
    total += cnt
print(f"  합: {total}건")

# 시나리오 4: in 쿼리 사용 (서버 _build_filters와 동일)
print("\n[4] unit_code IN [J1,J2,J3] AND year=='2025'")
cnt = sum(1 for _ in db.collection("problems")
    .where("source","==","NAESIN_N")
    .where("unit_code","in",["J1","J2","J3"])
    .where("year","==","2025").stream())
print(f"  합: {cnt}건")

# year 값 타입 확인
print("\n[5] NAESIN_N year 필드 타입 (J1 매핑된 문서 샘플 1개)")
for doc in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==","J1").limit(1).stream():
    d = doc.to_dict()
    y = d.get("year")
    print(f"  year={y!r} (type={type(y).__name__})")

