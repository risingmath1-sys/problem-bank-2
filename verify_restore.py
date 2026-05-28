"""복구 결과 검증."""
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

print("=== 복구 후 검증 ===\n")

# 1. 사용자 케이스: NAESIN_N 수열 (J1, J2, J3)
print("[1] NAESIN_N 수열 unit_code 분포 (복구 전: 0건)")
for code in ["J1","J2","J3"]:
    cnt = 0
    by_year = Counter()
    for doc in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).stream():
        d = doc.to_dict()
        cnt += 1
        by_year[str(d.get("year") or "?")] += 1
    print(f"  {code}: {cnt}건 - year {dict(by_year)}")

# 2. NAESIN_N 삼각함수 (I1, I2, I3)
print("\n[2] NAESIN_N 삼각함수 unit_code 분포 (복구 전: 0건)")
for code in ["I1","I2","I3"]:
    cnt = 0
    by_year = Counter()
    for doc in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).stream():
        d = doc.to_dict()
        cnt += 1
        by_year[str(d.get("year") or "?")] += 1
    print(f"  {code}: {cnt}건 - year {dict(by_year)}")

# 3. NAESIN_N 지수/로그 (H1, H2)
print("\n[3] NAESIN_N 지수/로그 unit_code 분포")
for code in ["H1","H2","H3","H4"]:
    cnt = sum(1 for _ in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).stream())
    print(f"  {code}: {cnt}건")

# 4. 이상 매핑이 남아 있는지 - 잘못된 코드 P/O/V 에 NAESIN_N (수학1/대수 시험지에 잡힐 일 없어야 함)
print("\n[4] NAESIN_N P/O/V 코드 (제거되어야 함, 복구 전: 多)")
for code in ["P1","P2","O1","O2","V1","V2","T4"]:
    cnt = sum(1 for _ in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).limit(50).stream())
    print(f"  {code}: {cnt}건")

# 5. NAESIN_A 도 같이 확인
print("\n[5] NAESIN_A 수열/삼각 unit_code")
for code in ["I1","I2","I3","J1","J2","J3"]:
    cnt = sum(1 for _ in db.collection("problems").where("source","==","NAESIN_A").where("unit_code","==",code).limit(500).stream())
    print(f"  {code}: {cnt}건")

# 6. 2025 고1 1학기 기말의 행렬 (D1) - naesin_n_unit_map.json 수정만 했고 재인덱싱 안 했으므로 아직 0
print("\n[6] 2025 고1 1학기 기말 NAESIN_N unit_code (행렬 재인덱싱 필요 확인용)")
naesin_n_2025_g1 = []
for doc in db.collection("problems").where("source","==","NAESIN_N").where("year","==","2025").stream():
    d = doc.to_dict()
    if d.get("grade") == "고1" and d.get("semester") == "1학기" and d.get("exam_type") == "기말고사":
        naesin_n_2025_g1.append(d)

unit_dist = Counter()
for d in naesin_n_2025_g1:
    unit_dist[d.get("unit_code") or "[EMPTY]"] += 1
print(f"  총 {len(naesin_n_2025_g1)}건")
for u, n in unit_dist.most_common():
    print(f"    {u}: {n}")

