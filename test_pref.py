"""선호도 라우트 디버깅."""
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

print("=== set_preference / get_preferences_bulk 직접 테스트 ===\n")
print(f"engine.set_preference: {hasattr(engine, 'set_preference')}")
print(f"engine.get_preferences_bulk: {hasattr(engine, 'get_preferences_bulk')}")
print()

# 어떤 test 가 있는지 확인 + 그 안의 problem_ids
print("=== 임의 saved_test 1개 조회 ===")
# saved_tests 컬렉션에서 최근 1개
import firebase_admin
from firebase_admin import firestore
db = firestore.client()
tests = list(db.collection("saved_tests").limit(2).stream())
if not tests:
    print("saved_tests 없음")
    sys.exit(0)

t = tests[0].to_dict()
print(f"Test ID (doc.id): {tests[0].id}")
print(f"user_id: {t.get('user_id')}")
print(f"problem_ids: {(t.get('problem_ids') or [])[:5]} ... (총 {len(t.get('problem_ids') or [])}개)")

# get_preferences_bulk 호출
pids = t.get('problem_ids') or []
uid = t.get('user_id')
if uid and pids:
    print(f"\n=== get_preferences_bulk(uid={uid}, pids[:5]={pids[:5]}) ===")
    try:
        pref_map = engine.get_preferences_bulk(uid, pids[:5])
        print(f"  결과: {pref_map}")
        print(f"  type: {type(pref_map).__name__}")
    except Exception as e:
        import traceback
        print(f"  ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()

# set_preference 시뮬레이션 (한 문제에 Good 설정)
if uid and pids:
    test_pid = str(pids[0])
    print(f"\n=== set_preference(uid={uid}, pid={test_pid[:50]}, value='Good') ===")
    try:
        engine.set_preference(uid, test_pid, "Good")
        print("  성공")
        # 다시 조회
        pref_map = engine.get_preferences_bulk(uid, [test_pid])
        print(f"  조회 결과: {pref_map}")
    except Exception as e:
        import traceback
        print(f"  ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()

