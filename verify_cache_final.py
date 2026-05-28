#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""변환 후 캐시 DB 최종 검증."""
import sqlite3, os, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

cache = os.path.join(os.environ.get("APPDATA",""), "naegiwangbank", "problems_cache.sqlite")
conn = sqlite3.connect(f"file:{cache}?mode=ro", uri=True)
c = conn.cursor()

# 무결성
c.execute("PRAGMA integrity_check")
integ = c.fetchone()[0]
print(f"[무결성] {integ}")

# NAESIN_A curriculum 분포
print("\n[NAESIN_A curriculum 분포]")
c.execute("SELECT curriculum, COUNT(*) FROM problems WHERE source='NAESIN_A' GROUP BY curriculum")
for cur, cnt in c.fetchall():
    print(f"  '{cur}': {cnt}건")

# 핵심 단원 검증 — 경우의수, 점과좌표, 부정적분
print("\n[경우의수 (C1) 검증 — 옛 도형의 방정식 문제 없어야]")
c.execute("""
    SELECT subject, middle_unit, COUNT(*)
    FROM problems
    WHERE source='NAESIN_A' AND unit_code='C1'
    GROUP BY subject, middle_unit
""")
for s, m, cnt in c.fetchall():
    marker = "  ⚠" if ("도형" in (m or "") or "좌표" in (m or "")) else "  ✓"
    print(f"{marker} subject={s:<14} middle={m:<22} {cnt}건")

print("\n[점과 좌표 (E1) 검증]")
c.execute("""
    SELECT subject, middle_unit, COUNT(*)
    FROM problems
    WHERE source='NAESIN_A' AND unit_code='E1'
    GROUP BY subject, middle_unit
""")
for s, m, cnt in c.fetchall():
    print(f"  ✓ subject={s:<14} middle={m:<22} {cnt}건")

print("\n[부정적분 (M1) 검증]")
c.execute("""
    SELECT subject, middle_unit, COUNT(*)
    FROM problems
    WHERE source='NAESIN_A' AND unit_code='M1'
    GROUP BY subject, middle_unit
""")
for s, m, cnt in c.fetchall():
    print(f"  ✓ subject={s:<14} middle={m:<22} {cnt}건")

print("\n[함수의 극한 (K1) 검증]")
c.execute("""
    SELECT subject, middle_unit, COUNT(*)
    FROM problems
    WHERE source='NAESIN_A' AND unit_code='K1'
    GROUP BY subject, middle_unit
""")
for s, m, cnt in c.fetchall():
    print(f"  ✓ subject={s:<14} middle={m:<22} {cnt}건")

# 전체 unit_code top 20
print("\n[NAESIN_A unit_code top 20]")
c.execute("""
    SELECT unit_code, COUNT(*) cnt
    FROM problems WHERE source='NAESIN_A'
    GROUP BY unit_code
    ORDER BY cnt DESC LIMIT 20
""")
for uc, cnt in c.fetchall():
    print(f"  {uc or '(빈)'}: {cnt}건")

# 변환된 흔적 확인 — mapped_unit_code 채워진 것
print("\n[mapped_unit_code 채워진 카운트 (변환 흔적)]")
c.execute("""
    SELECT COUNT(*) FROM problems
    WHERE source='NAESIN_A' AND mapped_unit_code IS NOT NULL AND mapped_unit_code != ''
""")
print(f"  mapped 채워진 NAESIN_A: {c.fetchone()[0]}건")

conn.close()
