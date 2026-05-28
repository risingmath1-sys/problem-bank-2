"""부팅 정합성 검사 동작 확인."""
import sys, io
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

# verbose=True 로 새 엔진 직접 생성 (부팅 시뮬레이션)
from backend.data_engine import make_engine
print("=== 부팅 정합성 검사 시뮬레이션 (verbose=True) ===\n")
engine = make_engine(local_db_path=str(PROJECT_ROOT / "problem_bank.db"), verbose=True)
print(f"\n결과 캐시 count: {engine.cache.count()}")

# bulk_update_field 메서드 확인
print(f"\nbulk_update_field 메서드 존재: {hasattr(engine, 'bulk_update_field')}")

