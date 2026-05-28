"""grade 값 정확히 분리해서 분석."""
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

import firebase_admin
from firebase_admin import firestore

db = firestore.client()
result = db.collection("problems").where("source", "==", "NAESIN_N").stream()
docs = [doc.to_dict() for doc in result]

# grade 값 정확 분포
grade_dist = Counter()
for d in docs:
    grade_dist[d.get("grade") or "[NULL]"] += 1

print("=== NAESIN_N grade 값 정확 분포 ===")
for g, n in grade_dist.most_common():
    print(f"  '{g}' (repr={g!r}): {n}건")

# 2025 + 1학기 + 기말 + grade='고1' 정확 매칭
target = []
for d in docs:
    if (str(d.get("year") or "") == "2025"
        and d.get("grade") == "고1"
        and d.get("semester") == "1학기"
        and d.get("exam_type") == "기말고사"):
        target.append(d)

print(f"\n=== 2025 grade='고1' semester='1학기' exam='기말고사' ===")
print(f"건수: {len(target)}건")

files = set(d.get("file_name") or "" for d in target)
print(f"시험지: {len(files)}개")

# unit_code 분포
unit_dist = Counter()
for d in target:
    unit_dist[d.get("unit_code") or "[EMPTY]"] += 1

print("\nunit_code 분포:")
for u, n in unit_dist.most_common():
    flag = ""
    if u.startswith("Z"):
        flag = "  ← 중학교 코드 (이상!)"
    elif u == "[EMPTY]":
        flag = "  ← EMPTY"
    print(f"  {u}: {n}{flag}")

# 빈값/Z* 파일들
print("\n=== 빈값/Z코드 파일명 ===")
problem_files = Counter()
for d in target:
    unit = d.get("unit_code") or ""
    if not unit or unit.startswith("Z"):
        problem_files[d.get("file_name") or ""] += 1

for fname, n in problem_files.most_common(30):
    print(f"  [{n:3d}] {fname[:110]}")

# 빈값/Z* 파일들의 단원명 키워드
print("\n=== 문제 있는 고1 파일의 단원명 키워드 ===")
kw_cnt = Counter()
for d in target:
    unit = d.get("unit_code") or ""
    if not unit or unit.startswith("Z"):
        fname = d.get("file_name") or ""
        for b in re.findall(r"\[([^\]]+)\]", fname):
            if any(k in b for k in ["식","함수","분","수열","확률","통계","도형","방정","부등","행렬","지수","로그","미적","벡터","기하","조합","순열","경우","다항","복소","인수","나머지","대수"]):
                kw_cnt[b] += 1

for kw, n in kw_cnt.most_common(30):
    print(f"  [{n:4d}] {kw}")

