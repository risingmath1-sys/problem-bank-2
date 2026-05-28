"""NAESIN_N 전수 조사 (UTF-8 파일 출력)."""
import sys
import json
import io
from pathlib import Path
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# stdout UTF-8 강제
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

import firebase_admin
from firebase_admin import firestore

db = firestore.client()
result = db.collection("problems").where("source", "==", "NAESIN_N").stream()
docs = [doc.to_dict() for doc in result]

out_lines = []
def W(s=""):
    out_lines.append(str(s))

W(f"=== NAESIN_N 전수 조사 (총 {len(docs)}건) ===\n")

# 1. grade/semester/curriculum별 분포
W("=" * 90)
W("[1] grade × semester × curriculum별 unit_code 분포")
W("=" * 90)

bucket = defaultdict(lambda: {"total": 0, "empty": 0, "z_code": 0})
for d in docs:
    year = str(d.get("year") or "?")
    grade = str(d.get("grade") or "?")
    sem = str(d.get("semester") or "?")
    curr = str(d.get("curriculum") or "?")
    unit = d.get("unit_code") or ""
    g_num = ''.join(c for c in grade if c.isdigit()) or "?"
    s_num = sem.split("학기")[0].strip() if "학기" in sem else "?"
    key = (year, g_num, s_num, curr)
    b = bucket[key]
    b["total"] += 1
    if not unit:
        b["empty"] += 1
    elif unit.startswith("Z"):
        b["z_code"] += 1

W(f"{'Year':<6} {'G':<3} {'S':<3} {'Curriculum':<14} {'Total':<7} {'Empty':<7} {'Z_Code':<7} {'Empty%':<7} {'Z%':<7}")
W("-" * 90)
for key in sorted(bucket.keys()):
    year, g, s, curr = key
    b = bucket[key]
    total = b["total"]
    e_pct = (b["empty"] * 100 / total) if total else 0
    z_pct = (b["z_code"] * 100 / total) if total else 0
    flag = "  <<< 의심" if e_pct > 5 or z_pct > 10 else ""
    W(f"{year:<6} {g:<3} {s:<3} {curr:<14} {total:<7} {b['empty']:<7} {b['z_code']:<7} {e_pct:>5.1f}% {z_pct:>5.1f}%{flag}")

# 2. 2025년 1학년 2학기 확인 (사용자 지목!)
W("\n" + "=" * 90)
W("[2] 2025 고1 2학기 NAESIN_N — 사용자가 400개 넘게 인덱싱했다고 함")
W("=" * 90)

g1_s2 = []
for d in docs:
    year = str(d.get("year") or "")
    grade = str(d.get("grade") or "")
    sem = str(d.get("semester") or "")
    g_num = ''.join(c for c in grade if c.isdigit())
    s_num = sem.split("학기")[0].strip() if "학기" in sem else ""
    if year == "2025" and g_num == "1" and s_num == "2":
        g1_s2.append(d)

W(f"2025년 고1 2학기 Firestore 건수: {len(g1_s2)}건")
if len(g1_s2) == 0:
    W("!!! 2학기 데이터가 Firestore에 0건 !!!")
    W("→ 사용자가 인덱싱한 400+ 시험지가 모두 다른 학기로 저장됐거나, 인덱싱 자체가 실패했음")

# semester 값 분포 (2025 G1)
W("\n2025 고1 semester 값 분포:")
sem_dist = Counter()
for d in docs:
    year = str(d.get("year") or "")
    grade = str(d.get("grade") or "")
    g_num = ''.join(c for c in grade if c.isdigit())
    if year == "2025" and g_num == "1":
        sem_dist[d.get("semester") or "[NULL]"] += 1
for s, n in sem_dist.most_common():
    W(f"  semester='{s}': {n}건")

# 3. 2025년 1학년 1학기 unit_code 분포 + 빈값/Z코드 파일 단원 키워드
W("\n" + "=" * 90)
W("[3] 2025 고1 1학기 unit_code 상세 분포")
W("=" * 90)

g1_s1 = [d for d in docs 
         if str(d.get("year") or "") == "2025" 
         and ''.join(c for c in str(d.get("grade") or "") if c.isdigit()) == "1"
         and (str(d.get("semester") or "").split("학기")[0].strip() == "1")]

W(f"Total: {len(g1_s1)}")
unit_dist = Counter()
for d in g1_s1:
    unit_dist[d.get("unit_code") or "[EMPTY]"] += 1

W("\nUnit_code 분포 (전체):")
for u, n in unit_dist.most_common():
    flag = ""
    if u.startswith("Z"):
        flag = "  ← BAD (중학교 코드)"
    elif u == "[EMPTY]":
        flag = "  ← EMPTY"
    W(f"  {u}: {n}{flag}")

# 4. 문제 있는 파일들의 파일명 (단원명 추출)
W("\n" + "=" * 90)
W("[4] 2025 고1 1학기 - unit_code 빈값/Z코드 파일들의 단원명")
W("=" * 90)

import re
empty_units = Counter()  # 파일명에서 추출한 단원명
z_units = Counter()
for d in g1_s1:
    unit = d.get("unit_code") or ""
    fname = d.get("file_name") or ""
    if not unit or unit.startswith("Z"):
        # 파일명에서 [...] 안의 항목 중 단원처럼 보이는 것 추출
        brackets = re.findall(r"\[([^\]]+)\]", fname)
        for b in brackets:
            # 단원 키워드 포함된 것만
            if any(kw in b for kw in ["식", "함수", "분", "수열", "확률", "통계", "도형", "방정", "부등", "행렬", "지수", "로그", "수렴", "미적", "벡터", "기하", "조합", "순열", "경우", "다항", "복소", "인수", "나머지"]):
                target = empty_units if not unit else z_units
                target[b] += 1

W(f"\n[EMPTY] unit_code 파일들의 단원명 키워드 (상위 30):")
for kw, n in empty_units.most_common(30):
    W(f"  [{n:4d}] {kw}")

W(f"\n[Z*] unit_code 파일들의 단원명 키워드 (상위 30):")
for kw, n in z_units.most_common(30):
    W(f"  [{n:4d}] {kw}")

# 5. 2025 고2, 고3 분포 — 사용자가 다른 학년도 인덱싱했을 수 있음
W("\n" + "=" * 90)
W("[5] 2025 고2, 고3 unit_code 분포 — 대수/수열 가능성")
W("=" * 90)

for target_grade in ["2", "3"]:
    docs_target = [d for d in docs 
                   if str(d.get("year") or "") == "2025" 
                   and ''.join(c for c in str(d.get("grade") or "") if c.isdigit()) == target_grade]
    W(f"\n2025 고{target_grade}: {len(docs_target)}건")
    unit_dist = Counter()
    for d in docs_target:
        unit_dist[d.get("unit_code") or "[EMPTY]"] += 1
    for u, n in unit_dist.most_common(20):
        flag = "  ← BAD" if u.startswith("Z") else ("  ← EMPTY" if u == "[EMPTY]" else "")
        W(f"  {u}: {n}{flag}")
    
    # 단원명 키워드
    keywords = Counter()
    for d in docs_target:
        unit = d.get("unit_code") or ""
        if not unit or unit.startswith("Z"):
            fname = d.get("file_name") or ""
            for m in re.findall(r"\[([^\]]+)\]", fname):
                if any(kw in m for kw in ["식", "함수", "분", "수열", "확률", "통계", "도형", "방정", "부등", "행렬", "지수", "로그", "수렴", "미적", "벡터", "기하", "조합", "순열", "경우", "다항", "복소", "인수"]):
                    keywords[m] += 1
    
    W(f"\n2025 고{target_grade} 문제 있는 파일의 단원명 키워드 (상위 20):")
    for kw, n in keywords.most_common(20):
        W(f"  [{n:4d}] {kw}")

# 파일로 저장
out_path = PROJECT_ROOT / "audit_report.txt"
out_path.write_text("\n".join(out_lines), encoding="utf-8")

# 콘솔에는 일부만
for line in out_lines[:80]:
    print(line)
print(f"\n... (전체 리포트: {out_path})")

