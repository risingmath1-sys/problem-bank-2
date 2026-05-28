"""NAESIN_N 전수 조사."""
import sys
import json
from pathlib import Path
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

import firebase_admin
from firebase_admin import firestore

db = firestore.client()

# 모든 NAESIN_N 데이터 스트림
print("=== NAESIN_N FULL AUDIT ===\n")
print("Loading all NAESIN_N docs...")
result = db.collection("problems").where("source", "==", "NAESIN_N").stream()

# 모든 필드를 메모리에 적재
docs = []
for doc in result:
    docs.append(doc.to_dict())

print(f"Total NAESIN_N: {len(docs)}\n")

# 1. year/grade/semester/curriculum별 unit_code 빈 값 분포
print("=" * 80)
print("[1] grade/semester/curriculum별 unit_code 분포")
print("=" * 80)
bucket = defaultdict(lambda: {"total": 0, "empty": 0, "z_code": 0, "by_unit": Counter()})

for d in docs:
    year = str(d.get("year") or "?")
    grade = str(d.get("grade") or "?")
    sem = str(d.get("semester") or "?")
    curr = str(d.get("curriculum") or "?")
    unit = d.get("unit_code") or ""
    
    # grade 숫자만 추출
    g_num = ''.join(c for c in grade if c.isdigit()) or "?"
    s_num = sem.split("학기")[0].strip() if "학기" in sem else "?"
    
    key = (year, g_num, s_num, curr[:8])
    b = bucket[key]
    b["total"] += 1
    if not unit:
        b["empty"] += 1
    elif unit.startswith("Z"):
        b["z_code"] += 1
    b["by_unit"][unit or "[EMPTY]"] += 1

print(f"{'Year':<6} {'G':<3} {'S':<3} {'Curr':<10} {'Total':<7} {'Empty':<7} {'Z_Code':<7} {'Empty%':<7}")
print("-" * 80)
for key in sorted(bucket.keys()):
    year, g, s, curr = key
    b = bucket[key]
    total = b["total"]
    empty = b["empty"]
    z = b["z_code"]
    pct = (empty * 100 / total) if total else 0
    flag = " <<<" if pct > 5 or z > 0 else ""
    print(f"{year:<6} {g:<3} {s:<3} {curr:<10} {total:<7} {empty:<7} {z:<7} {pct:>5.1f}%{flag}")

# 2. 2025년 1학년 2학기에 집중
print("\n" + "=" * 80)
print("[2] 2025 G1 S2 NAESIN_N (사용자 지목)")
print("=" * 80)

target_docs = []
for d in docs:
    year = str(d.get("year") or "")
    grade = str(d.get("grade") or "")
    sem = str(d.get("semester") or "")
    g_num = ''.join(c for c in grade if c.isdigit())
    s_num = sem.split("학기")[0].strip() if "학기" in sem else ""
    if year == "2025" and g_num == "1" and s_num == "2":
        target_docs.append(d)

print(f"Total: {len(target_docs)}")
if target_docs:
    unit_dist = Counter()
    curriculum_dist = Counter()
    subject_dist = Counter()
    for d in target_docs:
        unit_dist[d.get("unit_code") or "[EMPTY]"] += 1
        curriculum_dist[d.get("curriculum") or "[EMPTY]"] += 1
        subject_dist[d.get("subject") or "[EMPTY]"] += 1
    
    print(f"\nCurriculum 분포:")
    for c, n in curriculum_dist.most_common():
        print(f"  {c}: {n}")
    print(f"\nSubject 분포:")
    for s, n in subject_dist.most_common():
        print(f"  {s}: {n}")
    print(f"\nUnit_code 분포 (상위 25):")
    for u, n in unit_dist.most_common(25):
        flag = " ← BAD (middle school code)" if u.startswith("Z") else (" ← EMPTY" if u == "[EMPTY]" else "")
        print(f"  {u}: {n}{flag}")

# 3. 2025년 1학년 2학기 unit_code 빈 값 샘플 (파일명에서 단원 추론)
print("\n" + "=" * 80)
print("[3] 2025 G1 S2 unit_code 빈값 파일명 샘플 (단원명 추출)")
print("=" * 80)

empty_files = Counter()
z_files = Counter()
for d in target_docs:
    unit = d.get("unit_code") or ""
    fname = d.get("file_name") or ""
    if not unit:
        empty_files[fname] += 1
    elif unit.startswith("Z"):
        z_files[fname] += 1

print(f"\nUnit_code 빈값인 파일들 ({len(empty_files)}개 파일, 총 {sum(empty_files.values())}문제):")
for fname, cnt in empty_files.most_common(15):
    print(f"  [{cnt:3d}] {fname[:90]}")

print(f"\nUnit_code Z* (중학교 코드) 파일들 ({len(z_files)}개 파일):")
for fname, cnt in z_files.most_common(15):
    print(f"  [{cnt:3d}] {fname[:90]}")

# 4. 2025년 전체 1학년에서 unit_code Z*와 [EMPTY] 단원명 추출 (파일명에서)
print("\n" + "=" * 80)
print("[4] 2025 G1 전체 - 문제 있는 파일명에서 단원 키워드 추출")
print("=" * 80)

import re
keywords = Counter()
bad_files = []
for d in docs:
    year = str(d.get("year") or "")
    grade = str(d.get("grade") or "")
    g_num = ''.join(c for c in grade if c.isdigit())
    if year != "2025" or g_num != "1":
        continue
    unit = d.get("unit_code") or ""
    if not unit or unit.startswith("Z"):
        fname = d.get("file_name") or ""
        bad_files.append(fname)
        # 파일명에서 [...] 안의 단원명 추출
        for m in re.findall(r"\[([^\]]+)\]", fname):
            # 한글이 포함된 항목 중 단원처럼 보이는 것만 (출판사/지역명 제외용)
            if any(kw in m for kw in ["식", "함수", "분", "수열", "확률", "통계", "도형", "방정", "부등", "행렬", "지수", "로그", "수렴", "미적", "벡터", "기하"]):
                keywords[m] += 1

print(f"\n문제 있는 고1 파일 {len(bad_files)}개에서 추출한 단원 키워드 후보:")
for kw, n in keywords.most_common(30):
    print(f"  [{n:4d}] {kw}")

