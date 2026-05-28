"""4종 전수조사 + 1% 미만 항목 자동 정리.
대상:
  2. problems 중복 (file_hash, file_name+endnote_index)
  3. saved_tests orphan/ghost
  4. 메타데이터 결함 (의도적 빈값 제외)
  5. 사용자 데이터 orphan (preferences, scores)

자동 정리: 영향 비율이 해당 카테고리 전체 대비 1% 미만이면 DELETE.
1% 이상이면 보고만, 사용자 결정 대기.

백업: problem_bank.db.audit_backup_<timestamp>
"""
import sqlite3
import os
import sys
import json
import shutil
import time
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "problem_bank.db"
THRESHOLD = 0.01  # 1%

# 의도적 빈값 — 메모리 노트 참고
INTENTIONAL_EMPTY_UNIT_CODE_SOURCES = {"MOCK_EXAM"}  # MOCK_EXAM 984건 의도적

# 결과 누적
report = []  # [{name, total, affected, ratio, action, ids?}]


def backup_db():
    ts = time.strftime("%Y%m%d_%H%M%S")
    bp = f"{DB_PATH}.audit_backup_{ts}"
    shutil.copy2(DB_PATH, bp)
    print(f"[BACKUP] {bp}")
    return bp


def emit(name, total, affected, action="", detail=""):
    ratio = (affected / total) if total else 0.0
    report.append({
        "name": name, "total": total, "affected": affected,
        "ratio": ratio, "action": action, "detail": detail,
    })
    pct = ratio * 100
    auto = "[자동정리]" if ratio < THRESHOLD and affected > 0 else ""
    print(f"  {name:<45} {affected:>6,} / {total:>6,}  ({pct:5.2f}%)  {action}  {auto}  {detail}")


def audit_2_duplicates(conn):
    """problems 중복: file_hash 중복, file_name+endnote_index 중복."""
    print("\n[2] problems 중복")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM problems")
    total = cur.fetchone()[0]

    # 2-a: file_hash 중복 (NULL 제외)
    cur.execute("""
        SELECT file_hash, COUNT(*) c FROM problems
        WHERE file_hash IS NOT NULL AND file_hash != ''
        GROUP BY file_hash HAVING c > 1
    """)
    hash_dups = cur.fetchall()
    hash_extra = sum(c - 1 for _h, c in hash_dups)  # 중복 그룹에서 1개씩만 남기고 제거할 수
    emit("2-a problems.file_hash 중복", total, hash_extra)

    # 2-b: file_name + endnote_index 중복
    cur.execute("""
        SELECT file_name, endnote_index, COUNT(*) c FROM problems
        WHERE file_name IS NOT NULL AND endnote_index IS NOT NULL
        GROUP BY file_name, endnote_index HAVING c > 1
    """)
    fn_dups = cur.fetchall()
    fn_extra = sum(c - 1 for _f, _e, c in fn_dups)
    emit("2-b problems.file_name+endnote_index 중복", total, fn_extra)

    # 자동 정리: 각 그룹에서 id 가장 큰 것만 남기고 나머지 DELETE (안전: 작은 id가 먼저 등록)
    actions = 0
    if hash_extra and (hash_extra / total) < THRESHOLD:
        # 각 file_hash 그룹 처리
        for fh, _c in hash_dups:
            cur.execute("SELECT id FROM problems WHERE file_hash=? ORDER BY id", (fh,))
            ids = [r[0] for r in cur.fetchall()]
            keep, drop = ids[0], ids[1:]
            for did in drop:
                cur.execute("DELETE FROM problems WHERE id=?", (did,))
                actions += 1
        print(f"    -> file_hash 중복 자동 정리: {actions}건 삭제")
    if fn_extra and (fn_extra / total) < THRESHOLD:
        actions2 = 0
        for fn, en, _c in fn_dups:
            cur.execute("SELECT id FROM problems WHERE file_name=? AND endnote_index=? ORDER BY id",
                        (fn, en))
            ids = [r[0] for r in cur.fetchall()]
            keep, drop = ids[0], ids[1:]
            for did in drop:
                cur.execute("DELETE FROM problems WHERE id=?", (did,))
                actions2 += 1
        if actions2:
            print(f"    -> file_name+endnote_index 중복 자동 정리: {actions2}건 삭제")
    conn.commit()


def audit_3_saved_tests(conn):
    """saved_tests orphan id / ghost test."""
    print("\n[3] saved_tests 정합성")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM saved_tests")
    total_tests = cur.fetchone()[0]

    # 모든 problem id 집합
    cur.execute("SELECT id FROM problems")
    all_pids = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT id, problem_ids FROM saved_tests")
    rows = cur.fetchall()

    ghost = []     # 전체 orphan
    partial = []   # 일부 orphan
    for tid, pid_json in rows:
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
            ghost.append((tid, pids))
        else:
            partial.append((tid, pids, orph))

    emit("3-a saved_tests 전체 orphan (ghost)", total_tests, len(ghost))
    emit("3-b saved_tests 일부 orphan (partial)", total_tests, len(partial))

    # 자동 정리:
    # ghost 비율 < 1% → DELETE
    # partial 비율 < 1% → problem_ids JSON 에서 orphan ID 제거 (시험지 유지)
    if total_tests and len(ghost) and (len(ghost) / total_tests) < THRESHOLD:
        for tid, _pids in ghost:
            cur.execute("DELETE FROM saved_tests WHERE id=?", (tid,))
        print(f"    -> ghost saved_tests 자동 정리: {len(ghost)}건 삭제")
    if total_tests and len(partial) and (len(partial) / total_tests) < THRESHOLD:
        for tid, pids, orph in partial:
            clean = [p for p in pids if p not in orph]
            cur.execute("UPDATE saved_tests SET problem_ids=? WHERE id=?",
                        (json.dumps(clean, ensure_ascii=False), tid))
        print(f"    -> partial saved_tests 자동 정리: {len(partial)}건 ID 정리")
    conn.commit()


def audit_4_metadata(conn):
    """problems 메타데이터 결함 (의도적 빈값 제외)."""
    print("\n[4] problems 메타데이터 결함")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM problems")
    total = cur.fetchone()[0]

    # difficulty 빈값
    cur.execute("SELECT COUNT(*) FROM problems WHERE difficulty IS NULL OR difficulty=''")
    n_diff = cur.fetchone()[0]
    emit("4-a difficulty 빈값", total, n_diff)

    # problem_type 빈값
    cur.execute("SELECT COUNT(*) FROM problems WHERE problem_type IS NULL OR problem_type=''")
    n_ptype = cur.fetchone()[0]
    emit("4-b problem_type 빈값", total, n_ptype)

    # source 빈값
    cur.execute("SELECT COUNT(*) FROM problems WHERE source IS NULL OR source=''")
    n_src = cur.fetchone()[0]
    emit("4-c source 빈값", total, n_src)

    # file_hash NULL (중복 검출 불가)
    cur.execute("SELECT COUNT(*) FROM problems WHERE file_hash IS NULL OR file_hash=''")
    n_hash = cur.fetchone()[0]
    emit("4-d file_hash NULL", total, n_hash)

    # unit_code 빈값 (의도적 빈값 제외)
    placeholders = ",".join("?" * len(INTENTIONAL_EMPTY_UNIT_CODE_SOURCES))
    cur.execute(f"""
        SELECT COUNT(*) FROM problems
        WHERE (unit_code IS NULL OR unit_code='')
          AND source NOT IN ({placeholders})
    """, tuple(INTENTIONAL_EMPTY_UNIT_CODE_SOURCES))
    n_unit = cur.fetchone()[0]
    emit("4-e unit_code 빈값 (의도적 제외)", total, n_unit,
         detail=f"의도적 빈값({list(INTENTIONAL_EMPTY_UNIT_CODE_SOURCES)}) 제외")

    # 자동 정리는 위험 (메타 결함은 DELETE 아니라 별도 보정) → 보고만
    print("    -> [자동 정리 안 함] 메타 결함은 삭제 아닌 보정 대상. 보고만.")


def audit_5_user_orphan(conn):
    """problem_preferences / problem_scores 의 orphan problem_id."""
    print("\n[5] 사용자 데이터 orphan (preferences / scores)")
    cur = conn.cursor()

    # problems id 집합
    cur.execute("SELECT id FROM problems")
    all_pids = {r[0] for r in cur.fetchall()}

    # preferences
    cur.execute("SELECT COUNT(*) FROM problem_preferences")
    pref_total = cur.fetchone()[0]
    cur.execute("SELECT problem_id FROM problem_preferences")
    pref_pids = [r[0] for r in cur.fetchall()]
    pref_orph = [p for p in pref_pids if p not in all_pids]
    emit("5-a problem_preferences orphan", pref_total, len(pref_orph))

    # scores
    cur.execute("SELECT COUNT(*) FROM problem_scores")
    sc_total = cur.fetchone()[0]
    cur.execute("SELECT problem_id FROM problem_scores")
    sc_pids = [r[0] for r in cur.fetchall()]
    sc_orph = [p for p in sc_pids if p not in all_pids]
    emit("5-b problem_scores orphan", sc_total, len(sc_orph))

    if pref_total and len(pref_orph) and (len(pref_orph) / pref_total) < THRESHOLD:
        # orphan problem_id 들 DELETE
        for pid in set(pref_orph):
            cur.execute("DELETE FROM problem_preferences WHERE problem_id=?", (pid,))
        print(f"    -> preferences orphan 자동 정리: {len(pref_orph)}건 삭제")
    if sc_total and len(sc_orph) and (len(sc_orph) / sc_total) < THRESHOLD:
        for pid in set(sc_orph):
            cur.execute("DELETE FROM problem_scores WHERE problem_id=?", (pid,))
        print(f"    -> scores orphan 자동 정리: {len(sc_orph)}건 삭제")
    conn.commit()


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB 없음: {DB_PATH}")
        sys.exit(1)

    backup_db()
    conn = sqlite3.connect(DB_PATH)

    print("\n" + "=" * 78)
    print(f"[전수조사 + 1% 미만 자동정리]  (THRESHOLD={THRESHOLD*100}%)")
    print("=" * 78)

    audit_2_duplicates(conn)
    audit_3_saved_tests(conn)
    audit_4_metadata(conn)
    audit_5_user_orphan(conn)

    # 1% 이상인 항목 추가 보고
    print("\n" + "=" * 78)
    print("[1% 이상 — 사용자 결정 필요]")
    print("=" * 78)
    over = [r for r in report if r["ratio"] >= THRESHOLD and r["affected"] > 0]
    if over:
        for r in over:
            pct = r["ratio"] * 100
            print(f"  - {r['name']}: {r['affected']:,} / {r['total']:,} ({pct:.2f}%)  {r['detail']}")
    else:
        print("  (없음)")

    conn.close()
    print("\n[완료]")


if __name__ == "__main__":
    main()
