"""2015_to_2022 매핑 + Firestore mapped_unit_code 확인."""
import sys, io, json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. curriculum_config.json 의 2015_to_2022 매핑 확인
cfg_path = PROJECT_ROOT / "backend" / "curriculum_config.json"
with cfg_path.open(encoding="utf-8") as f:
    cfg = json.load(f)

print("=== curriculum_config.json 의 2015_to_2022 매핑 ===\n")
mapping = cfg.get("2015_to_2022", {})
print(f"총 {len(mapping)}개 매핑\n")
for k, v in sorted(mapping.items()):
    print(f"  {k} → {v}")

# 핵심: J1, J2, J3, I1, I2, I3 매핑
print("\n=== 수열/삼각함수 매핑 ===")
for code in ["I1","I2","I3","J1","J2","J3","H1","H2","H3","H4"]:
    target = mapping.get(code, "(없음)")
    flag = " ← 잘못!" if target.startswith(("P","O","V","T","N","U")) else ""
    print(f"  {code} → {target}{flag}")

# 2. Firestore 의 P1/P2/O1 매핑 문제의 mapped_unit_code 확인
print("\n\n=== Firestore: P/O 매핑된 NAESIN_N 2025 고2 의 mapped_unit_code ===")
from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass
import firebase_admin
from firebase_admin import firestore
db = firestore.client()

for code in ["P1","P2","O1","O2","V1","V2","T4"]:
    print(f"\n--- unit_code={code} ---")
    counter = Counter()
    for doc in db.collection("problems").where("source", "==", "NAESIN_N").where("unit_code", "==", code).limit(100).stream():
        d = doc.to_dict()
        if str(d.get("year") or "") == "2025" and d.get("grade") == "고2":
            mapped = d.get("mapped_unit_code") or "[NULL]"
            counter[mapped] += 1
    if counter:
        for mapped, n in counter.most_common():
            print(f"  mapped_unit_code='{mapped}': {n}건")
    else:
        print(f"  데이터 없음")

