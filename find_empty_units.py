"""현재 빈값 데이터의 정체 분석."""
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

# 빈값 (unit_code 없음) NAESIN_N 데이터 분석
empty = []
for doc in db.collection("problems").where("source","==","NAESIN_N").stream():
    d = doc.to_dict()
    if not (d.get("unit_code") or ""):
        empty.append((doc.id, d))

print(f"NAESIN_N 빈값 총: {len(empty)}건\n")

# middle_unit 분포
mu_dist = Counter(d.get("middle_unit") or "[NULL]" for _, d in empty)
print("=== middle_unit 값 분포 (상위 30) ===")
for mu, n in mu_dist.most_common(30):
    print(f"  [{n:4d}] '{mu}'")

# 파일명 분석 (행렬 외 키워드)
print("\n=== 빈값 파일명 단원 키워드 (행렬 외) ===")
kw_cnt = Counter()
for _, d in empty:
    fname = d.get("file_name") or ""
    if "행렬" in fname:
        continue  # 행렬은 이미 처리
    # 파일명에서 [...] 안의 단원처럼 보이는 텍스트 추출
    brackets = re.findall(r"\[([^\]]+)\]", fname)
    for b in brackets:
        if any(kw in b for kw in ["식","함수","분","수열","확률","통계","도형","방정","부등","지수","로그","미적","벡터","기하","조합","순열","경우","다항","복소","인수","나머지","대수","절대","집합","명제","좌표","공간","원의","극한","연속"]):
            kw_cnt[b] += 1

for kw, n in kw_cnt.most_common(30):
    print(f"  [{n:4d}] {kw}")

