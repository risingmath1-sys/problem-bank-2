"""Firestore → SQLite 캐시 동기화 (복구 후 캐시 refresh)."""
import sys, io, time
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
print(f"Engine: {type(engine).__name__}")
print(f"Cache engine: {type(engine.cache_engine).__name__ if hasattr(engine, 'cache_engine') else 'N/A'}")
print(f"\nresync_cache 호출...")
t0 = time.time()
try:
    engine.resync_cache()
    print(f"OK ({time.time()-t0:.1f}s)")
except Exception as e:
    print(f"force_full_resync 시도...")
    engine.force_full_resync()
    print(f"OK ({time.time()-t0:.1f}s)")

# 검증
print("\n=== 캐시 재동기화 후 fetch_random_problems 재시도 ===")
for desc, filters in [
    ("NAESIN_N + J1", {"source": "NAESIN_N", "unit_code": "J1"}),
    ("NAESIN_N + J1/J2/J3", {"source": "NAESIN_N", "unit_code": {"in": ["J1","J2","J3"]}}),
    ("NAESIN_N + I1/I2/I3", {"source": "NAESIN_N", "unit_code": {"in": ["I1","I2","I3"]}}),
]:
    result = engine.fetch_random_problems([{"filters": filters, "qty": 10}], exclude_ids=[], include_excluded=False)
    print(f"  [{desc}] → {len(result)}건")

