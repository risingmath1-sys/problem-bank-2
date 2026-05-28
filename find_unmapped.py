"""인덱싱 로그에서 매핑 실패한 [중단원] 텍스트 추출."""
import sys, io, json, re
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

log_path = PROJECT_ROOT / "backend" / "registration_log.json"
print(f"로그: {log_path}\n")

if not log_path.exists():
    print("로그 파일 없음.")
    sys.exit(1)

with log_path.open(encoding="utf-8") as f:
    data = json.load(f)

# data 구조 확인
print(f"로그 데이터 타입: {type(data).__name__}, 키 수: {len(data) if hasattr(data,'__len__') else '?'}")

# 매핑 없음 메시지 패턴: "[NAESIN_N] Problem N: 'XXX' → 매핑 없음"
pattern = re.compile(r"\[NAESIN_N\]\s*Problem\s*\d+:\s*'([^']+)'\s*→\s*매핑 없음")

unmapped = Counter()
total_logs = 0

def walk(obj):
    global total_logs
    if isinstance(obj, dict):
        for v in obj.values():
            walk(v)
    elif isinstance(obj, list):
        for item in obj:
            walk(item)
    elif isinstance(obj, str):
        total_logs += 1
        for m in pattern.finditer(obj):
            unmapped[m.group(1).strip()] += 1

walk(data)

print(f"\n총 문자열 로그: {total_logs}")
print(f"매핑 없음 케이스: {sum(unmapped.values())}건 / 고유 단원명: {len(unmapped)}개\n")

print("=== 매핑 실패 단원명 (빈도순) ===")
for name, n in unmapped.most_common(40):
    print(f"  [{n:4d}] '{name}'")

