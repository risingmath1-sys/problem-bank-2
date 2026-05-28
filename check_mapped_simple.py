#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys
from collections import Counter
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

cache_path = os.path.join(os.environ.get("APPDATA", ""), "naegiwangbank", "problems_cache.sqlite")
print(f"DB: {cache_path}\n")

conn = sqlite3.connect(f"file:{cache_path}?mode=ro", uri=True)
c = conn.cursor()

# 단순 SELECT로 데이터 가져와 Python에서 집계
print("="*90)
print("[1] mapped_unit_code 분포 (source별)")
print("="*90)

c.execute("SELECT source, mapped_unit_code FROM problems")
src_stats = {}
for src, m in c.fetchall():
    if src not in src_stats:
        src_stats[src] = {"total":0, "filled":0}
    src_stats[src]["total"] += 1
    if m and m != "":
        src_stats[src]["filled"] += 1

for src in sorted(src_stats.keys()):
    s = src_stats[src]
    pct = s["filled"]/s["total"]*100 if s["total"] else 0
    print(f"  {src}: 총 {s['total']}건 / mapped 채워진 것 {s['filled']}건 ({pct:.1f}%)")

# 2. mapped_unit_code 값 분포 (NAESIN_A + NAESIN_N)
print("\n"+"="*90)
print("[2] mapped_unit_code 값 분포 (NAESIN_A + NAESIN_N, 채워진 것만)")
print("="*90)

c.execute("SELECT mapped_unit_code FROM problems WHERE source IN ('NAESIN_A','NAESIN_N')")
counter = Counter()
for (m,) in c.fetchall():
    if m and m != "":
        counter[m] += 1

if counter:
    for code, cnt in counter.most_common(40):
        print(f"  '{code}': {cnt}건")
else:
    print("  (없음 — mapped_unit_code가 채워진 NAESIN 레코드 0건)")

# 3. NAESIN_A — curriculum별 분포
print("\n"+"="*90)
print("[3] NAESIN_A — curriculum 값 분포")
print("="*90)

c.execute("SELECT curriculum FROM problems WHERE source = 'NAESIN_A'")
curr_counter = Counter()
for (cur,) in c.fetchall():
    curr_counter[cur or "(빈값)"] += 1

for cur, cnt in curr_counter.most_common():
    print(f"  curriculum='{cur}': {cnt}건")

# 4. NAESIN_A year=2020 (확실한 2015 시기) 의 unit_code 분포
print("\n"+"="*90)
print("[4] NAESIN_A year=2020 자료의 unit_code 분포")
print("="*90)

c.execute("SELECT unit_code FROM problems WHERE source='NAESIN_A' AND year='2020'")
uc_counter = Counter()
for (uc,) in c.fetchall():
    uc_counter[uc or "(빈값)"] += 1

for uc, cnt in uc_counter.most_common(20):
    print(f"  {uc}: {cnt}건")

# 5. NAESIN_A year별 C1~C4, E1~E4 분포
print("\n"+"="*90)
print("[5] NAESIN_A year별 unit_code C/E 분포 (충돌 영역)")
print("="*90)

c.execute("SELECT year, unit_code FROM problems WHERE source='NAESIN_A' AND unit_code IN ('C1','C2','C3','C4','E1','E2','E3','E4')")
by_year = {}
for year, uc in c.fetchall():
    by_year.setdefault(year, Counter())[uc] += 1

print(f"  {'year':<6} | {'C1':<5} {'C2':<5} {'C3':<5} {'C4':<5} | {'E1':<5} {'E2':<5} {'E3':<5} {'E4':<5}")
print("  " + "-"*78)
for year in sorted(by_year.keys()):
    d = by_year[year]
    print(f"  {year:<6} | {d.get('C1',0):<5} {d.get('C2',0):<5} {d.get('C3',0):<5} {d.get('C4',0):<5} | "
          f"{d.get('E1',0):<5} {d.get('E2',0):<5} {d.get('E3',0):<5} {d.get('E4',0):<5}")

# 6. mapped_unit_code가 채워진 샘플
print("\n"+"="*90)
print("[6] mapped_unit_code 채워진 샘플 10개 (5-23 이전 흔적)")
print("="*90)

c.execute("SELECT file_name, year, grade, subject, curriculum, unit_code, mapped_unit_code, indexed_at FROM problems WHERE mapped_unit_code IS NOT NULL AND mapped_unit_code != '' LIMIT 10")
rows = c.fetchall()
if rows:
    for r in rows:
        ts = datetime.fromtimestamp(r[7]).strftime("%Y-%m-%d") if r[7] else "?"
        fname = (r[0] or "")[:50]
        print(f"  y={r[1]} g={r[2]} | {r[4]} | uc={r[5]} mapped={r[6]} | indexed={ts}")
        print(f"    {fname}")
else:
    print("  (mapped_unit_code 채워진 레코드 없음)")

# 7. NAESIN_A indexed_at 월별 분포 — 5-23 이전/이후
print("\n"+"="*90)
print("[7] NAESIN_A indexed_at 월별 분포 — mapped 채워진 비율")
print("="*90)

c.execute("SELECT indexed_at, mapped_unit_code FROM problems WHERE source='NAESIN_A' AND indexed_at IS NOT NULL")
by_ym = {}
for ts, m in c.fetchall():
    try:
        ym = datetime.fromtimestamp(ts).strftime("%Y-%m")
    except Exception:
        ym = "(invalid)"
    if ym not in by_ym:
        by_ym[ym] = {"total":0, "filled":0}
    by_ym[ym]["total"] += 1
    if m and m != "":
        by_ym[ym]["filled"] += 1

for ym in sorted(by_ym.keys()):
    s = by_ym[ym]
    pct = s["filled"]/s["total"]*100 if s["total"] else 0
    print(f"  {ym}: 총 {s['total']:>6}건 / mapped {s['filled']:>5}건 ({pct:5.1f}%)")

conn.close()
