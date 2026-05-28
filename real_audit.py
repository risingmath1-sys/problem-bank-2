"""middle_unit (인덱싱 시 단원명) vs unit_code 일치성 검증."""
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

with (PROJECT_ROOT / "backend" / "unit_hierarchy.json").open(encoding="utf-8") as f:
    hier = json.load(f)
code_to_name = {}
for version in ["2022", "2015"]:
    for subj in hier.get(version, []):
        for large in subj.get("large_units", []):
            for med in large.get("medium_units", []):
                code = med["code"]
                name = med["name"]
                if code not in code_to_name:
                    code_to_name[code] = []
                if name not in code_to_name[code]:
                    code_to_name[code].append(name)

from server.services.engine import get_engine
engine = get_engine()
import sqlite3
conn = sqlite3.connect(engine.cache.cache_path)
c = conn.cursor()

print("=== unit_code 별 middle_unit 분포 (NAESIN_N) ===\n")
mismatch_codes = []
for code in sorted(code_to_name.keys()):
    c.execute("SELECT middle_unit FROM problems WHERE source='NAESIN_N' AND unit_code=?", (code,))
    rows = c.fetchall()
    total = len(rows)
    if total == 0:
        continue
    mu_dist = Counter((r[0] or "[NULL]") for r in rows)
    main_mu = mu_dist.most_common(3)
    expected = code_to_name[code]
    main_str = " | ".join(f"'{m}'({n})" for m, n in main_mu)
    top_match = main_mu[0][0] in expected if main_mu else False
    flag = "OK" if top_match else "MISMATCH"
    if not top_match:
        mismatch_codes.append((code, main_mu[0][0] if main_mu else "", total))
    print(f"{code:<4} expected={expected[0][:25]:<28} total={total:<6} top: {main_str[:80]}  [{flag}]")

print(f"\n\n=== 결론: MISMATCH 발견 {len(mismatch_codes)}개 ===")
for code, actual_mu, total in mismatch_codes:
    print(f"  {code} (정상: {code_to_name[code][0]}) ← 실제 middle_unit: '{actual_mu}' / {total}건")

conn.close()
