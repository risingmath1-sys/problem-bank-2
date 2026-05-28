"""P/O/V/T 코드가 어디 단원인지 확인."""
import sys, io, json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# unit_hierarchy.json
hier_path = PROJECT_ROOT / "backend" / "unit_hierarchy.json"
with hier_path.open(encoding="utf-8") as f:
    hier = json.load(f)

# 모든 unit_code 한 줄로 정리
print("=== 단원 코드 사전 (unit_hierarchy.json) ===\n")
codes_dict = {}
for version in ["2022", "2015"]:
    print(f"--- {version} ---")
    for subj in hier.get(version, []):
        subj_name = subj.get("subject")
        for large in subj.get("large_units", []):
            l_name = large.get("name")
            for medium in large.get("medium_units", []):
                name = medium.get("name", "")
                code = medium.get("code", "")
                if code:
                    codes_dict[code] = f"[{version}] {subj_name} > {l_name} > {name}"
                    # P/O/V/T로 시작하는 것만 출력
                    if code[0] in "POVTNUWXY":
                        print(f"  {code}: {subj_name} > {l_name} > {name}")
    print()

# 사용자 의문 코드 확인
print("\n=== 2025 고2에 나타난 의문 코드 ===")
for code in ["P1","P2","O1","O2","V1","V2","T4","N1","N2","N3"]:
    print(f"  {code}: {codes_dict.get(code, '(없음)')}")

# Firestore 데이터 - P1/P2 가 있는 파일명 확인
from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

import firebase_admin
from firebase_admin import firestore
db = firestore.client()

print("\n=== 2025 고2 NAESIN_N P1/P2/O1/O2 unit_code 파일 샘플 ===")
result = db.collection("problems").where("source", "==", "NAESIN_N").stream()

for code in ["P1", "P2", "O1", "O2", "V1", "V2", "T4"]:
    samples = set()
    for doc in db.collection("problems").where("source", "==", "NAESIN_N").where("unit_code", "==", code).limit(50).stream():
        d = doc.to_dict()
        if str(d.get("year") or "") == "2025" and d.get("grade") == "고2":
            samples.add(d.get("file_name") or "")
    print(f"\n{code} ({codes_dict.get(code, '?')[:60]}):")
    for f in list(samples)[:3]:
        print(f"  {f[:120]}")

