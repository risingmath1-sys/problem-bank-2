"""SQLite 캐시 직접 확인 + force_full_resync."""
import sys, io, time, sqlite3
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
db_path = engine.db_path if hasattr(engine, 'db_path') else None
print(f"SQLite cache: {db_path}")

# 캐시 DB 직접 조회
if db_path and Path(db_path).exists():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("\n=== SQLite 캐시 직접 조회: NAESIN_N J1/J2/J3 ===")
    for code in ["J1","J2","J3"]:
        c.execute("SELECT COUNT(*) FROM problems WHERE source=? AND unit_code=?", ("NAESIN_N", code))
        print(f"  {code}: {c.fetchone()[0]}건")
    
    print("\n=== SQLite 캐시: NAESIN_N + H1/H2/H3 (원래 잘못된 매핑) ===")
    for code in ["H1","H2","H3"]:
        c.execute("SELECT COUNT(*) FROM problems WHERE source=? AND unit_code=?", ("NAESIN_N", code))
        print(f"  {code}: {c.fetchone()[0]}건 ← 잘못된 코드 (복구 전)")
    
    print("\n=== SQLite 캐시: NAESIN_N + P/O (원래 잘못된 매핑) ===")
    for code in ["P1","P2","O1","O2"]:
        c.execute("SELECT COUNT(*) FROM problems WHERE source=? AND unit_code=?", ("NAESIN_N", code))
        print(f"  {code}: {c.fetchone()[0]}건")
    
    c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_N'")
    print(f"\n캐시의 NAESIN_N 총: {c.fetchone()[0]}건")
    
    conn.close()

# force_full_resync 호출
print("\n=== force_full_resync 호출 (전체 재동기화) ===")
t0 = time.time()
try:
    engine.force_full_resync()
    print(f"OK ({time.time()-t0:.1f}s)")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback; traceback.print_exc()

# 재검증
print("\n=== 강제 재동기화 후 ===")
if db_path and Path(db_path).exists():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    for code in ["J1","J2","J3"]:
        c.execute("SELECT COUNT(*) FROM problems WHERE source=? AND unit_code=?", ("NAESIN_N", code))
        print(f"  J*: {code}: {c.fetchone()[0]}건")
    conn.close()

for desc, filters in [
    ("NAESIN_N + J1", {"source": "NAESIN_N", "unit_code": "J1"}),
    ("NAESIN_N + J1/J2/J3", {"source": "NAESIN_N", "unit_code": {"in": ["J1","J2","J3"]}}),
]:
    result = engine.fetch_random_problems([{"filters": filters, "qty": 5}], exclude_ids=[], include_excluded=False)
    print(f"  fetch [{desc}] → {len(result)}건")

