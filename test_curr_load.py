"""_load_curriculum_subjects() 동작 확인."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from server.routes.pages import _load_curriculum_subjects
result = _load_curriculum_subjects()
print(f"타입: {type(result).__name__}")
print(f"비어있나: {not result}")
print(f"키 수: {len(result) if result else 0}")
print(f"내용: {result}")

import json
try:
    print(f"\ntojson 시뮬레이션: {json.dumps(result, ensure_ascii=False)[:200]}")
except Exception as e:
    print(f"\nJSON 직렬화 에러: {e}")
