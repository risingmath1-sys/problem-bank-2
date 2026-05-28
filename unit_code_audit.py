"""각 unit_code 의 실제 데이터가 단원과 일치하는지 검증."""
import sys, io, re
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

from server.services.engine import get_engine
engine = get_engine()

import sqlite3
conn = sqlite3.connect(engine.cache.cache_path)
c = conn.cursor()

# unit_code 별 파일명 분석 — 경우의 수(C1) 의심부터
# 정상: C1(경우의수) 시험지에는 파일명에 "경우의수/순열/조합" 같은 키워드
EXPECTED = {
    "A1": ["다항식의연산", "다항식"],
    "A2": ["나머지정리", "항등식"],
    "A3": ["인수분해"],
    "B1": ["복소수"],
    "B2": ["이차방정식"],
    "B3": ["이차함수"],
    "B4": ["여러가지방정식", "고차방정식", "연립방정식"],
    "B5": ["여러가지부등식", "절대부등식", "부등식"],
    "C1": ["경우의수"],
    "C2": ["순열"],
    "C3": ["조합"],
    "D1": ["행렬"],
    "E1": ["점과좌표", "평면좌표", "도형의방정식"],
    "E2": ["직선의방정식"],
    "E3": ["원의방정식"],
    "E4": ["도형의이동"],
    "H1": ["지수"],
    "H2": ["로그"],
    "I1": ["삼각함수"],
    "J1": ["등차수열", "등비수열", "수열"],
    "J2": ["수열의합"],
    "J3": ["귀납법"],
}

print("=== unit_code vs 파일명 키워드 정합성 검사 (NAESIN_N) ===\n")
print(f"{'Code':<6} {'예상 키워드':<30} {'총건수':<8} {'매치%':<10} {'주요 불일치 파일명':<60}")
print("-" * 130)

for code, kws in EXPECTED.items():
    c.execute("SELECT file_name FROM problems WHERE source='NAESIN_N' AND unit_code=?", (code,))
    rows = c.fetchall()
    total = len(rows)
    if total == 0:
        continue
    match = 0
    mismatch_files = Counter()
    for (fname,) in rows:
        f_norm = re.sub(r"[\s,]", "", fname or "")
        if any(kw in f_norm for kw in kws):
            match += 1
        else:
            # 파일명에서 [ ] 마지막 (단원범위 표시) 추출
            brackets = re.findall(r"\[([^\]]+)\]", fname or "")
            mismatch_key = brackets[-1] if brackets else fname[:50]
            mismatch_files[mismatch_key] += 1
    pct = match * 100.0 / total
    flag = "  ⚠️" if pct < 80 else ("  🔴" if pct < 50 else "")
    main_mm = mismatch_files.most_common(1)[0] if mismatch_files else ("", 0)
    print(f"{code:<6} {','.join(kws)[:28]:<30} {total:<8} {pct:>5.1f}%{flag:<5} {main_mm[0][:55]}({main_mm[1]})")

conn.close()
