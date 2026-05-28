"""Firestore saved_tests 정리 (SQLite 정리 미러):
  3-a: 전체 orphan 시험지 DELETE
  3-b: 일부 orphan 시험지의 problem_ids 에서 orphan ID 제거

유효 problem id 판단: SQLite problem_bank.db (= Firestore problems 캐시)
"""
import sqlite3
import os
import sys
import json
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.getcwd())

DB_PATH = "problem_bank.db"


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB 없음: {DB_PATH}")
        sys.exit(1)

    # 1. SQLite 의 유효 problem id 로드 (Firestore problems 와 동일이라 가정)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM problems")
    all_pids = {r[0] for r in cur.fetchall()}
    conn.close()
    print(f"[INFO] SQLite problems {len(all_pids):,}건 — 유효 ID 기준")

    # 2. Firebase 초기화
    from backend.firebase_init import init_admin_sdk
    init_admin_sdk()
    from firebase_admin import firestore
    fs = firestore.client()

    # 3. Firestore saved_tests 전체 조회
    docs = list(fs.collection("saved_tests").stream())
    print(f"[INFO] Firestore saved_tests {len(docs)}건")

    ghost = []
    partial = []
    for doc in docs:
        data = doc.to_dict() or {}
        pids = data.get("problem_ids") or []
        if not pids:
            continue
        orph = [p for p in pids if p not in all_pids]
        if not orph:
            continue
        if len(orph) == len(pids):
            ghost.append((doc.id, data, pids))
        else:
            clean = [p for p in pids if p not in orph]
            partial.append((doc.id, data, pids, clean, orph))

    print(f"\n[발견] ghost={len(ghost)}건, partial={len(partial)}건")

    # 4-a. ghost DELETE
    print("\n[3-a] ghost saved_tests DELETE:")
    for did, data, pids in ghost:
        title = data.get("title", "")
        uid = data.get("user_id", "")
        fs.collection("saved_tests").document(did).delete()
        print(f"  - id={did:>4}  N={len(pids):>3}  user={str(uid)[:20]}  title={title!s}")

    # 4-b. partial UPDATE
    print("\n[3-b] partial saved_tests problem_ids 갱신:")
    for did, data, pids, clean, orph in partial:
        title = data.get("title", "")
        uid = data.get("user_id", "")
        fs.collection("saved_tests").document(did).update({"problem_ids": clean})
        print(f"  - id={did:>4}  orphan={len(orph):>2}/{len(pids):<3}  user={str(uid)[:20]}  title={title!s}")

    print(f"\n[완료] Firestore: ghost {len(ghost)}건 삭제, partial {len(partial)}건 정리.")


if __name__ == "__main__":
    main()
