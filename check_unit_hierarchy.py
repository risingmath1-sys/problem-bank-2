"""unit_hierarchy.json 의 2015 vs 2022 코드 비교."""
import sys, io, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with (PROJECT_ROOT / "backend" / "unit_hierarchy.json").open(encoding="utf-8") as f:
    hier = json.load(f)

def walk(version):
    """Return dict {code: (subject, large, name)}"""
    out = {}
    for subj in hier.get(version, []):
        s = subj.get("subject")
        for large in subj.get("large_units", []):
            l = large.get("name")
            for m in large.get("medium_units", []):
                out[m["code"]] = (s, l, m["name"])
    return out

m2022 = walk("2022")
m2015 = walk("2015")

print("=== 2022 코드 ===")
for c in sorted(m2022.keys()):
    s, l, n = m2022[c]
    print(f"  {c}: {s} > {l} > {n}")

print("\n=== 2015 코드 ===")
for c in sorted(m2015.keys()):
    s, l, n = m2015[c]
    print(f"  {c}: {s} > {l} > {n}")

# 동일 코드 비교
print("\n=== 같은 코드인데 다른 단원? (2015 vs 2022) ===")
common = sorted(set(m2022.keys()) & set(m2015.keys()))
for c in common:
    n22 = m2022[c][2]
    n15 = m2015[c][2]
    if n22 != n15:
        print(f"  {c}: 2022='{n22}' / 2015='{n15}'  ← 다름!")
    # else: 같으므로 출력 생략

# 2022에만 있는 코드
print("\n=== 2022에만 있는 코드 ===")
only22 = sorted(set(m2022.keys()) - set(m2015.keys()))
for c in only22:
    print(f"  {c}: {m2022[c]}")

print("\n=== 2015에만 있는 코드 ===")
only15 = sorted(set(m2015.keys()) - set(m2022.keys()))
for c in only15:
    print(f"  {c}: {m2015[c]}")

