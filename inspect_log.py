"""로그 구조 직접 검사."""
import sys, io, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

log_path = PROJECT_ROOT / "backend" / "registration_log.json"
with log_path.open(encoding="utf-8") as f:
    data = json.load(f)

print(f"키 샘플 (3개):")
for k in list(data.keys())[:3]:
    print(f"  '{k[:80]}'")
    v = data[k]
    print(f"    타입: {type(v).__name__}")
    if isinstance(v, dict):
        print(f"    필드: {list(v.keys())}")
    elif isinstance(v, list):
        print(f"    길이: {len(v)}, 첫 요소: {str(v[0])[:100] if v else 'empty'}")
    elif isinstance(v, str):
        print(f"    값(앞 200자): {v[:200]}")
    print()

# "행렬" 포함 키워드 검색
print("\n=== '행렬' 또는 '매핑' 포함 항목 검색 ===")
found = 0
for k, v in list(data.items())[:500]:
    if isinstance(v, dict):
        for fk, fv in v.items():
            if isinstance(fv, str) and ("행렬" in fv or "매핑 없음" in fv or "NAESIN_N" in fv):
                if found < 5:
                    print(f"  [{k[:60]}] {fk}: {fv[:200]}")
                    found += 1

# log 라는 키가 있는지
if data and isinstance(list(data.values())[0], dict):
    sample = list(data.values())[0]
    if 'log' in sample or 'logs' in sample:
        log_key = 'log' if 'log' in sample else 'logs'
        # 첫 항목의 log 필드 추출
        first_key = list(data.keys())[0]
        log_content = data[first_key].get(log_key)
        print(f"\n첫 항목 '{first_key[:50]}'의 {log_key} 필드:")
        if isinstance(log_content, list):
            for line in log_content[:30]:
                print(f"  {line[:150]}")
        elif isinstance(log_content, str):
            print(log_content[:1500])

