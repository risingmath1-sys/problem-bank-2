"""행렬 빈값 → D1 즉시 일괄 갱신.

조건: NAESIN_N + unit_code 빈값 + 파일명에 "행렬" 포함
헬퍼: bulk_update_field (Firestore + 캐시 자동 동기화)
"""
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

from server.services.engine import get_engine
engine = get_engine()

# 1. 후보 수집: NAESIN_N + unit_code 빈값 + 파일명에 "행렬" 포함
import firebase_admin
from firebase_admin import firestore
db = firestore.client()

candidates = []
skipped = 0
for doc in db.collection("problems").where("source","==","NAESIN_N").stream():
    d = doc.to_dict()
    uc = d.get("unit_code") or ""
    if uc:
        continue  # 이미 매핑된 건 건너뜀
    fname = d.get("file_name") or ""
    if "행렬" not in fname:
        skipped += 1
        continue
    candidates.append({
        "id": doc.id,
        "unit_code": "D1",
        "middle_unit": "행렬의 뜻과 연산",
        "large_unit": "행렬",
    })

print(f"빈값 + 파일명에 '행렬' 포함: {len(candidates)}건 → D1 일괄 갱신")
print(f"(파일명에 '행렬' 없는 빈값 {skipped}건 → 별도 처리 필요)\n")

if not candidates:
    print("처리할 후보 없음.")
    sys.exit(0)

# 2. 샘플 미리보기
print("샘플 5건:")
for c in candidates[:5]:
    print(f"  {c['id'][:80]} → D1")

# 3. bulk_update_field 실행 (Firestore + 캐시 동시 갱신)
print(f"\n실행 중...")
import time
t0 = time.time()
ok = engine.bulk_update_field(candidates)
print(f"완료: {ok}/{len(candidates)}건 ({time.time()-t0:.1f}s)")

# 4. 검증
import sqlite3
conn = sqlite3.connect(engine.cache.cache_path)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N' AND unit_code='D1'")
print(f"\n[검증] 캐시 D1 카운트: {c.fetchone()[0]}건")
conn.close()

