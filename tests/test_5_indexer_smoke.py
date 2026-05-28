# -*- coding: utf-8 -*-
"""
Phase 5 스모크: 양 모드에서 engine.ingest_indexed_problems 가
hwp_metadata_parser_v2._post_process_file 의 SQLite 직접 INSERT + naive
Firestore set() 두 경로를 한 번에 대체하는지 검증.

검증 항목:
  - 신규 ingest: id 매핑 (problem_id → id), MOCK_EXAM exam_number 보정,
                  타 source 의 exam_number=None.
  - 잠금 보존: difficulty_locked / unit_code_locked 가 1 인 기존 doc 은
                재인덱싱 결과로 덮어쓰지 않음.
  - is_excluded 보존: 재인덱싱이 사용자 출제 제외 상태 유지.
  - Firestore 모드: write-through 캐시 동기화 (server + cache 동일 값).

dummy id 만 사용 → 끝에 정리.
실행: python tests/test_5_indexer_smoke.py
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


# ─── dummy 데이터 (parser asdict() 형식 — problem_id 키) ────────────────────
DUMMY_FILE = lambda tag: f"_5smoke_{tag}.hwp"
DUMMY_SCHOOL = "_5smoke_school"


def make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=3, base_endnote=1, difficulty="C", unit_code="G1"):
    """ProblemRecord asdict 형식 — problem_id 가 PK."""
    items = []
    for i in range(count):
        idx = base_endnote + i
        items.append({
            "problem_id": f"_5smoke_{tag}_{idx}",
            "file_name": DUMMY_FILE(tag),
            "endnote_index": idx,
            "school": DUMMY_SCHOOL,
            "year": "2026",
            "grade": "3",
            "semester": "1",
            "exam_type": "smoke",
            "subject": "수학",
            "curriculum": "2022",
            "unit_code": unit_code,
            "mapped_unit_code": unit_code,
            "difficulty": difficulty,
            "problem_type": "객관식",
            "pos_start": [0, idx, 0],
            "pos_end": [0, idx + 1, 0],
            "large_unit": "수학",
            "middle_unit": "이차방정식",
            "source": source,
            "indexed_at": time.time(),
            "file_hash": f"hash_{idx}",
            "search_text": f"smoke search text {idx}",
            "tags": "",
        })
    return items


def cleanup_sqlite(tag):
    import sqlite3
    conn = sqlite3.connect(LOCAL_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM problems WHERE id LIKE ?", (f"_5smoke_{tag}_%",))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def cleanup_firestore(fs, tag):
    from google.cloud.firestore_v1.base_query import FieldFilter
    cnt = 0
    for s in (fs.collection("problems")
                .where(filter=FieldFilter("file_name", "==", DUMMY_FILE(tag)))
                .stream()):
        s.reference.delete()
        cnt += 1
    return cnt


def fetch_sqlite_row(pid):
    import sqlite3
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def fetch_firestore_doc(fs, pid):
    snap = fs.collection("problems").document(pid).get()
    return snap.to_dict() if snap.exists else None


def fetch_cache_row(cache, pid):
    with cache.connect() as conn:
        r = conn.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


# ─── SQLite 모드 ──────────────────────────────────────────────────────────
def smoke_sqlite():
    print("\n=== SQLite ===")
    tag = f"sql{int(time.time())}"

    os.environ["DATA_ENGINE"] = "sqlite"
    from backend.data_engine import make_engine, get_engine_mode
    print(f"DATA_ENGINE = {get_engine_mode()}")
    eng = make_engine(LOCAL_DB, verbose=False)

    try:
        # 1) 신규 ingest — 3건
        items = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=3)
        n = eng.ingest_indexed_problems(items)
        case("SQLite ingest 신규 count", n == 3, f"(actual={n})")

        pid1 = items[0]["problem_id"]
        r = fetch_sqlite_row(pid1)
        case("SQLite ingest id 매핑 (problem_id → id)",
             r is not None and r["id"] == pid1)
        case("SQLite ingest difficulty 저장", r and r["difficulty"] == "C")
        case("SQLite ingest unit_code 저장", r and r["unit_code"] == "G1")
        case("SQLite ingest 타 source exam_number=None",
             r and r["exam_number"] is None,
             f"(exam_number={r['exam_number']})")
        case("SQLite ingest problem_number = endnote_index",
             r and r["problem_number"] == 1)

        # 2) MOCK_EXAM exam_number 보정
        mock_items = [
            {**make_indexed_items(tag + "M", source="MOCK_EXAM", count=1, base_endnote=15)[0]},
            {**make_indexed_items(tag + "M", source="MOCK_EXAM", count=1, base_endnote=23)[0]},
            {**make_indexed_items(tag + "M", source="MOCK_EXAM", count=1, base_endnote=31)[0]},
        ]
        eng.ingest_indexed_problems(mock_items)
        rs = [fetch_sqlite_row(it["problem_id"]) for it in mock_items]
        case("MOCK_EXAM pn=15 → exam_number=15",
             rs[0] and rs[0]["exam_number"] == 15)
        case("MOCK_EXAM pn=23 → exam_number=23",
             rs[1] and rs[1]["exam_number"] == 23,
             f"(actual={rs[1]['exam_number']})")
        case("MOCK_EXAM pn=31 → exam_number=23",
             rs[2] and rs[2]["exam_number"] == 23,
             f"(actual={rs[2]['exam_number']})")

        # 3) 잠금 보존 — difficulty_locked
        # 사용자가 update_problem_meta 로 lock 설정
        eng.update_problem_meta(pid1, "difficulty", "A")
        # 재인덱싱 (difficulty=B 로 들어온 것처럼)
        new_items = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=1, difficulty="B")
        # 동일 문항 갱신 — problem_id 가 동일하도록 base_endnote 맞춤
        new_items[0]["problem_id"] = pid1
        new_items[0]["endnote_index"] = 1
        eng.ingest_indexed_problems(new_items)
        r = fetch_sqlite_row(pid1)
        case("SQLite 잠금 보존: difficulty_locked=1 시 difficulty 유지",
             r and r["difficulty"] == "A" and r["difficulty_locked"] == 1,
             f"(diff={r['difficulty']}, locked={r['difficulty_locked']})")

        # 4) 잠금 보존 — unit_code_locked
        pid2 = items[1]["problem_id"]
        eng.update_problem_meta(pid2, "unit_code", "M2", "함수")
        new_items2 = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=1, unit_code="N3")
        new_items2[0]["problem_id"] = pid2
        new_items2[0]["endnote_index"] = 2
        new_items2[0]["middle_unit"] = "확률"  # 새 인덱싱 값
        eng.ingest_indexed_problems(new_items2)
        r = fetch_sqlite_row(pid2)
        case("SQLite 잠금 보존: unit_code_locked=1 시 unit_code 유지",
             r and r["unit_code"] == "M2" and r["middle_unit"] == "함수"
             and r["unit_code_locked"] == 1,
             f"(uc={r['unit_code']}, mu={r['middle_unit']})")

        # 5) is_excluded 보존
        pid3 = items[2]["problem_id"]
        eng.set_exclusion_status([pid3], True)
        new_items3 = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=1)
        new_items3[0]["problem_id"] = pid3
        new_items3[0]["endnote_index"] = 3
        eng.ingest_indexed_problems(new_items3)
        r = fetch_sqlite_row(pid3)
        case("SQLite 재인덱싱이 is_excluded 유지",
             r and r["is_excluded"] == 1)

        # 6) 빈 리스트 ingest — 0 반환
        case("SQLite ingest 빈 리스트 → 0",
             eng.ingest_indexed_problems([]) == 0)

    finally:
        cleanup_sqlite(tag)
        cleanup_sqlite(tag + "M")


# ─── Firestore 모드 ───────────────────────────────────────────────────────
def smoke_firestore():
    print("\n=== Firestore ===")
    tag = f"fs{int(time.time())}"

    import firebase_admin
    from firebase_admin import credentials, firestore as _fs
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
    fs = _fs.client()

    os.environ["DATA_ENGINE"] = "firestore"
    from backend.data_engine import make_engine, get_engine_mode
    print(f"DATA_ENGINE = {get_engine_mode()}")
    eng = make_engine(LOCAL_DB, verbose=False)

    try:
        # 1) 신규 ingest — 3건
        items = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=3)
        n = eng.ingest_indexed_problems(items)
        case("Firestore ingest 신규 count", n == 3, f"(actual={n})")

        pid1 = items[0]["problem_id"]
        d = fetch_firestore_doc(fs, pid1)
        case("Firestore ingest server 문서 작성", d is not None and d.get("id") == pid1)
        case("Firestore ingest difficulty 저장", d and d.get("difficulty") == "C")
        case("Firestore ingest unit_code 저장", d and d.get("unit_code") == "G1")
        case("Firestore ingest 타 source exam_number=None",
             d and d.get("exam_number") is None)

        c = fetch_cache_row(eng.cache, pid1)
        case("Firestore ingest cache 동기화 (write-through)",
             c is not None and c.get("difficulty") == "C" and c.get("unit_code") == "G1")

        # 2) MOCK_EXAM exam_number 보정 (server + cache)
        mock_items = [
            {**make_indexed_items(tag + "M", source="MOCK_EXAM", count=1, base_endnote=15)[0]},
            {**make_indexed_items(tag + "M", source="MOCK_EXAM", count=1, base_endnote=23)[0]},
            {**make_indexed_items(tag + "M", source="MOCK_EXAM", count=1, base_endnote=31)[0]},
        ]
        eng.ingest_indexed_problems(mock_items)
        d_pn23 = fetch_firestore_doc(fs, mock_items[1]["problem_id"])
        c_pn23 = fetch_cache_row(eng.cache, mock_items[1]["problem_id"])
        case("Firestore MOCK_EXAM pn=23 → exam_number=23 (server)",
             d_pn23 and d_pn23.get("exam_number") == 23,
             f"(actual={d_pn23.get('exam_number') if d_pn23 else None})")
        case("Firestore MOCK_EXAM pn=23 → exam_number=23 (cache)",
             c_pn23 and c_pn23.get("exam_number") == 23)
        d_pn31 = fetch_firestore_doc(fs, mock_items[2]["problem_id"])
        case("Firestore MOCK_EXAM pn=31 → exam_number=23",
             d_pn31 and d_pn31.get("exam_number") == 23)

        # 3) 잠금 보존 — difficulty_locked
        eng.update_problem_meta(pid1, "difficulty", "A")
        new_items = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=1, difficulty="B")
        new_items[0]["problem_id"] = pid1
        new_items[0]["endnote_index"] = 1
        eng.ingest_indexed_problems(new_items)
        d = fetch_firestore_doc(fs, pid1)
        c = fetch_cache_row(eng.cache, pid1)
        case("Firestore 잠금 보존: diff_locked (server)",
             d and d.get("difficulty") == "A" and d.get("difficulty_locked") == 1)
        case("Firestore 잠금 보존: diff_locked (cache)",
             c and c.get("difficulty") == "A" and c.get("difficulty_locked") == 1)

        # 4) 잠금 보존 — unit_code_locked
        pid2 = items[1]["problem_id"]
        eng.update_problem_meta(pid2, "unit_code", "M2", "함수")
        new_items2 = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=1, unit_code="N3")
        new_items2[0]["problem_id"] = pid2
        new_items2[0]["endnote_index"] = 2
        new_items2[0]["middle_unit"] = "확률"
        eng.ingest_indexed_problems(new_items2)
        d = fetch_firestore_doc(fs, pid2)
        c = fetch_cache_row(eng.cache, pid2)
        case("Firestore 잠금 보존: uc_locked (server)",
             d and d.get("unit_code") == "M2" and d.get("middle_unit") == "함수"
             and d.get("unit_code_locked") == 1)
        case("Firestore 잠금 보존: uc_locked (cache)",
             c and c.get("unit_code") == "M2" and c.get("middle_unit") == "함수"
             and c.get("unit_code_locked") == 1)

        # 5) is_excluded 보존
        pid3 = items[2]["problem_id"]
        eng.set_exclusion_status([pid3], True)
        new_items3 = make_indexed_items(tag, source="SUNEUNG_SPECIAL", count=1)
        new_items3[0]["problem_id"] = pid3
        new_items3[0]["endnote_index"] = 3
        eng.ingest_indexed_problems(new_items3)
        d = fetch_firestore_doc(fs, pid3)
        c = fetch_cache_row(eng.cache, pid3)
        case("Firestore 재인덱싱이 is_excluded 유지 (server)",
             d and d.get("is_excluded") == 1)
        case("Firestore 재인덱싱이 is_excluded 유지 (cache)",
             c and c.get("is_excluded") == 1)

        # 6) 빈 리스트 ingest — 0 반환
        case("Firestore ingest 빈 리스트 → 0",
             eng.ingest_indexed_problems([]) == 0)

    finally:
        rem = cleanup_firestore(fs, tag) + cleanup_firestore(fs, tag + "M")
        if rem:
            print(f"  [cleanup] Firestore 잔재 {rem}건 정리")
        with eng.cache.connect() as conn:
            conn.execute("DELETE FROM problems WHERE id LIKE '_5smoke_%'")
            conn.commit()
        # 캐시 SQLite 의 problem_bank.db 잔재도 함께 정리
        cleanup_sqlite(tag)
        cleanup_sqlite(tag + "M")


def main():
    smoke_sqlite()
    smoke_firestore()
    print(f"\n{'=' * 40}\nPASS: {PASS}    FAIL: {FAIL}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
