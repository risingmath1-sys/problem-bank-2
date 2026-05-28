"""2025 고1 1학기 기말고사 NAESIN_N 정확 분석."""
import sys
import io
import re
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

# 2025 고1 1학기 기말고사만
target = []
for d in docs:
    year = str(d.get("year") or "")
    grade = str(d.get("grade") or "")
    sem = str(d.get("semester") or "")
    exam = str(d.get("exam_type") or "")
    g_num = ''.join(c for c in grade if c.isdigit())
    s_num = sem.split("학기")[0].strip() if "학기" in sem else ""
    if year == "2025" and g_num == "1" and s_num == "1" and exam == "기말고사":
        target.append(d)

print(f"=== 2025 고1 1학기 기말고사 NAESIN_N ({len(target)}건) ===\n")

# exam_type 분포 (혹시 다르게 저장된 게 있는지)
exam_dist = Counter()
for d in docs:
    year = str(d.get("year") or "")
    grade = str(d.get("grade") or "")
    g_num = ''.join(c for c in grade if c.isdigit())
    if year == "2025" and g_num == "1":
        exam_dist[d.get("exam_type") or "[NULL]"] += 1

print("2025 고1 전체의 exam_type 분포:")
for e, n in exam_dist.most_common():
    print(f"  '{e}': {n}건")

# 시험지 단위 (file_name 기준) 개수
files = set(d.get("file_name") or "" for d in target)
print(f"\n시험지(파일) 개수: {len(files)}개")
print(f"문제 개수: {len(target)}건")

# unit_code 분포
print("\n=== unit_code 분포 ===")
unit_dist = Counter()
for d in target:
    unit_dist[d.get("unit_code") or "[EMPTY]"] += 1

for u, n in unit_dist.most_common():
    flag = ""
    if u.startswith("Z"):
        flag = "  ← BAD (중학교 코드)"
    elif u == "[EMPTY]":
        flag = "  ← EMPTY"
    print(f"  {u}: {n}{flag}")

# 빈값/Z코드 파일들의 단원명
print("\n=== 빈값/Z코드 파일들의 단원명 키워드 ===")

problem_units = Counter()  # 단원명 키워드
problem_files = []
for d in target:
    unit = d.get("unit_code") or ""
    fname = d.get("file_name") or ""
    if not unit or unit.startswith("Z"):
        problem_files.append((fname, unit or "[EMPTY]"))
        for b in re.findall(r"\[([^\]]+)\]", fname):
            if any(kw in b for kw in ["식", "함수", "분", "수열", "확률", "통계", "도형", "방정", "부등", "행렬", "지수", "로그", "수렴", "미적", "벡터", "기하", "조합", "순열", "경우", "다항", "복소", "인수", "나머지", "대수"]):
                problem_units[b] += 1

print(f"문제 있는 문항: {len(problem_files)}건")
print(f"\n단원명 키워드 (상위 30):")
for kw, n in problem_units.most_common(30):
    print(f"  [{n:4d}] {kw}")

# 어떤 학교/시험지가 문제인지
print("\n=== 문제 있는 시험지(파일) 목록 ===")
file_dist = Counter()
for fname, unit in problem_files:
    file_dist[fname] += 1

for fname, n in file_dist.most_common(20):
    print(f"  [{n:3d}] {fname[:100]}")

