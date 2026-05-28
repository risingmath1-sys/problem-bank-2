"""복구 후 NAESIN_N에 남은 P/O/T 잔재 분석."""
import sys, io
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

# NAESIN_N의 P/O/T 코드 데이터 분석
print("=== NAESIN_N P/O/T 잔재 분석 ===\n")
for code in ["P1","P2","O1","O2","T4"]:
    print(f"--- unit_code={code} ---")
    samples = []
    for doc in db.collection("problems").where("source","==","NAESIN_N").where("unit_code","==",code).stream():
        d = doc.to_dict()
        samples.append({
            "file": d.get("file_name") or "",
            "mapped": d.get("mapped_unit_code") or "[NULL]",
            "subject": d.get("subject") or "",
            "grade": d.get("grade") or "",
            "year": d.get("year") or "",
        })
    
    by_file = Counter(s["file"] for s in samples)
    by_mapped = Counter(s["mapped"] for s in samples)
    by_subject = Counter(s["subject"] for s in samples)
    
    print(f"  총 {len(samples)}건")
    print(f"  mapped_unit_code: {dict(by_mapped)}")
    print(f"  subject: {dict(by_subject)}")
    print(f"  파일 (상위 3):")
    for f, n in by_file.most_common(3):
        print(f"    [{n}] {f[:100]}")
    print()

