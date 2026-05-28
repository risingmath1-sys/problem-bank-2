# -*- coding: utf-8 -*-
"""
Phase 4-A: problems 컬렉션 로컬 SQLite 캐시 미러.

목적:
  Firestore problems(29K+) 를 매 쿼리마다 호출하면 비용/지연 모두 ✗.
  로컬 SQLite 미러를 두고 모든 READ 는 캐시에서 수행.

배치/정책:
  - 위치: %APPDATA%\\naegiwangbank\\problems_cache.sqlite
  - 스키마: 원본 SQLite `problems` 테이블과 byte-for-byte 동일 (인덱스 포함)
  - sync 모드:
      full       : 캐시 비웠다 받기 (첫 부팅용)
      incremental: cache 안 max(updated_at) > watermark 기준으로 추가/갱신만 받기
  - watermark 는 캐시 자체에 저장 (별도 메타 테이블) — 캐시 파일만 보면 자급
  - 동시성: 단일 GUI 프로세스 가정 (multi-instance 동기화 불필요)

사용법:
  cache = ProblemsCache(firestore_client, key_path)
  cache.ensure_synced()              # 부팅 시 1회: 캐시 없으면 full, 있으면 incremental
  with cache.connect() as conn:      # FirestoreEngine 이 내부 SQL 쿼리에 사용
      conn.execute("SELECT ...").fetchall()
"""
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from typing import Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from google.cloud.firestore_v1 import DocumentSnapshot


# ----- 경로 ---------------------------------------------------------------
def default_cache_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "naegiwangbank")


def default_cache_path() -> str:
    return os.path.join(default_cache_dir(), "problems_cache.sqlite")


def default_seed_path() -> str:
    """배포 시 동봉된 시드 캐시 파일 경로 (backend/seed/problems_cache.sqlite).

    첫 부팅 사용자가 Firestore 에서 29K+ 문항을 받지 않도록, admin 이
    `ProblemsCache.export_seed()` 로 만들어둔 시드를 함께 배포한다.
    """
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(backend_dir, "seed", "problems_cache.sqlite")


# ----- 스키마 -------------------------------------------------------------
# 원본 SQLite problems 테이블과 동일한 컬럼 (db_engine.py:23-47 + migrations)
PROBLEM_COLUMNS = [
    "id",                 # PK
    "file_name",
    "endnote_index",
    "school",
    "year",
    "grade",
    "semester",
    "exam_type",
    "subject",
    "curriculum",
    "unit_code",
    "mapped_unit_code",
    "difficulty",
    "problem_type",
    "pos_start",          # JSON string
    "pos_end",            # JSON string
    "large_unit",
    "middle_unit",
    "file_hash",
    "search_text",
    "is_excluded",        # 0|1
    "source",
    "problem_number",
    "exam_number",
    "tags",
    "difficulty_locked",  # 0|1
    "unit_code_locked",   # 0|1
    "indexed_at",         # REAL (epoch sec)
]

# 캐시는 원본 + updated_at (epoch float) 추가 (incremental sync watermark용)
CACHE_COLUMNS = PROBLEM_COLUMNS + ["updated_at"]

CREATE_PROBLEMS_SQL = f"""
CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY,
    file_name TEXT,
    endnote_index INTEGER,
    school TEXT,
    year TEXT,
    grade TEXT,
    semester TEXT,
    exam_type TEXT,
    subject TEXT,
    curriculum TEXT,
    unit_code TEXT,
    mapped_unit_code TEXT,
    difficulty TEXT,
    problem_type TEXT,
    pos_start TEXT,
    pos_end TEXT,
    large_unit TEXT,
    middle_unit TEXT,
    file_hash TEXT,
    search_text TEXT,
    is_excluded INTEGER DEFAULT 0,
    source TEXT DEFAULT '',
    problem_number INTEGER,
    exam_number INTEGER,
    tags TEXT DEFAULT '',
    difficulty_locked INTEGER DEFAULT 0,
    unit_code_locked INTEGER DEFAULT 0,
    indexed_at REAL,
    updated_at REAL
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_subject ON problems (subject)",
    "CREATE INDEX IF NOT EXISTS idx_unit_code ON problems (unit_code)",
    "CREATE INDEX IF NOT EXISTS idx_mapped_unit_code ON problems (mapped_unit_code)",
    "CREATE INDEX IF NOT EXISTS idx_difficulty ON problems (difficulty)",
    "CREATE INDEX IF NOT EXISTS idx_year ON problems (year)",
    "CREATE INDEX IF NOT EXISTS idx_source ON problems (source)",
    "CREATE INDEX IF NOT EXISTS idx_file_name ON problems (file_name)",
    "CREATE INDEX IF NOT EXISTS idx_updated_at ON problems (updated_at)",
]

CREATE_META_SQL = """
CREATE TABLE IF NOT EXISTS cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""


# ----- 메인 매니저 ---------------------------------------------------------
class ProblemsCache:
    """problems 컬렉션 로컬 SQLite 미러."""

    def __init__(self, firestore_client, cache_path: Optional[str] = None,
                 verbose: bool = True):
        self.fs = firestore_client
        self.cache_path = cache_path or default_cache_path()
        self.verbose = verbose
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        self._init_schema()

    def _log(self, msg: str):
        if self.verbose:
            print(f"[ProblemsCache] {msg}")

    # --- schema ---
    def _init_schema(self):
        with self.connect() as conn:
            conn.execute(CREATE_PROBLEMS_SQL)
            conn.execute(CREATE_META_SQL)
            for sql in CREATE_INDEXES:
                conn.execute(sql)
            conn.commit()

    # --- connection ---
    @contextmanager
    def connect(self):
        """sqlite3 connection. caller 가 commit/rollback 책임."""
        conn = sqlite3.connect(self.cache_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # --- meta ---
    def get_meta(self, key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM cache_meta WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def set_meta(self, key: str, value: str):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO cache_meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()

    def count(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]

    def max_updated_at(self) -> Optional[float]:
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(updated_at) FROM problems").fetchone()
            return row[0] if row and row[0] is not None else None

    # --- conversion ---
    @staticmethod
    def _doc_to_row(snap: DocumentSnapshot) -> Optional[tuple]:
        d = snap.to_dict()
        if not d:
            return None
        # Firestore Timestamp → epoch float
        ua = d.get("updated_at")
        ua_epoch = None
        if ua is not None:
            try:
                ua_epoch = ua.timestamp()
            except Exception:
                ua_epoch = None
        # 문서 ID 우선 (필드 누락 안전)
        prob_id = d.get("id") or snap.id
        values = []
        for col in PROBLEM_COLUMNS:
            if col == "id":
                values.append(prob_id)
            else:
                v = d.get(col)
                # Firestore 에 list/dict 로 저장된 필드 (예: pos_start/pos_end 가 [sec,para,char])
                # → SQLite 바인딩 불가하므로 JSON 직렬화
                if isinstance(v, (list, dict)):
                    v = json.dumps(v, ensure_ascii=False)
                values.append(v)
        values.append(ua_epoch)
        return tuple(values)

    # --- sync ---
    def full_sync(self) -> int:
        """전체 다운로드 (캐시 초기화 후 적재). 반환: 적재 건수."""
        self._log("full sync 시작 (캐시 초기화)")
        t0 = time.time()
        with self.connect() as conn:
            conn.execute("DELETE FROM problems")
            conn.commit()

            placeholders = ",".join(["?"] * len(CACHE_COLUMNS))
            cols_sql = ",".join(CACHE_COLUMNS)
            sql = f"INSERT OR REPLACE INTO problems({cols_sql}) VALUES({placeholders})"

            n = 0
            buffer = []
            BATCH = 1000
            for snap in self.fs.collection("problems").stream():
                row = self._doc_to_row(snap)
                if row is None:
                    continue
                buffer.append(row)
                if len(buffer) >= BATCH:
                    conn.executemany(sql, buffer)
                    conn.commit()
                    n += len(buffer)
                    buffer.clear()
                    self._log(f"  ... {n}건 적재")
            if buffer:
                conn.executemany(sql, buffer)
                conn.commit()
                n += len(buffer)

        dt = time.time() - t0
        self.set_meta("last_full_sync", str(time.time()))
        self.set_meta("last_sync_count", str(n))
        self._log(f"full sync 완료: {n}건 / {dt:.1f}s")
        return n

    def incremental_sync(self) -> int:
        """캐시 max(updated_at) > watermark 기준 갱신분만 받기. 반환: 갱신 건수."""
        wm = self.max_updated_at()
        if wm is None:
            self._log("incremental: watermark 없음 → full_sync 로 대체")
            return self.full_sync()

        self._log(f"incremental sync 시작 (watermark = {wm})")
        # Firestore Timestamp 비교용
        from datetime import datetime, timezone
        wm_dt = datetime.fromtimestamp(wm, tz=timezone.utc)

        t0 = time.time()
        n = 0
        with self.connect() as conn:
            placeholders = ",".join(["?"] * len(CACHE_COLUMNS))
            cols_sql = ",".join(CACHE_COLUMNS)
            sql = f"INSERT OR REPLACE INTO problems({cols_sql}) VALUES({placeholders})"

            buffer = []
            BATCH = 500
            q = (
                self.fs.collection("problems")
                .where(filter=FieldFilter("updated_at", ">", wm_dt))
                .order_by("updated_at")
            )
            for snap in q.stream():
                row = self._doc_to_row(snap)
                if row is None:
                    continue
                buffer.append(row)
                if len(buffer) >= BATCH:
                    conn.executemany(sql, buffer)
                    conn.commit()
                    n += len(buffer)
                    buffer.clear()
            if buffer:
                conn.executemany(sql, buffer)
                conn.commit()
                n += len(buffer)

        dt = time.time() - t0
        self.set_meta("last_incremental_sync", str(time.time()))
        if n > 0:
            self._log(f"incremental sync 완료: {n}건 갱신 / {dt:.1f}s")
        else:
            self._log(f"incremental sync 완료: 변경 없음 ({dt:.2f}s)")
        return n

    def ensure_synced(self) -> int:
        """부팅 시 호출: 캐시 비어있으면 시드 임포트 → incremental, 아니면 incremental.

        2026-05-23: 정합성 검사 추가. incremental 후 캐시 count vs Firestore count 비교.
        차이 > 0.5% 이거나 절대 차이 > 50 이면 stale 의심 → 자동 full_sync.
        외부에서 batch.update 등으로 updated_at 갱신 없이 쓴 경우(우회 케이스) 자동 복구.
        """
        if self.count() == 0:
            if self._try_import_seed():
                # 시드 임포트 성공 → 시드 시점 이후 변경분만 받기
                self.incremental_sync()
            else:
                # 시드 없음 → 첫 부팅 = 전체 다운로드
                return self.full_sync()
        else:
            self.incremental_sync()

        # ── 정합성 검사 ──
        try:
            self._integrity_check_and_repair()
        except Exception as e:
            self._log(f"정합성 검사 실패: {e} (계속 진행)")
        return self.count()

    def _integrity_check_and_repair(self):
        """캐시 vs Firestore 카운트 비교. 차이 크면 full_sync 강제.

        호출 비용: Firestore aggregation count 1회 (1 read = 거의 무료).
        """
        try:
            from google.cloud.firestore_v1.aggregation import AggregationQuery
            agg = self.fs.collection("problems").count()
            res = agg.get()
            fs_count = res[0][0].value if res and res[0] else 0
        except Exception:
            # Aggregation count 미지원 환경 → 스킵 (운영 비용 고려해 stream count 안 함)
            self._log("Firestore aggregation count 미지원 → 정합성 검사 스킵")
            return

        cache_count = self.count()
        if fs_count == 0:
            return
        diff = abs(fs_count - cache_count)
        diff_pct = diff * 100.0 / fs_count
        self._log(f"정합성 검사: cache={cache_count} vs firestore={fs_count} (Δ={diff}, {diff_pct:.2f}%)")
        if diff_pct > 0.5 or diff > 50:
            self._log(f"⚠️  캐시 stale 의심 → full_sync 자동 실행")
            self.full_sync()

    # --- seed (첫 부팅 폭탄 방지) ---
    def _try_import_seed(self) -> bool:
        """배포 동봉 시드를 캐시 파일로 복사. 시드 없으면 False."""
        seed_path = default_seed_path()
        if not os.path.isfile(seed_path):
            return False
        try:
            # 현 schema 와 다를 수 있으니, 시드 → 임시 → 본 캐시 (덮어쓰기)
            shutil.copyfile(seed_path, self.cache_path)
            self._log(f"seed 임포트 완료: {seed_path} → {self.cache_path}")
            # schema/인덱스 보강 (시드가 구 스키마일 수도 있음)
            self._init_schema()
            n = self.count()
            self._log(f"seed 적재 결과: {n}건")
            return n > 0
        except Exception as e:
            self._log(f"seed 임포트 실패: {e} → full_sync 로 진행")
            return False

    def export_seed(self, target_path: Optional[str] = None) -> str:
        """현재 캐시를 시드 파일로 복사. admin 이 배포 직전에 1회 실행.

        반환: 작성된 파일의 절대 경로.
        """
        target = target_path or default_seed_path()
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        # 안전한 dump (락 없음 보장 위해 backup API 사용)
        with self.connect() as src:
            dst = sqlite3.connect(target)
            try:
                src.backup(dst)
            finally:
                dst.close()
        n = self.count()
        self._log(f"seed export 완료: {target} ({n}건)")
        return os.path.abspath(target)

    def upsert_one(self, doc_dict: dict):
        """admin write 직후 캐시도 즉시 갱신 (Phase 4-D 에서 사용)."""
        ua = doc_dict.get("updated_at")
        ua_epoch = None
        if ua is not None:
            try:
                ua_epoch = ua.timestamp()
            except Exception:
                ua_epoch = ua if isinstance(ua, (int, float)) else time.time()
        else:
            ua_epoch = time.time()

        values = []
        for col in PROBLEM_COLUMNS:
            values.append(doc_dict.get(col))
        values.append(ua_epoch)

        placeholders = ",".join(["?"] * len(CACHE_COLUMNS))
        cols_sql = ",".join(CACHE_COLUMNS)
        with self.connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO problems({cols_sql}) VALUES({placeholders})",
                values,
            )
            conn.commit()

    def delete_one(self, problem_id: str):
        with self.connect() as conn:
            conn.execute("DELETE FROM problems WHERE id=?", (problem_id,))
            conn.commit()

    def delete_many(self, problem_ids):
        ids = list(problem_ids)
        if not ids:
            return
        with self.connect() as conn:
            qmark = ",".join(["?"] * len(ids))
            conn.execute(f"DELETE FROM problems WHERE id IN ({qmark})", ids)
            conn.commit()
