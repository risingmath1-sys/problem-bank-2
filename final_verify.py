"""최종 검증 + 메모리 정리."""
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
db_path = engine.db_path

# 새 connection 으로 SQLite 다시 조회
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== 최종 SQLite 캐시 상태 ===")
c.execute("SELECT COUNT(*) FROM problems")
print(f"전체 problems: {c.fetchone()[0]}건")

c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N'")
print(f"NAESIN_N: {c.fetchone()[0]}건")

print("\n=== NAESIN_N 수열/삼각함수 ===")
for code in ["J1","J2","J3","I1","I2","I3"]:
    c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N' AND unit_code=?", (code,))
    print(f"  {code}: {c.fetchone()[0]}건")

print("\n=== NAESIN_A 수열/삼각함수 ===")
for code in ["J1","J2","J3","I1","I2","I3"]:
    c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_A' AND unit_code=?", (code,))
    print(f"  {code}: {c.fetchone()[0]}건")

# 사용자 사용 패턴: NAESIN_N + 수열 + year=2025
print("\n=== 사용자 시나리오 ===")
c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N' AND unit_code IN ('J1','J2','J3')")
print(f"  NAESIN_N + 수열 전체: {c.fetchone()[0]}건")

c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N' AND unit_code IN ('J1','J2','J3') AND year='2025'")
print(f"  NAESIN_N + 수열 + year=2025: {c.fetchone()[0]}건")

conn.close()

# fetch_random_problems 한번 더
result = engine.fetch_random_problems(
    [{"filters": {"source": "NAESIN_N", "unit_code": {"in": ["J1","J2","J3"]}}, "qty": 100}],
    exclude_ids=[], include_excluded=False
)
print(f"\nfetch_random_problems(NAESIN_N + 수열, qty=100): {len(result)}건")

