import os
import sqlite3
import json
import time
from typing import List, Dict

class LocalDBEngine:
    """
    High-speed SQLite engine for localized problem indexing and statistics.
    Provides fast filtering and counting for the random extraction GUI.
    """
    def __init__(self, db_path: str = "problem_bank.db"):
        self.db_path = db_path
        self._init_db()
        self.init_user_tables()

    def _init_db(self):
        """Initializes the SQLite schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create problems table
        cursor.execute("""
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
                is_excluded INTEGER DEFAULT 0
            )
        """)
        
        # Migration: 컬럼 추가 (이미 존재하면 OperationalError → 정상, 로그만 출력)
        _migrations = [
            ("mapped_unit_code",    "ALTER TABLE problems ADD COLUMN mapped_unit_code TEXT"),
            ("is_excluded",         "ALTER TABLE problems ADD COLUMN is_excluded INTEGER DEFAULT 0"),
            ("source",              "ALTER TABLE problems ADD COLUMN source TEXT DEFAULT ''"),
            ("problem_number",      "ALTER TABLE problems ADD COLUMN problem_number INTEGER"),
            ("exam_number",         "ALTER TABLE problems ADD COLUMN exam_number INTEGER"),
            ("difficulty_locked",   "ALTER TABLE problems ADD COLUMN difficulty_locked INTEGER DEFAULT 0"),
            ("unit_code_locked",    "ALTER TABLE problems ADD COLUMN unit_code_locked INTEGER DEFAULT 0"),
            ("indexed_at",          "ALTER TABLE problems ADD COLUMN indexed_at REAL"),
            ("tags",                "ALTER TABLE problems ADD COLUMN tags TEXT DEFAULT ''"),
        ]
        for col_name, sql in _migrations:
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError:
                pass  # 이미 존재 — 정상
            except Exception as e:
                print(f"[DBEngine][Migration] '{col_name}' 컬럼 추가 실패 (예상치 못한 오류): {e}")

        # Create indexes for speed
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subject ON problems (subject)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_unit_code ON problems (unit_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mapped_unit_code ON problems (mapped_unit_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_difficulty ON problems (difficulty)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_year ON problems (year)")
        
        conn.commit()
        conn.close()

    def sync_json_dir(self, json_dir: str):
        """
        Synchronizes all JSON files in the directory with the SQLite DB.
        """
        if not os.path.exists(json_dir):
            print(f"[DBEngine] Directory not found: {json_dir}")
            return

        json_files = [f for f in os.listdir(json_dir) if f.lower().endswith(".json")]
        print(f"[DBEngine] Syncing {len(json_files)} files...")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        new_count = 0
        update_count = 0

        for filename in json_files:
            file_path = os.path.join(json_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data_list = json.load(f)
                
                for item in data_list:
                    # Convert lists/dicts to JSON strings for SQLite storage
                    pos_start_str = json.dumps(item.get("pos_start", []))
                    pos_end_str = json.dumps(item.get("pos_end", []))

                    # 수동 잠금 보호: 기존 레코드에서 locked 상태 조회
                    cursor.execute(
                        "SELECT difficulty_locked, unit_code_locked, difficulty, unit_code, middle_unit "
                        "FROM problems WHERE id=?",
                        (item.get("problem_id"),)
                    )
                    existing = cursor.fetchone()
                    if existing:
                        d_locked, u_locked, old_diff, old_uc, old_mu = existing
                        final_diff = old_diff if d_locked else item.get("difficulty")
                        final_uc   = old_uc   if u_locked else item.get("unit_code")
                        final_mu   = old_mu   if u_locked else item.get("middle_unit")
                        final_d_locked = d_locked
                        final_u_locked = u_locked
                    else:
                        final_diff = item.get("difficulty")
                        final_uc   = item.get("unit_code")
                        final_mu   = item.get("middle_unit")
                        final_d_locked = 0
                        final_u_locked = 0

                    # Use UPSERT (INSERT OR REPLACE)
                    cursor.execute("""
                        INSERT OR REPLACE INTO problems (
                            id, file_name, endnote_index, school, year, grade,
                            semester, exam_type, subject, curriculum, unit_code, mapped_unit_code,
                            source, difficulty, problem_type, pos_start, pos_end,
                            large_unit, middle_unit, indexed_at, file_hash, search_text,
                            difficulty_locked, unit_code_locked
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item.get("problem_id"),
                        item.get("file_name"),
                        item.get("endnote_index"),
                        item.get("school"),
                        item.get("year"),
                        item.get("grade"),
                        item.get("semester"),
                        item.get("exam_type"),
                        item.get("subject"),
                        item.get("curriculum"),
                        final_uc,
                        item.get("mapped_unit_code"),
                        item.get("source", ""),
                        final_diff,
                        item.get("problem_type"),
                        pos_start_str,
                        pos_end_str,
                        item.get("large_unit"),
                        final_mu,
                        item.get("indexed_at"),
                        item.get("file_hash"),
                        item.get("search_text"),
                        final_d_locked,
                        final_u_locked
                    ))
                    new_count += 1
            except Exception as e:
                print(f"[DBEngine] Error processing {filename}: {e}")

        conn.commit()
        conn.close()
        print(f"[DBEngine] Sync complete. Total records: {new_count}")

    def ingest_indexed_problems(self, items: List[Dict]) -> int:
        """인덱서가 새로 추출한 문제 결과를 problems 테이블에 upsert.

        Phase 5 — 기존 hwp_metadata_parser_v2._post_process_file 의 sqlite3
        직접 INSERT 블록을 엔진 인터페이스로 추출. main_gui.py 에서 활성
        엔진(LocalDBEngine | FirestoreEngine) 의 동일 시그니처를 호출.

        items: ProblemRecord 를 asdict() 한 dict 의 리스트.
               'problem_id' 키는 problems.id 컬럼으로 매핑.

        잠금 보존: difficulty_locked / unit_code_locked 가 1 이면 새 인덱싱
                   값으로 덮어쓰지 않음. is_excluded 는 항상 기존값 유지
                   (사용자 출제 제외 상태 보호).
        MOCK_EXAM exam_number: 1-22 그대로, 선택구간(확통/미적/기하)은
                                (problem_number-22-1) % 8 + 23 으로 보정.
        """
        if not items:
            return 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        count = 0
        try:
            for item in items:
                pid = item.get("problem_id") or item.get("id")
                if not pid:
                    continue

                pos_start_str = json.dumps(item.get("pos_start", []))
                pos_end_str = json.dumps(item.get("pos_end", []))

                pnum = item.get("endnote_index")
                src = item.get("source", "")
                if src == "MOCK_EXAM" and pnum is not None:
                    exam_num = pnum if pnum <= 22 else (pnum - 22 - 1) % 8 + 23
                else:
                    exam_num = None

                # 잠금/제외 상태 보존
                cursor.execute(
                    "SELECT difficulty_locked, unit_code_locked, difficulty, "
                    "unit_code, middle_unit, is_excluded "
                    "FROM problems WHERE id=?", (pid,)
                )
                existing = cursor.fetchone()
                if existing:
                    d_locked, u_locked, old_diff, old_uc, old_mu, old_excl = existing
                    final_diff = old_diff if d_locked else item.get("difficulty")
                    final_uc   = old_uc   if u_locked else item.get("unit_code")
                    final_mu   = old_mu   if u_locked else item.get("middle_unit")
                    final_d_locked = d_locked or 0
                    final_u_locked = u_locked or 0
                    final_excluded = old_excl or 0
                else:
                    final_diff = item.get("difficulty")
                    final_uc   = item.get("unit_code")
                    final_mu   = item.get("middle_unit")
                    final_d_locked = 0
                    final_u_locked = 0
                    final_excluded = 0

                cursor.execute("""
                    INSERT OR REPLACE INTO problems (
                        id, file_name, endnote_index, school, year, grade,
                        semester, exam_type, subject, curriculum, unit_code, mapped_unit_code,
                        source, difficulty, problem_type, pos_start, pos_end,
                        large_unit, middle_unit, indexed_at, file_hash, search_text,
                        problem_number, exam_number, tags,
                        difficulty_locked, unit_code_locked, is_excluded
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pid,
                    item.get("file_name"),
                    item.get("endnote_index"),
                    item.get("school"),
                    item.get("year"),
                    item.get("grade"),
                    item.get("semester"),
                    item.get("exam_type"),
                    item.get("subject"),
                    item.get("curriculum"),
                    final_uc,
                    item.get("mapped_unit_code"),
                    src,
                    final_diff,
                    item.get("problem_type"),
                    pos_start_str,
                    pos_end_str,
                    item.get("large_unit"),
                    final_mu,
                    item.get("indexed_at"),
                    item.get("file_hash"),
                    item.get("search_text"),
                    pnum,
                    exam_num,
                    item.get("tags", ""),
                    final_d_locked,
                    final_u_locked,
                    final_excluded,
                ))
                count += 1
            conn.commit()
        finally:
            conn.close()
        return count

    def query_counts(self, filters: Dict = None, include_excluded: bool = False) -> int:
        """
        Returns the count of problems matching the filters.
        Supports:
        - Exact match: {"subject": "Math"} -> subject = 'Math'
        - List (IN): {"difficulty": ["A", "B"]} -> difficulty IN ('A', 'B')
        - Operator (Dict): {"year": {"ne": "2023"}} -> year != '2023'
                           {"rate": {"gte": 30, "lte": 90}} -> rate >= 30 AND rate <= 90
                           {"school": {"like": "%High%"}} -> school LIKE '%High%'
        include_excluded: True이면 is_excluded=1 문제도 포함하여 카운트
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) FROM problems"
        params = []
        conditions = []
        
        if filters:
            for key, value in filters.items():
                if value is None or value == "":
                    continue
                
                # 1. List -> IN clause
                if isinstance(value, list):
                    if not value: continue # Skip empty list
                    placeholders = ",".join(["?"] * len(value))
                    conditions.append(f"{key} IN ({placeholders})")
                    params.extend(value)
                
                # 2. Dict -> Operator based
                elif isinstance(value, dict):
                    for op, val in value.items():
                        if op == "eq":
                            conditions.append(f"{key} = ?")
                            params.append(val)
                        elif op == "ne":
                            conditions.append(f"{key} != ?")
                            params.append(val)
                        elif op == "gt":
                            conditions.append(f"{key} > ?")
                            params.append(val)
                        elif op == "gte":
                            conditions.append(f"{key} >= ?")
                            params.append(val)
                        elif op == "lt":
                            conditions.append(f"{key} < ?")
                            params.append(val)
                        elif op == "lte":
                            conditions.append(f"{key} <= ?")
                            params.append(val)
                        elif op == "in":
                            if not val: continue
                            placeholders = ",".join(["?"] * len(val))
                            conditions.append(f"{key} IN ({placeholders})")
                            params.extend(val)
                        elif op == "not_in":
                            if not val: continue
                            placeholders = ",".join(["?"] * len(val))
                            conditions.append(f"{key} NOT IN ({placeholders})")
                            params.extend(val)
                        elif op == "like":
                            conditions.append(f"{key} LIKE ?")
                            params.append(val)
                
                # 3. Basic value -> Exact match
                else:
                    conditions.append(f"{key} = ?")
                    params.append(value)
        
        # include_excluded=False(기본)이면 제외된 문제 카운트에서 제외
        if not include_excluded:
            conditions.append("is_excluded = 0")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        try:
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
        except sqlite3.Error as e:
            print(f"[DB Error] Query: {query}, Params: {params}, Error: {e}")
            count = 0
        finally:
            conn.close()

        return count

    def search_schools(self, keyword: str, limit: int = 20) -> List[str]:
        """
        Searches for distinct school names matching the keyword.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            query = "SELECT DISTINCT school FROM problems WHERE school LIKE ? LIMIT ?"
            cursor.execute(query, (f"%{keyword}%", limit))
            results = [row[0] for row in cursor.fetchall() if row[0]]
        except sqlite3.Error as e:
            print(f"[DB Error] Search schools: {e}")
            results = []
        finally:
            conn.close()
        return results

    def search_mock_exam_brands(self, keyword: str) -> List[str]:
        """MOCK_EXAM id에서 keyword를 포함하는 시험명(파일명 prefix) 목록 반환."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT DISTINCT id FROM problems WHERE source='MOCK_EXAM' AND id LIKE ?",
                (f"%{keyword}%",)
            )
            rows = [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"[DB Error] search_mock_exam_brands: {e}")
            rows = []
        finally:
            conn.close()
        # id에서 문제번호 suffix(_NN) 제거 → 시험명 추출
        prefixes = set()
        for id_ in rows:
            parts = id_.rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                prefixes.add(parts[0])
            else:
                prefixes.add(id_)
        return sorted(prefixes)

    def get_ids_by_mock_brands(self, brands: List[str]) -> List[str]:
        """MOCK_EXAM 중 brands 키워드 중 하나라도 포함하는 문제 id 목록 반환."""
        if not brands:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            conditions = " OR ".join(["id LIKE ?" for _ in brands])
            params = [f"%{b}%" for b in brands]
            cursor.execute(
                f"SELECT id FROM problems WHERE source='MOCK_EXAM' AND ({conditions})",
                params
            )
            ids = [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"[DB Error] get_ids_by_mock_brands: {e}")
            ids = []
        finally:
            conn.close()
        return ids

    def get_unique_years(self) -> List[str]:
        """
        Returns a sorted list (descending) of distinct years available in the DB.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT year FROM problems ORDER BY year DESC")
            years = [str(row[0]) for row in cursor.fetchall() if row[0]]
            # Filter out non-numeric or empty if necessary, but keep text for flexibility
            return sorted(years, reverse=True)
        except sqlite3.Error as e:
            print(f"[DB Error] Get unique years: {e}")
            return []
        finally:
            conn.close()

    def fetch_random_problems(self, criteria_list: List[Dict], exclude_ids: List[str] = None, include_excluded: bool = False) -> List[Dict]:
        """
        Fetches random problems matching specific criteria.

        Args:
            criteria_list: List of dicts, each containing:
                - filters: dict of constraints (unit_code, difficulty, problem_type, etc.)
                - qty: number of problems to fetch for this criteria
            exclude_ids: List of problem IDs to exclude (for append mode)
            include_excluded: If True, also include problems with is_excluded=1

        Returns:
            List of problem dictionaries (row data converted to dict)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # Access columns by name
        cursor = conn.cursor()
        
        results = []
        # 누적 제외 ID: 외부에서 넘어온 것 + 이번 호출에서 이미 뽑은 것 모두 포함
        used_ids = list(exclude_ids or [])

        try:
            for criteria in criteria_list:
                filters = criteria.get("filters", {})
                qty = criteria.get("qty", 0)
                if qty <= 0: continue

                query = "SELECT * FROM problems"
                params = []
                conditions = []

                # Build dynamic WHERE clause
                for key, value in filters.items():
                    if value is None or value == "": continue

                    if isinstance(value, list): # IN
                        ph = ",".join(["?"] * len(value))
                        conditions.append(f"{key} IN ({ph})")
                        params.extend(value)
                    elif isinstance(value, dict): # Ops
                        for op, val in value.items():
                             if op == "in":
                                 ph = ",".join(["?"] * len(val))
                                 conditions.append(f"{key} IN ({ph})")
                                 params.extend(val)
                             elif op == "not_in":
                                 ph = ",".join(["?"] * len(val))
                                 conditions.append(f"{key} NOT IN ({ph})")
                                 params.extend(val)
                    else: # Exact
                        conditions.append(f"{key} = ?")
                        params.append(value)

                # 제외 문제 필터
                if not include_excluded:
                    conditions.append("is_excluded = 0")

                # 쿼리 간 중복 방지: 이미 뽑힌 ID 전부 제외
                if used_ids:
                    ph = ",".join(["?"] * len(used_ids))
                    conditions.append(f"id NOT IN ({ph})")
                    params.extend(used_ids)

                where_str = " WHERE " + " AND ".join(conditions) if conditions else ""
                query += where_str

                # Randomize and Limit
                query += " ORDER BY RANDOM() LIMIT ?"
                params.append(qty)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                for row in rows:
                    d = dict(row)
                    # Deserialize JSON fields
                    for field in ['pos_start', 'pos_end', 'problem_ids', 'metadata']:
                        if d.get(field) and isinstance(d[field], str):
                            try:
                                d[field] = json.loads(d[field])
                            except:
                                pass
                    results.append(d)
                    # 이번 쿼리에서 뽑힌 ID를 누적 → 다음 쿼리에서 중복 방지
                    used_ids.append(d['id'])

        except sqlite3.Error as e:
            print(f"[DB Error] Fetch random problems: {e}")
        finally:
            conn.close()

        return results

    def search_problems(self, filters: Dict, limit: int = 1000) -> List[Dict]:
        """
        Searches problems with specific filters (Stable sort for Management Tab).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        results = []
        try:
            query = "SELECT * FROM problems"
            params = []
            conditions = []
            
            for key, value in filters.items():
                if value is None or value == "": continue
                
                # Simple exact match or LIKE for school
                if key == "school":
                    conditions.append("school LIKE ?")
                    params.append(f"%{value}%")
                else:
                    conditions.append(f"{key} = ?")
                    params.append(value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            # Stable Sort: Year DESC, School, Grade(숫자순), ID
            # CAST(grade AS INTEGER): grade가 문자열이어도 숫자 정렬 보장 (1→2→3, not 1→10→2)
            query += " ORDER BY year DESC, school ASC, CAST(grade AS INTEGER) ASC, id ASC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            
        except sqlite3.Error as e:
            print(f"[DB Error] Search problems: {e}")
        finally:
            conn.close()
        return results

    def delete_problems(self, problem_ids: List[str]) -> int:
        """Deletes specific problems by ID."""
        if not problem_ids: return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        deleted_count = 0
        try:
            placeholders = ",".join(["?"] * len(problem_ids))
            query = f"DELETE FROM problems WHERE id IN ({placeholders})"
            cursor.execute(query, problem_ids)
            deleted_count = cursor.rowcount
            conn.commit()
        except sqlite3.Error as e:
            print(f"[DB Error] Delete problems: {e}")
        finally:
            conn.close()
        return deleted_count

    def check_duplicate_exam(self, meta: Dict) -> List[str]:
        """
        Checks if an exam with the same metadata already exists.
        Returns a list of distinct file_names found.
        Meta keys: school, year, grade, semester, exam_type, subject
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        found_files = []
        
        try:
            # Construct check query
            conditions = []
            params = []
            # Strict fields for exam identity
            check_fields = ["school", "year", "grade", "semester", "exam_type", "subject"]
            
            for field in check_fields:
                val = meta.get(field)
                if val:
                    conditions.append(f"{field} = ?")
                    params.append(val)
            
            if not conditions: return [] # Safety: don't match everything
            
            query = "SELECT DISTINCT file_name FROM problems WHERE " + " AND ".join(conditions)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            found_files = [row[0] for row in rows if row[0]]
            
        except sqlite3.Error as e:
            print(f"[DB Error] Check duplicate: {e}")
        finally:
            conn.close()
            
        return found_files

    def delete_exam(self, meta: Dict) -> int:
        """Deletes all problems matching the exam metadata (Bulk Delete)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        deleted_count = 0
        try:
            conditions = []
            params = []
            check_fields = ["school", "year", "grade", "semester", "exam_type", "subject"]
            
            for field in check_fields:
                val = meta.get(field, "")
                if val:
                    conditions.append(f"{field} = ?")
                    params.append(val)
            
            if not conditions: return 0
            
            query = "DELETE FROM problems WHERE " + " AND ".join(conditions)
            cursor.execute(query, params)
            deleted_count = cursor.rowcount
            conn.commit()
        except sqlite3.Error as e:
            print(f"[DB Error] Delete exam: {e}")
        finally:
            conn.close()
        return deleted_count

    def search_exams_grouped(self, filters: Dict) -> List[Dict]:
        """
        Searches exams (files) grouped by file_name.
        Returns adv_score(A×2+B×1), units_concat(시험범위 단원 목록) 포함.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        results = []
        try:
            query = """
                SELECT
                    school, file_name, year, grade, semester, exam_type, subject, curriculum,
                    COUNT(id) AS problem_count,
                    SUM(CASE WHEN difficulty='A' THEN 2
                             WHEN difficulty='B' THEN 1 ELSE 0 END) AS adv_score,
                    GROUP_CONCAT(DISTINCT
                        CASE
                            WHEN middle_unit IS NOT NULL AND middle_unit != '' THEN middle_unit
                            WHEN large_unit  IS NOT NULL AND large_unit  != '' THEN large_unit
                            ELSE NULL
                        END
                    ) AS units_concat
                FROM problems
            """

            params = []
            conditions = []

            for key, value in filters.items():
                if value is None or value == "":
                    continue
                if key == "school":
                    conditions.append("school LIKE ?")
                    params.append(f"%{value}%")
                elif key == "file_name_like":
                    conditions.append("file_name LIKE ?")
                    params.append(f"%{value}%")
                elif key == "unit_like":
                    # 시험범위 단원 검색 — 해당 단원을 포함한 문제가 하나라도 있는 파일
                    conditions.append(
                        "(middle_unit LIKE ? OR large_unit LIKE ?)"
                    )
                    params.append(f"%{value}%")
                    params.append(f"%{value}%")
                elif key == "unit_range_codes":
                    pass   # HAVING 절에서 처리 (아래)
                else:
                    conditions.append(f"{key} = ?")
                    params.append(value)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " GROUP BY file_name"

            # 단원 범위 코드 필터: 지정 범위 밖 unit_code 를 가진 문제가
            # 하나라도 있으면 해당 파일 제외 ("완전 포함만" 기능)
            unit_range = filters.get('unit_range_codes')
            if unit_range:
                ph = ",".join("?" * len(unit_range))
                query += f"""
                    HAVING SUM(
                        CASE WHEN unit_code IS NOT NULL
                                  AND unit_code != ''
                                  AND unit_code NOT IN ({ph})
                             THEN 1 ELSE 0 END
                    ) = 0
                """
                params.extend(unit_range)

            query += " ORDER BY school ASC, year DESC, file_name ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]

        except sqlite3.Error as e:
            print(f"[DB Error] Search exams grouped: {e}")
        finally:
            conn.close()
        return results

    def get_naesin_score_thresholds(self) -> tuple:
        """NAESIN_A 전체 시험파일의 상급총점(A×2+B×1) 분포로
        상위 백분위 임계 점수를 계산한다.

        반환: (th10, th30, th60)
          - score >= th10 → 최상 (상위 0~10%)
          - score >= th30 → 상   (상위 10~30%)
          - score >= th60 → 중   (상위 30~60%)
          - score <  th60 → 하   (상위 60~100%)
        데이터가 없으면 (0, 0, 0) 반환.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("""
                SELECT
                    file_name,
                    SUM(CASE WHEN difficulty='A' THEN 2
                             WHEN difficulty='B' THEN 1 ELSE 0 END) AS adv_score
                FROM problems
                WHERE source = 'NAESIN_A'
                GROUP BY file_name
                ORDER BY adv_score DESC
            """).fetchall()
        finally:
            conn.close()

        if not rows:
            return (0, 0, 0)

        scores = [r[1] or 0 for r in rows]
        n = len(scores)

        def _score_at(pct):
            idx = max(0, min(n - 1, int(n * pct) - 1))
            return scores[idx]

        th10 = _score_at(0.10)   # 상위 10% 경계
        th30 = _score_at(0.30)   # 상위 30% 경계
        th60 = _score_at(0.60)   # 상위 60% 경계
        return (th10, th30, th60)

    def get_subject_unit_codes(self, subject: str) -> list:
        """과목명으로 DB의 고유 unit_code 목록을 교육과정 순서(알파벳+숫자)로 반환.
        unit_hierarchy.json에 없는 2015 과목의 폴백용으로 사용.
        반환: ['A1', 'A2', 'B1', ...] 정렬된 리스트
        """
        import re
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("""
                SELECT DISTINCT unit_code
                FROM problems
                WHERE subject = ?
                  AND unit_code IS NOT NULL AND unit_code != ''
            """, (subject,)).fetchall()
        except sqlite3.Error as e:
            print(f"[DB Error] get_subject_unit_codes: {e}")
            return []
        finally:
            conn.close()

        codes = [r[0] for r in rows]

        def _key(c):
            m = re.match(r'^([A-Za-z]+)(\d+)$', c)
            return (m.group(1), int(m.group(2))) if m else (c, 0)

        return sorted(codes, key=_key)


    def get_unit_stats(self, file_names: List[str]) -> List[Dict]:
        """
        Gets unit distribution statistics for the specified files.
        Returns: [ {large_unit, middle_unit, count}, ... ]
        """
        if not file_names: return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        results = []
        try:
            placeholders = ",".join(["?"] * len(file_names))
            query = f"""
                SELECT 
                    large_unit, middle_unit, COUNT(id) as count
                FROM problems
                WHERE file_name IN ({placeholders})
                GROUP BY large_unit, middle_unit
                ORDER BY large_unit, middle_unit
            """
            
            cursor.execute(query, file_names)
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            
        except sqlite3.Error as e:
            print(f"[DB Error] Get unit stats: {e}")
        finally:
            conn.close()
        return results

    def delete_exams_by_filenames(self, file_names: List[str]) -> int:
        """Deletes all problems belonging to specific files."""
        if not file_names: return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        deleted_count = 0
        try:
            placeholders = ",".join(["?"] * len(file_names))
            query = f"DELETE FROM problems WHERE file_name IN ({placeholders})"
            cursor.execute(query, file_names)
            deleted_count = cursor.rowcount
            conn.commit()
        except sqlite3.Error as e:
            print(f"[DB Error] Delete exams by filenames: {e}")
        finally:
            conn.close()
        return deleted_count

    def get_problems_by_files(self, file_names: List[str]) -> List[Dict]:
        """
        Retrieves all problems belonging to specific files.
        Returns: List of problem dicts with is_excluded status.
        """
        if not file_names: return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        results = []
        try:
            placeholders = ",".join(["?"] * len(file_names))
            query = f"""
                SELECT id, file_name, school, year, grade, semester, exam_type, subject, 
                       large_unit, middle_unit, difficulty, problem_type, is_excluded, endnote_index,
                       pos_start, pos_end
                FROM problems
                WHERE file_name IN ({placeholders})
                ORDER BY file_name ASC, endnote_index ASC
            """
            
            cursor.execute(query, file_names)
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            
            # [FIX] Deserialize pos_start/pos_end from JSON strings to Python lists
            import json
            for r in results:
                for key in ('pos_start', 'pos_end'):
                    val = r.get(key)
                    if isinstance(val, str):
                        try:
                            r[key] = json.loads(val)
                        except (json.JSONDecodeError, ValueError):
                            r[key] = None
            
        except sqlite3.Error as e:
            print(f"[DB Error] Get problems by files: {e}")
        finally:
            conn.close()
        return results

    def set_exclusion_status(self, problem_ids: List[str], excluded: bool) -> int:
        """
        Updates the exclusion status for a list of problem IDs.

        [AUDIT] 호출 추적 로그를 stdout 과 exclusion_audit.log 에 기록.
        제외/해제 cascade 버그가 재발하면 이 로그로 즉시 원인 추적 가능.
        로그 형식:
          [EXCL_AUDIT YYYY-MM-DD HH:MM:SS] EXCLUDE|RESTORE count=N sample=[..] callers=...
        """
        if not problem_ids: return 0

        # ── AUDIT 로그 ───────────────────────────────────────────────
        # FirestoreEngine 이 cache 동기화 차원에서 위임하는 경우엔 이미
        # via=Firestore 라인이 찍혔으므로 여기서는 스킵 (이중 로그 방지).
        if os.environ.get("EXCL_AUDIT_SUPPRESS") != "1":
            try:
                import traceback, datetime
                stack = traceback.extract_stack()
                callers = []
                # 자기 자신(set_exclusion_status) 제외, 직전 호출자 3단계
                for fr in stack[-4:-1]:
                    callers.append(f"{os.path.basename(fr.filename)}:{fr.lineno} {fr.name}")
                ts     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                action = "EXCLUDE" if excluded else "RESTORE"
                sample = list(problem_ids[:3])
                line   = (
                    f"[EXCL_AUDIT {ts}] {action} count={len(problem_ids)} "
                    f"sample={sample} callers={' <- '.join(callers)}"
                )
                print(line)
                try:
                    log_path = os.path.join(os.path.dirname(self.db_path), "exclusion_audit.log")
                    with open(log_path, "a", encoding="utf-8") as _f:
                        _f.write(line + "\n")
                except Exception:
                    pass
            except Exception:
                pass
        # ─────────────────────────────────────────────────────────────

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        updated_count = 0

        try:
            val = 1 if excluded else 0
            placeholders = ",".join(["?"] * len(problem_ids))
            query = f"UPDATE problems SET is_excluded = ? WHERE id IN ({placeholders})"

            # Param order: value, id1, id2, ...
            params = [val] + problem_ids
            cursor.execute(query, params)
            updated_count = cursor.rowcount
            conn.commit()

        except sqlite3.Error as e:
            print(f"[DB Error] Set exclusion status: {e}")
        finally:
            conn.close()
        return updated_count

    def update_problem_meta(self, problem_id: str, field: str, value: str, unit_name: str = None):
        """
        난이도 또는 단원을 수동으로 수정하고 잠금 플래그를 설정.
        재인덱싱(sync_json_dir) 시에도 잠긴 필드는 유지됨.
        field: 'difficulty' 또는 'unit_code'
        unit_name: field='unit_code' 일 때 middle_unit에 저장할 한글명
        """
        allowed = {"difficulty", "unit_code"}
        if field not in allowed:
            raise ValueError(f"수정 불가 필드: {field}")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            if field == "unit_code":
                cursor.execute(
                    "UPDATE problems SET unit_code=?, middle_unit=?, unit_code_locked=1 WHERE id=?",
                    (value, unit_name or value, problem_id)
                )
            else:  # difficulty
                cursor.execute(
                    "UPDATE problems SET difficulty=?, difficulty_locked=1 WHERE id=?",
                    (value, problem_id)
                )
            conn.commit()
        except sqlite3.Error as e:
            print(f"[DB Error] update_problem_meta: {e}")
        finally:
            conn.close()

    def init_user_tables(self):
        """Initializes tables for user storage (Folders & Tests)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. User Directories (Folders)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_directories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Saved Tests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default',
                directory_id INTEGER,  -- NULL if in Root
                title TEXT NOT NULL,
                unit_summary TEXT,
                problem_ids TEXT,     -- JSON list of IDs
                metadata TEXT,        -- JSON extra data (options)
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(directory_id) REFERENCES user_directories(id) ON DELETE CASCADE
            )
        """)

        # 3. Problem Scores (채점 기록)
        # 시험지(test_id) 안의 각 문제(problem_id)에 대해 O/X 기록
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS problem_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                problem_id TEXT NOT NULL,
                is_correct INTEGER NOT NULL DEFAULT 1,  -- 1=O, 0=X
                scored_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(test_id) REFERENCES saved_tests(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_problem_id ON problem_scores (problem_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_test_id ON problem_scores (test_id)")

        # 4b. Problem Preferences (문항 선호도)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS problem_preferences (
                user_id   TEXT NOT NULL,
                problem_id TEXT NOT NULL,
                preference TEXT NOT NULL CHECK(preference IN ('Good', 'Soso', 'Bad')),
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, problem_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_user    ON problem_preferences (user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_problem  ON problem_preferences (problem_id)")

        # 4. 오답 폴더 보호: is_protected 컬럼 마이그레이션
        try:
            cursor.execute("ALTER TABLE user_directories ADD COLUMN is_protected INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # 이미 존재

        # 5. 보호 폴더 자동 부트스트랩은 제거됨 (4-B+ 이후 admin uid 기준).
        #    신규 사용자는 user_admin.create_user() 가 admin uid 기준으로 생성.

        conn.commit()
        conn.close()

    # --- Score Management (채점 기록) ---

    def save_scores(self, test_id: int, scores: Dict[str, int]) -> bool:
        """
        시험지의 채점 결과를 저장 (기존 기록 대체).
        scores: {problem_id: 1(O) or 0(X), ...}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # 해당 시험지의 기존 채점 기록 삭제 후 재삽입
            cursor.execute("DELETE FROM problem_scores WHERE test_id = ?", (test_id,))
            rows = [(test_id, pid, val) for pid, val in scores.items()]
            cursor.executemany(
                "INSERT INTO problem_scores (test_id, problem_id, is_correct) VALUES (?, ?, ?)", rows
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"[DB Error] save_scores: {e}")
            return False
        finally:
            conn.close()

    def get_scores_for_test(self, test_id: int) -> Dict[str, int]:
        """특정 시험지의 채점 기록 반환. {problem_id: is_correct}"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT problem_id, is_correct FROM problem_scores WHERE test_id = ?", (test_id,)
            )
            return {row["problem_id"]: row["is_correct"] for row in cursor.fetchall()}
        finally:
            conn.close()

    def get_correct_rate(self, problem_id: str) -> float:
        """
        문제의 전체 정답률 반환 (0.0 ~ 1.0).
        채점 기록이 없으면 None 반환.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*), SUM(is_correct) FROM problem_scores WHERE problem_id = ?",
                (problem_id,)
            )
            row = cursor.fetchone()
            total, correct = row[0], row[1]
            if not total:
                return None
            return (correct or 0) / total
        finally:
            conn.close()

    def get_correct_rates_bulk(self, problem_ids: List[str]) -> Dict[str, float]:
        """
        여러 문제의 정답률을 한 번에 반환. {problem_id: rate or None}
        """
        if not problem_ids:
            return {}
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            ph = ",".join(["?"] * len(problem_ids))
            cursor.execute(
                f"SELECT problem_id, COUNT(*), SUM(is_correct) FROM problem_scores "
                f"WHERE problem_id IN ({ph}) GROUP BY problem_id",
                problem_ids
            )
            result = {}
            for row in cursor.fetchall():
                pid, total, correct = row[0], row[1], row[2]
                result[pid] = (correct or 0) / total if total else None
            # 기록 없는 문제는 None
            for pid in problem_ids:
                if pid not in result:
                    result[pid] = None
            return result
        finally:
            conn.close()
    # --- Correct Rate Filter Helpers ---

    def get_problem_ids_by_rate(self, min_rate: float, max_rate: float) -> List[str]:
        """
        정답률이 min_rate ~ max_rate 범위(0.0~1.0)인 problem_id 목록 반환.
        채점 기록이 없는 문제는 결과에 포함되지 않는다.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT problem_id,
                       CAST(SUM(is_correct) AS REAL) / COUNT(*) AS rate
                FROM problem_scores
                GROUP BY problem_id
                HAVING rate >= ? AND rate <= ?
                """,
                (min_rate, max_rate)
            )
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"[DB Error] get_problem_ids_by_rate: {e}")
            return []
        finally:
            conn.close()

    def get_problem_ids_with_scores(self) -> List[str]:
        """채점 기록이 1건 이상 있는 모든 problem_id 반환."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT problem_id FROM problem_scores")
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"[DB Error] get_problem_ids_with_scores: {e}")
            return []
        finally:
            conn.close()

    # --- Folder Management ---

    def create_folder(self, name: str, user_id: str = "default", parent_id: int = None) -> Dict:
        """Creates a new folder. parent_id=None means root. Max depth=3."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO user_directories (user_id, name, parent_id) VALUES (?, ?, ?)",
                (user_id, name, parent_id)
            )
            conn.commit()
            return {"success": True, "id": cursor.lastrowid}
        except Exception as e:
            return {"success": False, "message": str(e)}
        finally:
            conn.close()

    def get_folders(self, user_id: str = "default") -> List[Dict]:
        """Returns all folders for a user"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM user_directories WHERE user_id = ? ORDER BY id", (user_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def rename_folder(self, folder_id: int, new_name: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE user_directories SET name = ? WHERE id = ?", (new_name, folder_id))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()

    def is_folder_protected(self, folder_id: int) -> bool:
        """보호된 폴더(오답 등) 여부 확인"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT is_protected FROM user_directories WHERE id = ?", (folder_id,))
            row = cursor.fetchone()
            return bool(row and row[0])
        finally:
            conn.close()

    def get_protected_folder_id(self, name: str, user_id: str) -> int:
        """보호된 폴더 ID 반환 (없으면 None). user_id 필수 (4-B+ 이후 default 인자 제거)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id FROM user_directories WHERE name=? AND user_id=? AND is_protected=1",
                (name, user_id)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def ensure_protected_folder(self, user_id: str, name: str = "오답") -> int:
        """멱등. 이미 있으면 그 id, 없으면 보호 폴더 발급. (SQLite-only 모드에서 authoritative.)"""
        existing = self.get_protected_folder_id(name, user_id)
        if existing is not None:
            return existing
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO user_directories (user_id, name, is_protected) VALUES (?, ?, 1)",
                (user_id, name)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def ensure_protected_folder_method(self, user_id: str, name: str = "오답") -> int:
        """FirestoreEngine 호환성 alias — server/ 코드(api_library.py)에서 이 이름으로 호출."""
        return self.ensure_protected_folder(user_id, name)

    def get_folder_test_count(self, folder_id: int) -> int:
        """폴더 내 시험지 수 반환 (하위 폴더 포함)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # 이 폴더 직접 포함된 시험지
            cursor.execute("SELECT COUNT(*) FROM saved_tests WHERE directory_id=?", (folder_id,))
            count = cursor.fetchone()[0]
            # 하위 폴더들 재귀적으로 확인
            cursor.execute("SELECT id FROM user_directories WHERE parent_id=?", (folder_id,))
            children = [r[0] for r in cursor.fetchall()]
            return count
        finally:
            conn.close()

    def get_all_subfolder_ids(self, folder_id: int) -> list:
        """폴더 및 모든 하위 폴더 ID 목록 반환"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        result = []
        try:
            def collect(fid):
                result.append(fid)
                cursor.execute("SELECT id FROM user_directories WHERE parent_id=?", (fid,))
                for (child_id,) in cursor.fetchall():
                    collect(child_id)
            collect(folder_id)
        finally:
            conn.close()
        return result

    def is_folder_empty(self, folder_id: int) -> bool:
        """폴더(+하위 폴더 전체)에 시험지가 없는지 확인"""
        all_ids = self.get_all_subfolder_ids(folder_id)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" * len(all_ids))
            cursor.execute(
                f"SELECT COUNT(*) FROM saved_tests WHERE directory_id IN ({placeholders})",
                all_ids
            )
            return cursor.fetchone()[0] == 0
        finally:
            conn.close()

    def delete_folder(self, folder_id: int) -> Dict:
        """폴더 삭제. 보호 폴더 삭제 불가. 시험지가 있으면 삭제 불가."""
        if self.is_folder_protected(folder_id):
            return {"success": False, "message": "보호된 폴더는 삭제할 수 없습니다."}
        if not self.is_folder_empty(folder_id):
            return {"success": False, "message": "폴더(또는 하위 폴더) 안에 시험지가 있어 삭제할 수 없습니다.\n시험지를 모두 삭제하거나 이동한 후 다시 시도하세요."}
        # 하위 폴더 포함 전체 삭제
        all_ids = self.get_all_subfolder_ids(folder_id)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            for fid in reversed(all_ids):  # 가장 깊은 것부터
                cursor.execute("DELETE FROM user_directories WHERE id=?", (fid,))
            conn.commit()
            return {"success": True}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}
        finally:
            conn.close()

    # --- Test Management ---

    def save_test(self, test_data: Dict, user_id: str = "default") -> Dict:
        """
        Saves a test.
        Args:
            test_data: {
                "id": Optional[int] (if update),
                "title": str,
                "unit_summary": str,
                "directory_id": Optional[int],
                "problem_ids": List[str] or JSON str,
                "metadata": Dict or JSON str
            }
        Returns: {"success": bool, "id": int, "message": str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 1. Total Limit Check (1000)
            stats = self.get_user_storage_stats(user_id)
            if stats['total_tests'] >= 1000 and 'id' not in test_data: # Only check on insert
                 return {"success": False, "message": "총 시험지 저장 한도(1000개)를 초과했습니다."}

            # 2. Folder Limit Check (30 root / 50 subfolder)
            # Need to count items in target folder
            dir_id = test_data.get('directory_id')

            # Check if we are inserting new item
            if 'id' not in test_data:
                if dir_id is not None:
                    query = "SELECT COUNT(*) FROM saved_tests WHERE user_id=? AND directory_id=?"
                    params = [user_id, dir_id]
                else:
                    query = "SELECT COUNT(*) FROM saved_tests WHERE user_id=? AND directory_id IS NULL"
                    params = [user_id]

                cursor.execute(query, params)
                cnt = cursor.fetchone()[0]

                # If Root, we need to add folder count too
                if dir_id is None:
                    cursor.execute("SELECT COUNT(*) FROM user_directories WHERE user_id=?", (user_id,))
                    folder_cnt = cursor.fetchone()[0]
                    if (cnt + folder_cnt) >= 30:
                         return {"success": False, "message": "최상위 경로에는 최대 30개 항목만 저장 가능합니다."}
                else:
                    # In Subfolder
                    if cnt >= 50:
                         return {"success": False, "message": "폴더 내에는 최대 50개 시험지만 저장 가능합니다."}

            # Prepare Data
            p_ids = test_data['problem_ids']
            if not isinstance(p_ids, str): p_ids = json.dumps(p_ids)
            
            meta = test_data.get('metadata', {})
            if not isinstance(meta, str): meta = json.dumps(meta)
            
            # Insert or Update
            if 'id' in test_data and test_data['id']:
                # Update
                cursor.execute("""
                    UPDATE saved_tests 
                    SET title=?, unit_summary=?, directory_id=?, problem_ids=?, metadata=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                """, (test_data['title'], test_data.get('unit_summary',''), dir_id, p_ids, meta, test_data['id']))
                new_id = test_data['id']
            else:
                # Insert
                cursor.execute("""
                    INSERT INTO saved_tests (user_id, directory_id, title, unit_summary, problem_ids, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, dir_id, test_data['title'], test_data.get('unit_summary',''), p_ids, meta))
                new_id = cursor.lastrowid
                
            conn.commit()
            return {"success": True, "id": new_id}
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e)}
        finally:
            conn.close()

    def get_all_tests_sorted(self, user_id: str = "default") -> List[Dict]:
        """
        Returns ALL saved tests with their folder info, sorted by created_at DESC (latest first).
        Used for the exclusion setting dialog (date mode).
        Each dict includes: id, title, unit_summary, directory_id, folder_name, created_at
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT st.id, st.title, st.unit_summary, st.directory_id,
                       st.created_at, ud.name AS folder_name
                FROM saved_tests st
                LEFT JOIN user_directories ud ON st.directory_id = ud.id
                WHERE st.user_id = ?
                ORDER BY st.created_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_tests(self, directory_id: int = None, user_id: str = "default") -> List[Dict]:
        """Get tests in a specific folder (or Root if directory_id is None)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            if directory_id is None:
                cursor.execute("SELECT * FROM saved_tests WHERE user_id=? AND directory_id IS NULL ORDER BY created_at DESC", (user_id,))
            else:
                cursor.execute("SELECT * FROM saved_tests WHERE user_id=? AND directory_id=? ORDER BY created_at DESC", (user_id, directory_id))
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
            
    def get_test_detail(self, test_id: int, user_id: str = "default") -> Dict:
        """
        Returns a test with its actual problem data loaded.
        Joins saved_tests with problems table using stored problem_ids.
        Returns: {
            'id': int,
            'title': str,
            'unit_summary': str,
            'directory_id': int,
            'problems': List[Dict]  <- actual problem data
        } or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM saved_tests WHERE id=? AND user_id=?",
                (test_id, user_id)
            )
            row = cursor.fetchone()
            if not row:
                return None

            test = dict(row)

            # Parse stored problem_ids
            p_ids = test.get('problem_ids', '[]')
            if isinstance(p_ids, str):
                try:
                    p_ids = json.loads(p_ids)
                except Exception:
                    p_ids = []

            problems = []
            if p_ids:
                placeholders = ",".join(["?"] * len(p_ids))
                cursor.execute(
                    f"SELECT * FROM problems WHERE id IN ({placeholders})",
                    p_ids
                )
                rows = cursor.fetchall()
                # Maintain original order
                order_map = {pid: i for i, pid in enumerate(p_ids)}
                raw = [dict(r) for r in rows]
                raw.sort(key=lambda r: order_map.get(r.get('id'), 9999))

                # Deserialize JSON fields
                for r in raw:
                    for field in ('pos_start', 'pos_end'):
                        val = r.get(field)
                        if isinstance(val, str):
                            try:
                                r[field] = json.loads(val)
                            except Exception:
                                r[field] = None
                    problems.append(r)

            test['problems'] = problems
            return test

        except sqlite3.Error as e:
            print(f"[DB Error] get_test_detail: {e}")
            return None
        finally:
            conn.close()

    def delete_test(self, test_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM problem_scores WHERE test_id=?", (test_id,))
            cursor.execute("DELETE FROM saved_tests WHERE id=?", (test_id,))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()

    def get_user_storage_stats(self, user_id: str = "default") -> Dict:
        """Returns counts for limit checking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # 1. Total Tests
            cursor.execute("SELECT COUNT(*) FROM saved_tests WHERE user_id=?", (user_id,))
            total_tests = cursor.fetchone()[0]
            
            # 2. Root Items (Folders + Tests in Root)
            cursor.execute("SELECT COUNT(*) FROM user_directories WHERE user_id=?", (user_id,))
            root_folders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM saved_tests WHERE user_id=? AND directory_id IS NULL", (user_id,))
            root_tests = cursor.fetchone()[0]
            
            root_items = root_folders + root_tests
            
            return {
                "total_tests": total_tests,
                "root_items": root_items
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────
    # 문항 선호도 관리 (Preference Management)
    # ─────────────────────────────────────────────────────────────

    def get_all_problem_ids(self) -> list:
        """problems 테이블의 모든 id를 리스트로 반환."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT id FROM problems").fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    def set_preference(self, user_id: str, problem_id, preference) -> bool:
        """문항 선호도 저장 (Good/Soso/Bad). preference=None이면 삭제."""
        conn = sqlite3.connect(self.db_path)
        try:
            if preference is None:
                conn.execute(
                    "DELETE FROM problem_preferences WHERE user_id=? AND problem_id=?",
                    (user_id, str(problem_id))
                )
            else:
                conn.execute("""
                    INSERT INTO problem_preferences (user_id, problem_id, preference, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(user_id, problem_id) DO UPDATE SET
                        preference = excluded.preference,
                        updated_at = excluded.updated_at
                """, (user_id, str(problem_id), preference))
            conn.commit()
            return True
        except Exception as e:
            print(f"[DB] set_preference 오류: {e}")
            return False
        finally:
            conn.close()

    def get_preferences_bulk(self, user_id: str, problem_ids: list) -> dict:
        """여러 문항의 선호도를 일괄 조회.
        반환: {problem_id(str): 'Good'/'Soso'/'Bad'}"""
        if not problem_ids:
            return {}
        str_ids = [str(pid) for pid in problem_ids]
        conn = sqlite3.connect(self.db_path)
        try:
            ph = ",".join("?" * len(str_ids))
            rows = conn.execute(
                f"SELECT problem_id, preference FROM problem_preferences "
                f"WHERE user_id=? AND problem_id IN ({ph})",
                [user_id] + str_ids
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        finally:
            conn.close()

    def get_all_preference_user_ids(self) -> list:
        """선호도를 등록한 모든 사용자 ID 목록"""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM problem_preferences"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def get_problem_ids_by_preference(self, user_ids: list, preferences: list,
                                      candidate_ids: list = None) -> set:
        """선호도 기준으로 문제 ID 필터링 (str 집합 반환).

        - user_ids     : 고려할 사용자 ID 목록
        - preferences  : 포함할 선호도 ['Good','Soso','Bad']
        - candidate_ids: 후보 ID 목록 (None이면 pref_map에만 존재하는 것으로 제한)
        - 미설정 문항은 'Soso' 로 처리
        """
        if not user_ids or not preferences:
            return set()
        pref_set = set(preferences)

        conn = sqlite3.connect(self.db_path)
        try:
            uid_ph = ",".join("?" * len(user_ids))
            rows = conn.execute(
                f"SELECT problem_id, preference FROM problem_preferences "
                f"WHERE user_id IN ({uid_ph})",
                list(user_ids)
            ).fetchall()
        finally:
            conn.close()

        # problem_id → 이 사용자들의 선호도 집합
        pref_map: dict = {}
        for pid, pref in rows:
            pref_map.setdefault(str(pid), set()).add(pref)

        if candidate_ids is None:
            # candidate를 모르므로 pref_map 기준
            return {pid for pid, prefs in pref_map.items() if prefs & pref_set}
        else:
            result = set()
            for pid in candidate_ids:
                spid = str(pid)
                if spid in pref_map:
                    if pref_map[spid] & pref_set:
                        result.add(spid)
                else:
                    # 미설정 → Soso 처리
                    if 'Soso' in pref_set:
                        result.add(spid)
            return result


if __name__ == "__main__":
    # Test execution
    engine = LocalDBEngine("g:/문제은행/문제은행2/problem_bank.db")
    engine.sync_json_dir("g:/문제은행/문제은행2/indexed_results")
    
    # Test query
    total = engine.query_counts()
    print(f"Total problems in DB: {total}")
    
    # Example filter query
    math_count = engine.query_counts({"subject": "수학(상)"})
    print(f"Subject '수학(상)' count: {math_count}")
