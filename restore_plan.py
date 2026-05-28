"""복구 계획 분석 — 어떤 문서를 어떻게 복구할지 미리 확인."""
import sys, io
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass
import firebase_admin
from firebase_admin import firestore
db = firestore.client()

print("=== 복구 대상 분석 ===\n")

# 전체 problems 컬렉션
all_total = 0
need_restore = 0       # unit_code != mapped_unit_code AND mapped_unit_code 있음 → 복구 가능
already_identity = 0   # unit_code == mapped_unit_code  → 정상 (또는 mapped 비어있고 unit_code 있음)
empty_both = 0         # unit_code == "" AND mapped == "" → 빈값

# 복구 대상 (unit_code, mapped_unit_code) 변화 통계
restore_pairs = Counter()
by_source = Counter()

for doc in db.collection("problems").stream():
    d = doc.to_dict()
    all_total += 1
    uc = d.get("unit_code") or ""
    mc = d.get("mapped_unit_code") or ""
    src = d.get("source") or "?"
    
    if mc and uc != mc:
        need_restore += 1
        restore_pairs[(uc, mc)] += 1
        by_source[src] += 1
    elif not uc and not mc:
        empty_both += 1
    else:
        already_identity += 1

print(f"전체 problems: {all_total}건")
print(f"  복구 대상 (unit_code != mapped_unit_code): {need_restore}건")
print(f"  정상/identity: {already_identity}건")
print(f"  unit_code+mapped 모두 빈값: {empty_both}건")

print(f"\n복구 대상 source 분포:")
for src, n in by_source.most_common():
    print(f"  {src}: {n}건")

print(f"\n복구 매핑 패턴 상위 25 (현재 → 복구 후):")
for (uc, mc), n in restore_pairs.most_common(25):
    print(f"  {uc} → {mc}: {n}건")

