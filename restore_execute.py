"""Firestore 일괄 복구 — mapped_unit_code 가 있으면 unit_code 를 그것으로 덮어쓰기.

전략:
1. 변경 대상의 (doc_id, 현재 unit_code, 새 unit_code) 를 JSON 백업
2. Firestore batched_write (배치당 500) 로 unit_code 갱신
3. mapped_unit_code 는 그대로 둠 (감사 추적용)

dry_run=True 면 실제 쓰기 없이 검증만.
"""
import sys, io, json, time
from pathlib import Path
from datetime import datetime

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

DRY_RUN = False  # ← True 면 실제 쓰기 없이 검증만

db = firestore.client()

print(f"=== Firestore unit_code 복구 (dry_run={DRY_RUN}) ===\n")
t_start = time.time()

# 1. 변경 대상 수집 + 백업
plan = []  # [(doc_id, old_uc, new_uc, source, year, grade)]
print("[1/3] 변경 대상 수집 중...")
for doc in db.collection("problems").stream():
    d = doc.to_dict()
    uc = d.get("unit_code") or ""
    mc = d.get("mapped_unit_code") or ""
    if mc and uc != mc:
        plan.append({
            "id": doc.id,
            "old_unit_code": uc,
            "new_unit_code": mc,
            "source": d.get("source") or "",
            "year": d.get("year") or "",
            "grade": d.get("grade") or "",
        })

print(f"  복구 대상: {len(plan)}건")

# 2. 백업 저장
backup_path = PROJECT_ROOT / f"restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with backup_path.open("w", encoding="utf-8") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)
print(f"  백업 저장: {backup_path}")

if DRY_RUN:
    print("\n[DRY RUN] 실제 쓰기 생략. 변경 샘플 10개:")
    for p in plan[:10]:
        print(f"  {p['id'][:60]}: {p['old_unit_code']} → {p['new_unit_code']}")
    print(f"\n총 {len(plan)}건이 갱신될 예정.")
else:
    # 3. Batched write (Firestore batch 한도: 500/batch)
    print(f"\n[2/3] Firestore batched update...")
    BATCH_SIZE = 400  # 안전 마진
    updated = 0
    failed = 0
    for i in range(0, len(plan), BATCH_SIZE):
        chunk = plan[i:i + BATCH_SIZE]
        batch = db.batch()
        for p in chunk:
            ref = db.collection("problems").document(p["id"])
            batch.update(ref, {"unit_code": p["new_unit_code"]})
        try:
            batch.commit()
            updated += len(chunk)
            print(f"  batch {i//BATCH_SIZE + 1}: {len(chunk)}건 갱신 (누적 {updated})")
        except Exception as e:
            failed += len(chunk)
            print(f"  batch {i//BATCH_SIZE + 1} 실패: {e}")
    
    print(f"\n[3/3] 완료: 성공 {updated}건, 실패 {failed}건")

print(f"\n경과시간: {time.time()-t_start:.1f}초")

