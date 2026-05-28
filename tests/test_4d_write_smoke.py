# -*- coding: utf-8 -*-
"""
Phase 4-D 스모크: SQLite/Firestore 양 모드에서 problems WRITE 5개 메서드를 호출.

검증:
  - 양 모드 동일 시그니처/반환값.
  - Firestore 모드는 캐시 SQLite 까지 일관되게 갱신되는지 확인 (write-through).
  - dummy id 만 사용 → 영구 부작용 없도록 끝에 정리.

실행:
  python tests/test_4d_write_smoke.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

LOCAL_DB = os.path.join(ROOT, "problem_bank.db")
SA_PATH = os.path.join(ROOT, "backend", "naegiwangbank-firebase-adminsdk-fbsvc-5e5e798b33.json")

PASS = 0
FAIL = 0


def case(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}  {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ─── dummy 데이터 셋업/정리 ───────────────────────────────────────────────
DUMMY_FILE = lambda tag: f"_4dsmoke_{tag}.hwp"
DUMMY_SCHOOL = "_4dsmoke_school"


def make_dummy_rows(tag, count=3):
    """SQLite/Firestore 양쪽에 동일하게 넣을 수 있는 row dict 리스트."""
    rows = []
    for i in range(1, count + 1):
        rows.append({
            "id": f"_4dsmoke_{tag}_{i}",
            "file_name": DUMMY_FILE(tag),
            "endnote_index": i,
            "school": DUMMY_SCHOOL,
            "year": "2026",
            "grade": "3",
            "semester": "1",
            "exam_type": "smoke",
            "subject": "수학",
            "curriculum": "2022",
            "unit_code": "G1",
            "mapped_unit_code": "G1",
            "difficulty": "C",
            "problem_type": "객관식",
            "is_excluded": 0,
            "source": "SMOKE",
            "problem_number": i,
            "exam_number": 1,
            "tags": "",
            "difficulty_locked": 0,
            "unit_code_locked": 0,
            "indexed_at": time.time(),
            "large_unit": "수학",
            "middle_unit": "이차방정식",
        })
    return rows


def setup_sqlite(rows):
    import sqlite3
    conn = sqlite3.connect(LOCAL_DB)
    cur = conn.cursor()
    cols = list(rows[0].keys())
    ph = ",".join(["?"] * len(cols))
    cs = ",".join(cols)
    for r in rows:
        cur.execute(
            f"INSERT OR REPLACE INTO problems({cs}) VALUES({ph})",
            [r[c] for c in cols]
        )
    conn.commit()
    conn.close()


def cleanup_sqlite(tag):
    import sqlite3
    conn = sqlite3.connect(LOCAL_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM problems WHERE id LIKE ?", (f"_4dsmoke_{tag}_%",))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def setup_firestore(fs, rows):
    """Firestore + 로컬 캐시 양쪽에 dummy 적재."""
    from firebase_admin import firestore as _fs
    batch = fs.batch()
    for r in rows:
        d = dict(r)
        # Firestore 는 updated_at 을 SERVER_TIMESTAMP 로 — incremental_sync 가 잡도록.
        d["updated_at"] = _fs.SERVER_TIMESTAMP
        ref = fs.collection("problems").document(r["id"])
        batch.set(ref, d)
    batch.commit()


def cleanup_firestore(fs, tag):
    from google.cloud.firestore_v1.base_query import FieldFilter
    cnt = 0
    # tag 로 시작하는 dummy 도큐먼트 id 검색
    for s in (fs.collection("problems")
                .where(filter=FieldFilter("file_name", "==", DUMMY_FILE(tag)))
                .stream()):
        s.reference.delete()
        cnt += 1
    return cnt


def fetch_firestore_doc(fs, pid):
    snap = fs.collection("problems").document(pid).get()
    return snap.to_dict() if snap.exists else None


def fetch_cache_row(cache, pid):
    with cache.connect() as conn:
        r = conn.execute(
            "SELECT * FROM problems WHERE id=?", (pid,)
        ).fetchone()
        return dict(r) if r else None


# ─── SQLite 모드 ──────────────────────────────────────────────────────────
def smoke_sqlite():
    print("\n=== SQLite ===")
    tag = f"sql{int(time.time())}"
    rows = make_dummy_rows(tag, count=3)
    setup_sqlite(rows)

    os.environ["DATA_ENGINE"] = "sqlite"
    from backend.data_engine import make_engine, get_engine_mode
    print(f"DATA_ENGINE = {get_engine_mode()}")
    eng = make_engine(LOCAL_DB, verbose=False)

    pid1 = rows[0]["id"]
    pid2 = rows[1]["id"]
    pid3 = rows[2]["id"]

    # 1) update_problem_meta — difficulty
    eng.update_problem_meta(pid1, "difficulty", "A")
    import sqlite3
    conn = sqlite3.connect(LOCAL_DB); conn.row_factory = sqlite3.Row
    r = dict(conn.execute("SELECT * FROM problems WHERE id=?", (pid1,)).fetchone())
    conn.close()
    case("SQLite update_problem_meta difficulty",
         r["difficulty"] == "A" and r["difficulty_locked"] == 1,
         f"(diff={r['difficulty']}, locked={r['difficulty_locked']})")

    # 2) update_problem_meta — unit_code
    eng.update_problem_meta(pid2, "unit_code", "M2", "함수")
    conn = sqlite3.connect(LOCAL_DB); conn.row_factory = sqlite3.Row
    r = dict(conn.execute("SELECT * FROM problems WHERE id=?", (pid2,)).fetchone())
    conn.close()
    case("SQLite update_problem_meta unit_code",
         r["unit_code"] == "M2" and r["middle_unit"] == "함수" and r["unit_code_locked"] == 1)

    # 3) set_exclusion_status — exclude
    n = eng.set_exclusion_status([pid1, pid2], True)
    case("SQLite set_exclusion_status excluded count", n == 2)
    conn = sqlite3.connect(LOCAL_DB)
    cur = conn.execute("SELECT id, is_excluded FROM problems WHERE id IN (?,?)",
                       (pid1, pid2)).fetchall()
    conn.close()
    case("SQLite is_excluded=1", all(c[1] == 1 for c in cur))

    # 4) set_exclusion_status — restore
    eng.set_exclusion_status([pid1, pid2], False)
    conn = sqlite3.connect(LOCAL_DB)
    cur = conn.execute("SELECT id, is_excluded FROM problems WHERE id IN (?,?)",
                       (pid1, pid2)).fetchall()
    conn.close()
    case("SQLite is_excluded restored", all(c[1] == 0 for c in cur))

    # 5) delete_problems — 단건
    n = eng.delete_problems([pid1])
    case("SQLite delete_problems count", n == 1)
    conn = sqlite3.connect(LOCAL_DB)
    r = conn.execute("SELECT id FROM problems WHERE id=?", (pid1,)).fetchone()
    conn.close()
    case("SQLite delete_problems gone", r is None)

    # 6) delete_exam — meta 일치 (남은 pid2, pid3)
    n = eng.delete_exam({
        "school": DUMMY_SCHOOL, "year": "2026", "grade": "3",
        "semester": "1", "exam_type": "smoke", "subject": "수학",
    })
    case("SQLite delete_exam count", n == 2, f"(actual={n})")

    # 7) delete_exams_by_filenames — 이미 비어있어야 함 → 0
    setup_sqlite(make_dummy_rows(tag + "X", count=2))  # 새 dummy
    n = eng.delete_exams_by_filenames([DUMMY_FILE(tag + "X")])
    case("SQLite delete_exams_by_filenames count", n == 2, f"(actual={n})")

    # cleanup safety
    cleanup_sqlite(tag)
    cleanup_sqlite(tag + "X")


# ─── Firestore 모드 ───────────────────────────────────────────────────────
def smoke_firestore():
    print("\n=== Firestore ===")
    tag = f"fs{int(time.time())}"
    rows = make_dummy_rows(tag, count=3)

    # firebase_admin 초기화
    import firebase_admin
    from firebase_admin import credentials, firestore as _fs
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
    fs = _fs.client()

    # Firestore 에 dummy 추가
    setup_firestore(fs, rows)

    os.environ["DATA_ENGINE"] = "firestore"
    from backend.data_engine import make_engine, get_engine_mode
    print(f"DATA_ENGINE = {get_engine_mode()}")
    eng = make_engine(LOCAL_DB, verbose=False)
    # 캐시에 incremental_sync 가 dummy 를 적재했어야 함
    pid1, pid2, pid3 = [r["id"] for r in rows]

    case("Firestore setup cache has pid1",
         fetch_cache_row(eng.cache, pid1) is not None)

    try:
        # 1) update_problem_meta — difficulty
        eng.update_problem_meta(pid1, "difficulty", "A")
        d = fetch_firestore_doc(fs, pid1)
        case("Firestore update_problem_meta diff (server)",
             d and d.get("difficulty") == "A" and d.get("difficulty_locked") == 1)
        c = fetch_cache_row(eng.cache, pid1)
        case("Firestore update_problem_meta diff (cache)",
             c and c.get("difficulty") == "A" and c.get("difficulty_locked") == 1)

        # 2) update_problem_meta — unit_code
        eng.update_problem_meta(pid2, "unit_code", "M2", "함수")
        d = fetch_firestore_doc(fs, pid2)
        case("Firestore update_problem_meta unit (server)",
             d and d.get("unit_code") == "M2" and d.get("middle_unit") == "함수"
             and d.get("unit_code_locked") == 1)
        c = fetch_cache_row(eng.cache, pid2)
        case("Firestore update_problem_meta unit (cache)",
             c and c.get("unit_code") == "M2" and c.get("middle_unit") == "함수"
             and c.get("unit_code_locked") == 1)

        # 3) set_exclusion_status — exclude
        n = eng.set_exclusion_status([pid1, pid2], True)
        case("Firestore set_exclusion_status count", n == 2)
        d1 = fetch_firestore_doc(fs, pid1); d2 = fetch_firestore_doc(fs, pid2)
        case("Firestore is_excluded=1 (server)",
             d1.get("is_excluded") == 1 and d2.get("is_excluded") == 1)
        c1 = fetch_cache_row(eng.cache, pid1); c2 = fetch_cache_row(eng.cache, pid2)
        case("Firestore is_excluded=1 (cache)",
             c1.get("is_excluded") == 1 and c2.get("is_excluded") == 1)

        # 4) set_exclusion_status — restore
        eng.set_exclusion_status([pid1, pid2], False)
        d1 = fetch_firestore_doc(fs, pid1); d2 = fetch_firestore_doc(fs, pid2)
        case("Firestore is_excluded restored (server)",
             d1.get("is_excluded") == 0 and d2.get("is_excluded") == 0)
        c1 = fetch_cache_row(eng.cache, pid1); c2 = fetch_cache_row(eng.cache, pid2)
        case("Firestore is_excluded restored (cache)",
             c1.get("is_excluded") == 0 and c2.get("is_excluded") == 0)

        # 5) delete_problems — 단건
        n = eng.delete_problems([pid1])
        case("Firestore delete_problems count", n == 1)
        case("Firestore delete_problems server gone",
             fetch_firestore_doc(fs, pid1) is None)
        case("Firestore delete_problems cache gone",
             fetch_cache_row(eng.cache, pid1) is None)

        # 6) delete_exam — meta 일치 (남은 pid2, pid3)
        n = eng.delete_exam({
            "school": DUMMY_SCHOOL, "year": "2026", "grade": "3",
            "semester": "1", "exam_type": "smoke", "subject": "수학",
        })
        case("Firestore delete_exam count", n == 2, f"(actual={n})")
        case("Firestore delete_exam pid2 gone",
             fetch_firestore_doc(fs, pid2) is None
             and fetch_cache_row(eng.cache, pid2) is None)
        case("Firestore delete_exam pid3 gone",
             fetch_firestore_doc(fs, pid3) is None
             and fetch_cache_row(eng.cache, pid3) is None)

        # 7) delete_exams_by_filenames — 새 dummy 묶음
        rows2 = make_dummy_rows(tag + "X", count=2)
        setup_firestore(fs, rows2)
        # 캐시에 적재 (incremental_sync)
        eng.cache.incremental_sync()
        n = eng.delete_exams_by_filenames([DUMMY_FILE(tag + "X")])
        case("Firestore delete_exams_by_filenames count", n == 2, f"(actual={n})")
        case("Firestore delete_exams_by_filenames cache gone",
             fetch_cache_row(eng.cache, rows2[0]["id"]) is None)
    finally:
        # 잔재 정리
        rem = cleanup_firestore(fs, tag) + cleanup_firestore(fs, tag + "X")
        if rem:
            print(f"  [cleanup] Firestore 잔재 {rem}건 정리")
        # 캐시도 정리
        with eng.cache.connect() as conn:
            conn.execute("DELETE FROM problems WHERE id LIKE '_4dsmoke_%'")
            conn.commit()


def main():
    smoke_sqlite()
    smoke_firestore()
    print(f"\n{'='*40}\nPASS: {PASS}    FAIL: {FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
