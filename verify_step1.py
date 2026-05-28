#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1 사전 검증:
  - NAESIN_A 현황 (오늘 인덱싱 포함)
  - subject 표기 일관성
  - 빈 subject 카운트
  - 기하 옛/새 구분 가능 여부
"""
import sqlite3, sys, time
from datetime import datetime, timedelta
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

DB = "file:G:/문제은행/문제은행2/problem_bank.db?mode=ro"
conn = sqlite3.connect(DB, uri=True)
c = conn.cursor()

# ─────────────────────────────────────────────────────────
# [1] NAESIN_A 현황
# ─────────────────────────────────────────────────────────
print("=" * 90)
print("[1] NAESIN_A 현황")
print("=" * 90)

c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_A'")
total_a = c.fetchone()[0]
print(f"  총 건수: {total_a:,}건")

# 오늘 인덱싱된 자료 (indexed_at 기준)
today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_A' AND indexed_at >= ?", (today_start,))
today_cnt = c.fetchone()[0]
print(f"  오늘 인덱싱: {today_cnt:,}건")

# 어제부터 오늘까지 (최근 24시간)
yest = (datetime.now() - timedelta(days=1)).timestamp()
c.execute("SELECT COUNT(*) FROM problems WHERE source='NAESIN_A' AND indexed_at >= ?", (yest,))
recent_24 = c.fetchone()[0]
print(f"  최근 24시간: {recent_24:,}건")

# 최근 인덱싱 일별 분포 (1주일)
week_ago = (datetime.now() - timedelta(days=7)).timestamp()
c.execute("""
    SELECT indexed_at FROM problems
    WHERE source='NAESIN_A' AND indexed_at >= ?
""", (week_ago,))
day_cnt = Counter()
for (ts,) in c.fetchall():
    if ts:
        d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        day_cnt[d] += 1
print("\n  최근 7일 일별 인덱싱:")
for d in sorted(day_cnt.keys()):
    print(f"    {d}: {day_cnt[d]:,}건")

# ─────────────────────────────────────────────────────────
# [2] subject 표기 일관성
# ─────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("[2] NAESIN_A subject 표기 분포")
print("=" * 90)

c.execute("SELECT subject FROM problems WHERE source='NAESIN_A'")
subj_cnt = Counter()
for (s,) in c.fetchall():
    subj_cnt[s if s else "(빈값)"] += 1

for subj, cnt in subj_cnt.most_common():
    print(f"  '{subj}': {cnt:,}건")

# ─────────────────────────────────────────────────────────
# [3] subject별 curriculum 매트릭스
# ─────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("[3] subject × curriculum 매트릭스 (NAESIN_A)")
print("=" * 90)

c.execute("SELECT subject, curriculum FROM problems WHERE source='NAESIN_A'")
matrix = {}
for s, cur in c.fetchall():
    key = (s or "(빈)", cur or "(빈)")
    matrix[key] = matrix.get(key, 0) + 1

# subject별로 모음
by_subj = {}
for (s, cur), cnt in matrix.items():
    by_subj.setdefault(s, {})[cur] = cnt

for s in sorted(by_subj.keys()):
    print(f"\n  subject = '{s}'")
    for cur, cnt in sorted(by_subj[s].items(), key=lambda x: -x[1]):
        print(f"    curriculum = '{cur}': {cnt}건")

# ─────────────────────────────────────────────────────────
# [4] '기하' subject — 옛/새 구분 가능성
# ─────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("[4] '기하' subject의 옛/새 구분 (curriculum + year + grade + unit_code)")
print("=" * 90)

c.execute("""
    SELECT curriculum, year, grade, unit_code
    FROM problems
    WHERE source='NAESIN_A' AND subject='기하'
""")
giha = c.fetchall()
print(f"  '기하' 총 {len(giha)}건")

# curriculum 분포
giha_curr = Counter()
for r in giha:
    giha_curr[r[0] or "(빈)"] += 1
print("\n  curriculum 분포:")
for cur, cnt in giha_curr.most_common():
    print(f"    '{cur}': {cnt}건")

# year-grade 별
print("\n  year별 분포 (year-grade 기준 옛/새 판단):")
yr_grade = Counter()
for r in giha:
    try:
        yr = int(r[1]) if r[1] else None
        gr_str = str(r[2] or "")
        # "고1"→1, "고2"→2 등
        gr = int(''.join(filter(str.isdigit, gr_str))) if any(ch.isdigit() for ch in gr_str) else None
        if yr and gr is not None:
            era = "2022(new)" if (yr - gr >= 2024) else "2015(old)"
            yr_grade[(yr, gr, era)] += 1
    except Exception:
        pass

for (yr, gr, era), cnt in sorted(yr_grade.items()):
    print(f"    year={yr}, grade=고{gr} → {era}: {cnt}건")

# 기하의 unit_code 분포 (S, T, U, V 코드)
giha_uc = Counter()
for r in giha:
    giha_uc[r[3] or "(빈)"] += 1
print("\n  unit_code 분포:")
for uc, cnt in giha_uc.most_common(20):
    print(f"    {uc}: {cnt}건")

# ─────────────────────────────────────────────────────────
# [5] 옛 과목 (수학(상)/(하)/1/2/미적분/확률과 통계) — unit_code 풀
# ─────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("[5] 옛 과목별 unit_code 풀 (변환 대상 식별용)")
print("=" * 90)

OLD_SUBJECTS = ['수학(상)', '수학(하)', '수학1', '수학2', '미적분', '확률과 통계',
                '수학상', '수학하']  # 변종 포함

for s in OLD_SUBJECTS:
    c.execute("""
        SELECT unit_code, COUNT(*)
        FROM problems
        WHERE source='NAESIN_A' AND subject = ?
        GROUP BY unit_code
        ORDER BY COUNT(*) DESC
    """, (s,))
    rows = c.fetchall()
    if rows:
        print(f"\n  '{s}': {sum(r[1] for r in rows)}건")
        codes = ", ".join(f"{r[0]}({r[1]})" for r in rows[:15] if r[0])
        print(f"    상위 코드: {codes}")

# ─────────────────────────────────────────────────────────
# [6] 새 과목 — 코드 풀
# ─────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("[6] 새 과목별 unit_code 풀 (변환 안 함 — 보존 대상)")
print("=" * 90)

NEW_SUBJECTS = ['공통수학1', '공통수학2', '대수', '미적분I', '확률과통계', '미적분II']

for s in NEW_SUBJECTS:
    c.execute("""
        SELECT unit_code, COUNT(*)
        FROM problems
        WHERE source='NAESIN_A' AND subject = ?
        GROUP BY unit_code
        ORDER BY COUNT(*) DESC
    """, (s,))
    rows = c.fetchall()
    if rows:
        print(f"\n  '{s}': {sum(r[1] for r in rows)}건")
        codes = ", ".join(f"{r[0]}({r[1]})" for r in rows[:15] if r[0])
        print(f"    상위 코드: {codes}")

conn.close()
print("\n" + "=" * 90)
print("[검증 완료]")
print("=" * 90)
