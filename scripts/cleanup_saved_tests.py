"""saved_tests 정리:
  3-a: ghost (전체 orphan) 시험지 DELETE
  3-b: partial (일부 orphan) 시험지의 problem_ids JSON 에서 orphan ID 제거
"""
import sqlite3
import os
import sys
import json
import shutil
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "problem_bank.db"


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB 없음: {DB_PATH}")
        sys.exit(1)

    ts = time.strftime("%Y%m%d_%H%M%S")
    bp = f"{DB_PATH}.cleanup_st_backup_{ts}"
    shutil.copy2(DB_PATH, bp)
    print(f"[BACKUP] {bp}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 유효 problem id 집합
    cur.execute("SELECT id FROM problems")
    all_pids = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT id, user_id, title, problem_ids FROM saved_tests")
    rows = cur.fetchall()

    ghost = []
    partial = []
    for tid, uid, title, pid_json in rows:
        try:
            pids = json.loads(pid_json) if pid_json else []
        except Exception:
            pids = []
        if not pids:
            continue
        orph = [p for p in pids if p not in all_pids]
        if not orph:
            continue
        if len(orph) == len(pids):
            ghost.append((tid, uid, title, len(pids)))
        else:
            clean = [p for p in pids if p not in orph]
            partial.append((tid, uid, title, pids, clean, orph))

    print(f"\n[발견] ghost={len(ghost)}건, partial={len(partial)}건")

    # 3-a: ghost DELETE
    print("\n[3-a] ghost saved_tests DELETE:")
    for tid, uid, title, n in ghost:
        cur.execute("DELETE FROM saved_tests WHERE id=?", (tid,))
        print(f"  - id={tid:>4}  N={n:>3}  user={str(uid)[:20]}  title={title!s}")

    # 3-b: partial — problem_ids 갱신
    print("\n[3-b] partial saved_tests orphan 제거:")
    for tid, uid, title, pids, clean, orph in partial:
        cur.execute("UPDATE saved_tests SET problem_ids=? WHERE id=?",
                    (json.dumps(clean, ensure_ascii=False), tid))
        print(f"  - id={tid:>4}  orphan={len(orph):>2}/{len(pids):<3}  user={str(uid)[:20]}  title={title!s}")

    conn.commit()
    conn.close()

    print(f"\n[완료] ghost {len(ghost)}건 삭제, partial {len(partial)}건 정리.")


if __name__ == "__main__":
    main()
