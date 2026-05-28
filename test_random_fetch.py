"""서버의 fetch_random_problems 함수를 직접 호출해서 0건 원인 추적."""
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

from server.services.engine import get_engine

engine = get_engine()
print(f"Engine type: {type(engine).__name__}")

# 사용자 시나리오 1: NAESIN_N + 수열 J1
print("\n[1] NAESIN_N + unit_code=J1 (10건 요청)")
filters = {"source": "NAESIN_N", "unit_code": "J1"}
try:
    result = engine.fetch_random_problems([{"filters": filters, "qty": 10}], exclude_ids=[], include_excluded=False)
    print(f"  결과: {len(result)}건")
    for p in result[:3]:
        print(f"    id={p.get('id', '?')[:50]}, unit_code={p.get('unit_code')}, year={p.get('year')}, source={p.get('source')}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")
    import traceback; traceback.print_exc()

# 시나리오 2: in J1/J2/J3
print("\n[2] NAESIN_N + unit_code IN [J1,J2,J3] (10건 요청)")
filters = {"source": "NAESIN_N", "unit_code": {"in": ["J1","J2","J3"]}}
try:
    result = engine.fetch_random_problems([{"filters": filters, "qty": 10}], exclude_ids=[], include_excluded=False)
    print(f"  결과: {len(result)}건")
    for p in result[:3]:
        print(f"    unit_code={p.get('unit_code')}, year={p.get('year')}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")

# 시나리오 3: count_problems 메소드 있다면 사용
print("\n[3] engine.count_problems 호출")
try:
    cnt = engine.count_problems({"source": "NAESIN_N", "unit_code": "J1"})
    print(f"  J1 count: {cnt}")
except AttributeError:
    print(f"  count_problems 메소드 없음")
except Exception as e:
    print(f"  ERROR: {e}")

# 시나리오 4: engine 의 메소드 리스트
print("\n[4] Engine 메소드:")
for m in sorted(dir(engine)):
    if not m.startswith("_"):
        print(f"  - {m}")

