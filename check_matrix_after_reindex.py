"""재인덱싱 후 행렬 D1 상태 확인."""
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

# 1. NAESIN_N D1 (행렬) 카운트
print("=== [1] NAESIN_N D1(행렬) 카운트 ===")
d1_count = sum(1 for _ in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==","D1").stream())
print(f"  D1: {d1_count}건")

# 2. 2025 고1 1학기 기말 NAESIN_N 빈값 카운트
print("\n=== [2] 2025 고1 1학기 기말 NAESIN_N 분포 ===")
target = []
for doc in db.collection("problems").where("source","==","NAESIN_N").where("year","==","2025").stream():
    d = doc.to_dict()
    if d.get("grade") == "고1" and d.get("semester") == "1학기" and d.get("exam_type") == "기말고사":
        target.append((doc.id, d))

unit_dist = Counter()
for doc_id, d in target:
    unit_dist[d.get("unit_code") or "[EMPTY]"] += 1

print(f"총 {len(target)}건")
for u, n in unit_dist.most_common():
    print(f"  {u}: {n}")

# 3. 빈값 케이스 — 파일별 분포 + 최근 indexed_at 확인
print("\n=== [3] 빈값 케이스 파일별 + 최근 인덱싱 시간 ===")
empty_by_file = Counter()
for doc_id, d in target:
    if not (d.get("unit_code") or ""):
        empty_by_file[d.get("file_name") or ""] += 1

print(f"빈값 파일 수: {len(empty_by_file)}개")
for fname, n in empty_by_file.most_common(10):
    print(f"  [{n:3d}] {fname[:100]}")

# 한 파일 골라 indexed_at 확인 (최근 인덱싱 여부)
if empty_by_file:
    sample_fname = list(empty_by_file.keys())[0]
    print(f"\n샘플 파일 '{sample_fname[:60]}...' 의 첫 문제 상세:")
    for doc_id, d in target:
        if d.get("file_name") == sample_fname:
            import datetime
            iat = d.get("indexed_at")
            iat_str = datetime.datetime.fromtimestamp(iat).strftime("%Y-%m-%d %H:%M:%S") if iat else "[NULL]"
            print(f"  ID: {doc_id[:60]}")
            print(f"  unit_code: '{d.get('unit_code')}'")
            print(f"  mapped_unit_code: '{d.get('mapped_unit_code')}'")
            print(f"  middle_unit: '{d.get('middle_unit')}'")
            print(f"  large_unit: '{d.get('large_unit')}'")
            print(f"  indexed_at: {iat_str}")
            print(f"  unit_code_locked: {d.get('unit_code_locked')}")
            break

