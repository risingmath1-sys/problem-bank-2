#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

# 로컬 DB
conn = sqlite3.connect("file:G:/문제은행/문제은행2/problem_bank.db?mode=ro", uri=True)
c = conn.cursor()

# NAESIN_A + 2015 curriculum 자료
c.execute("""
    SELECT curriculum, unit_code, subject, year, grade, file_name
    FROM problems
    WHERE source = 'NAESIN_A'
""")
rows = c.fetchall()

# curriculum 분포
curr_cnt = Counter()
for r in rows:
    curr_cnt[r[0] or "(빈값)"] += 1

print("=" * 80)
print("[NAESIN_A] curriculum 분포")
print("=" * 80)
for k, v in curr_cnt.most_common():
    print(f"  '{k}': {v}건")

# 2015 자료만 추출
rows_2015 = [r for r in rows if r[0] and "2015" in r[0]]
print(f"\n2015 자료: {len(rows_2015)}건")

# 2015 자료의 unit_code 분포
print("\n" + "=" * 80)
print("[NAESIN_A + 2015 curriculum] unit_code 분포 (상위 30)")
print("=" * 80)

uc_cnt = Counter()
for r in rows_2015:
    uc_cnt[r[1] or "(빈값)"] += 1

for code, cnt in uc_cnt.most_common(30):
    print(f"  {code}: {cnt}건")

# 옛 코드 vs 새 코드 식별
# 옛 코드 중 새 체계에 없는 것: G1~G7 (확통-순열), H1~H3 (확통-확률), I1~I4 (확통-통계),
#                              J1~J5 (수1-지수로그), K1~K4 (수1-삼각), L1~L5 (수1-수열),
#                              M1~M2 (수2-극한), N1~N6 (수2-미분), O1~O4 (수2-적분),
#                              P1~P3 (미적-극한), Q1~Q5 (미적-미분), R1~R2 (미적-적분),
#                              S1~S4 (기하-이차곡선), T1~T3 (기하-벡터)
# 옛 코드 중 새 체계와 겹치는 의미 충돌: B4(고차vs여러가지방정식 - OK), C1~C4(평면좌표vs경우의수 - 충돌),
#                                       D1~D3(집합vs행렬 - 충돌), E1~E3(함수vs도형방정식 - 충돌),
#                                       F1~F3(경우의수vs집합 - 충돌)

# 새 체계 코드 (2022)
NEW_2022_CODES = set()
for L1 in "ABCDEFGHIJKLMNOPQRSTUV":
    for i in range(1, 9):
        NEW_2022_CODES.add(f"{L1}{i}")

# 옛 체계에만 있는 코드 = 변환 안 된 게 확실
# (G5,G6,G7, H3, I2, I4, J5, K3,K4, L4,L5, N4,N5,N6, O3,O4, P3, Q3,Q4,Q5, R2, S4, T3)
OLD_ONLY_CODES = {
    "G4","G5","G6","G7",   # 확통 (옛)
    "H3",                  # 확통 독립시행
    "I4",                  # 통계적 추정 (옛은 I4=통계적 추정, 새는 I4 없음)
    "J4","J5",             # 수1 로그함수, 지수로그활용
    "K3","K4",             # 삼각방정식, 삼각활용
    "L4","L5",             # 귀납적, 귀납법
    "N4","N5","N6",        # 수2 미분 후반
    "O3","O4",             # 정적분활용
    "P3",                  # 등비급수 도형
    "Q3","Q4","Q5",        # 미적 미분 후반
    "R2",                  # 미적 정적분 활용
    "S4",                  # 기하 접선
    "T3",                  # 평면도형 방정식
}

# 매핑 안 된 옛 코드 보유 NAESIN_A + 2015 카운트
old_in_2015 = Counter()
for r in rows_2015:
    if r[1] in OLD_ONLY_CODES:
        old_in_2015[r[1]] += 1

print("\n" + "=" * 80)
print("[변환 안 된 흔적] NAESIN_A + 2015 중 '새 체계에 없는' 옛 코드")
print("=" * 80)
if old_in_2015:
    for code, cnt in old_in_2015.most_common():
        print(f"  {code}: {cnt}건  ← 매핑 안 된 자료")
else:
    print("  (없음 — 모든 자료가 새 체계의 코드로 저장됨)")

# 샘플 5건
if old_in_2015:
    print("\n샘플 5건:")
    samples = [r for r in rows_2015 if r[1] in OLD_ONLY_CODES][:5]
    for r in samples:
        print(f"  uc={r[1]} | subject={r[2]} | year={r[3]} g={r[4]}")
        print(f"    {r[5][:70]}")

conn.close()
