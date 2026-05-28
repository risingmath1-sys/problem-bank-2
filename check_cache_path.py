"""실제 캐시 파일 경로 + 강제 재구축."""
import sys, io, sqlite3, time
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

print(f"local_db_path (개인데이터): {engine.db_path}")
print(f"cache.cache_path (problems 캐시): {engine.cache.cache_path}")
print(f"cache count: {engine.cache.count()}")

# 진짜 캐시 파일 직접 조회
cache_path = engine.cache.cache_path
conn = sqlite3.connect(cache_path)
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM problems")
print(f"\n=== 진짜 캐시 ({cache_path}) ===")
print(f"전체 problems: {c.fetchone()[0]}건")

c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N'")
print(f"NAESIN_N: {c.fetchone()[0]}건")

for code in ["J1","J2","J3","I1","I2","I3"]:
    c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N' AND unit_code=?", (code,))
    print(f"  NAESIN_N + {code}: {c.fetchone()[0]}건")

conn.close()

