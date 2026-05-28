"""행렬의 unit_code 찾기."""
import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# curriculum_config.json 확인
config_path = PROJECT_ROOT / "backend" / "curriculum_config.json"
if config_path.exists():
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    # 2022년 2023년도 확인
    for year, data in config.items():
        for subject, units in data.items():
            for unit in units:
                if "행렬" in unit.get("name", ""):
                    print(f"[{year}년] {subject}: {unit}")

# Firestore에서 "행렬"을 제목에 포함한 NAESIN_N 문제 직접 조회
from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

import firebase_admin
from firebase_admin import firestore

db = firestore.client()

# "행렬"이 제목에 있는 NAESIN_N 문제
print("\n=== Firestore에서 제목에 '행렬' 있는 NAESIN_N ===")
naesin_n = db.collection("problems").where("source", "==", "NAESIN_N").stream()
count = 0
for doc in naesin_n:
    data = doc.to_dict()
    title = data.get("title") or ""
    
    if "행렬" in title:
        count += 1
        if count <= 10:
            print(f"[{count}] {title}")
            print(f"    unit_code={data.get('unit_code')}, year={data.get('year')}, grade={data.get('grade')}, semester={data.get('semester')}")

print(f"\nTotal: {count}건")

