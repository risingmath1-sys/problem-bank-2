"""middle_unit + large_unit 일괄 정상화 (unit_code 기준)."""
import sys, io, json
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

# unit_code → (middle_unit, large_unit) 정답표 (2022 우선)
with (PROJECT_ROOT / "backend" / "unit_hierarchy.json").open(encoding="utf-8") as f:
    hier = json.load(f)

code_info = {}  # {code: (middle, large)}
for version in ["2022", "2015"]:  # 2022 먼저 → 우선권
    for subj in hier.get(version, []):
        for large in subj.get("large_units", []):
            l_name = large.get("name", "")
            for med in large.get("medium_units", []):
                code = med["code"]
                if code not in code_info:
                    code_info[code] = (med.get("name", ""), l_name)

print(f"정답표: {len(code_info)}개 unit_code")

from server.services.engine import get_engine
engine = get_engine()
import sqlite3

# 캐시에서 어긋난 데이터 찾기 (NAESIN_N + NAESIN_A)
conn = sqlite3.connect(engine.cache.cache_path)
c = conn.cursor()

updates = []
for code, (correct_mu, correct_lu) in code_info.items():
    c.execute(
        "SELECT id, middle_unit, large_unit FROM problems "
        "WHERE unit_code=? AND source IN ('NAESIN_N','NAESIN_A','SUNEUNG_SPECIAL','SUNEUNG_COMPLETE','MOCK_EXAM') "
        "AND (middle_unit != ? OR large_unit != ?)",
        (code, correct_mu, correct_lu),
    )
    for (pid, cur_mu, cur_lu) in c.fetchall():
        updates.append({
            "id": pid,
            "middle_unit": correct_mu,
            "large_unit": correct_lu,
        })
conn.close()

print(f"\n어긋난 데이터: {len(updates)}건")
if not updates:
    print("정상!")
    sys.exit(0)

# 패턴 분석
by_code = Counter()
for u in updates:
    by_code[u["middle_unit"]] += 1
print("\n갱신할 middle_unit 분포 (상위 10):")
for mu, n in by_code.most_common(10):
    print(f"  {mu}: {n}건")

# bulk_update_field 실행 (Firestore + 캐시 동시 갱신)
print(f"\n실행 중...")
import time
t0 = time.time()
ok = engine.bulk_update_field(updates)
print(f"완료: {ok}/{len(updates)}건 ({time.time()-t0:.1f}s)")

# 검증
conn = sqlite3.connect(engine.cache.cache_path)
c = conn.cursor()
print("\n=== 검증 (어긋난 케이스 잔여) ===")
remaining = 0
for code, (correct_mu, correct_lu) in code_info.items():
    c.execute(
        "SELECT COUNT(*) FROM problems "
        "WHERE unit_code=? AND (middle_unit != ? OR large_unit != ?)",
        (code, correct_mu, correct_lu),
    )
    n = c.fetchone()[0]
    if n > 0:
        remaining += n
        print(f"  {code}: {n}건 아직 어긋남")
print(f"\n총 잔여: {remaining}건")
conn.close()

