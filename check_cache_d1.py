"""캐시에 D1이 있는지 직접 확인 + 서버 fetch 시뮬레이션."""
import sys, io, sqlite3
from pathlib import Path

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
cache_path = engine.cache.cache_path
print(f"cache: {cache_path}\n")

conn = sqlite3.connect(cache_path)
c = conn.cursor()

# NAESIN_N D1 캐시 카운트
c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N' AND unit_code='D1'")
cache_d1 = c.fetchone()[0]

# Firestore D1 (engine 통해서 검증)
print(f"[캐시] NAESIN_N + D1: {cache_d1}건")

# 2025 고1 1학기 기말 D1 (캐시)
c.execute("""SELECT COUNT(*) FROM problems 
             WHERE source='NAESIN_N' AND unit_code='D1'
             AND year='2025' AND grade='고1' AND semester='1학기' AND exam_type='기말고사'""")
print(f"[캐시] 2025 고1 1학기 기말 + D1: {c.fetchone()[0]}건")

# 빈값 카운트 (캐시)
c.execute("""SELECT COUNT(*) FROM problems 
             WHERE source='NAESIN_N'
             AND year='2025' AND grade='고1' AND semester='1학기' AND exam_type='기말고사'
             AND (unit_code IS NULL OR unit_code='')""")
print(f"[캐시] 2025 고1 1학기 기말 NAESIN_N 빈값: {c.fetchone()[0]}건")

conn.close()

# fetch_random_problems 직접 호출
print("\n=== fetch_random_problems(NAESIN_N + D1) ===")
result = engine.fetch_random_problems(
    [{"filters": {"source": "NAESIN_N", "unit_code": "D1"}, "qty": 5}],
    exclude_ids=[], include_excluded=False
)
print(f"결과: {len(result)}건")
for p in result[:3]:
    print(f"  id={p.get('id', '')[:60]}, unit_code={p.get('unit_code')}, year={p.get('year')}")

