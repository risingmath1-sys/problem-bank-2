"""원본 HWP 파일 전수조사 -- problems.file_name 들이 실제 디스크에 있는지 확인.
사용: python scripts/audit_missing_files.py
"""
import sqlite3
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "problem_bank.db"


def build_hwp_index(root):
    idx = {}
    if not os.path.exists(root):
        print(f"[WARN] HWP_SOURCE_ROOT 없음: {root}")
        return idx
    print(f"[INFO] HWP 인덱싱 시작: {root}")
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if fname.lower().endswith(".hwp"):
                idx.setdefault(fname, os.path.join(dirpath, fname))
    print(f"[INFO] HWP 인덱싱 완료: {len(idx)}건")
    return idx


def main():
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB 없음: {DB_PATH}")
        sys.exit(1)

    sys.path.insert(0, os.getcwd())
    from server import config
    hwp_root = str(config.HWP_SOURCE_ROOT)
    hwp_index = build_hwp_index(hwp_root)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # problems 의 file_name 별 통계: (file_name, source, count)
    cur.execute("""
        SELECT file_name, source, COUNT(*)
        FROM problems
        WHERE file_name IS NOT NULL AND file_name != ''
        GROUP BY file_name, source
    """)
    rows = cur.fetchall()

    # file_name 별로 (source, count) 누적
    per_file = defaultdict(lambda: {"sources": defaultdict(int), "total": 0})
    for fname, source, cnt in rows:
        per_file[fname]["sources"][source or "?"] += cnt
        per_file[fname]["total"] += cnt

    # null/blank file_name 별도
    cur.execute("SELECT COUNT(*) FROM problems WHERE file_name IS NULL OR file_name = ''")
    null_count = cur.fetchone()[0]

    total_files = len(per_file)
    missing = []
    by_source_missing = defaultdict(int)
    by_source_total = defaultdict(int)

    for fname, info in per_file.items():
        for src, n in info["sources"].items():
            by_source_total[src] += n
        if fname not in hwp_index:
            missing.append((fname, info["total"], dict(info["sources"])))
            for src, n in info["sources"].items():
                by_source_missing[src] += n

    print()
    print("=" * 78)
    print("[원본 HWP 파일 전수조사]")
    print("=" * 78)
    print(f"  DB에 등록된 파일명 (DISTINCT) : {total_files}")
    print(f"  디스크 HWP 파일 (인덱싱)      : {len(hwp_index)}")
    print(f"  file_name NULL/빈값 (problems): {null_count}")
    print(f"  [파일 없음] 등록 파일명       : {len(missing)}")
    print()

    print("-" * 78)
    print("[소스별 누락 통계]")
    print("-" * 78)
    print(f"  {'source':<20} {'누락 problems':>15} / {'총 problems':>12}")
    for src in sorted(set(list(by_source_total.keys()) + list(by_source_missing.keys()))):
        print(f"  {src:<20} {by_source_missing.get(src, 0):>15,} / {by_source_total.get(src, 0):>12,}")
    print()

    if missing:
        print("-" * 78)
        print(f"[파일 없음] file_name {len(missing)}건 (problems 많은 순)")
        print("-" * 78)
        missing.sort(key=lambda x: -x[1])
        for fname, total, srcs in missing[:80]:
            src_str = ",".join(f"{s}={n}" for s, n in srcs.items())
            print(f"  problems={total:>4}  src=[{src_str}]  {fname}")
        if len(missing) > 80:
            print(f"  ... 외 {len(missing) - 80}건")

    print()
    print("=" * 78)
    print("[완료]")
    print("=" * 78)


if __name__ == "__main__":
    main()
