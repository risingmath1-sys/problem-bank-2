# -*- coding: utf-8 -*-
"""
Phase 4-A/4-B: Firestore + 로컬 캐시 하이브리드 엔진.

전략 (Phase 4-A 완료):
  - problems READ (15개 메서드)
      → 로컬 SQLite 캐시 파일에 LocalDBEngine 을 띄워 그대로 위임.
        ⇒ 기존 LocalDBEngine 의 SQL 쿼리 100% 재사용. 호환성 ★★★.
  - problems WRITE / 개인 데이터 WRITE
      → 기존 SQLite (problem_bank.db) 로 폴백.
        4-C/D 에서 단계적으로 Firestore 직접 호출로 교체.

전략 (Phase 4-B 추가):
  - 개인 데이터 READ (17개 메서드)
      → Firestore 직접 호출. 캐시 X (호출 빈도 낮음 + 신선도 우선).
        결과는 SQLite 출력 shape (dict 키/타입) 에 맞춰 정규화.

부팅 흐름:
  FirestoreEngine() → ProblemsCache.ensure_synced() → 캐시 최신화
                    → cache_engine = LocalDBEngine(cache_path)
                    → local_engine = LocalDBEngine(problem_bank.db)

호출 라우팅:
  engine.get_problems_by_files(...)   # in PROBLEMS_READ → cache_engine
  engine.get_folders(uid)             # 정의된 메서드   → Firestore (4-B)
  engine.save_test(...)               # 그 외           → local_engine (4-C 에서 교체)

설계 원본:
  로그인시스템설계도.md §5 Phase 4
  로그인시스템_작업현황.md Phase 4
"""
import datetime
import os
from typing import Dict, List, Optional

from google.cloud.firestore_v1.base_query import FieldFilter

# problems 컬렉션 READ 메서드 — 캐시(LocalDBEngine on cache file) 위임.
# db_engine.py 의 public 메서드를 카테고리화해서 추출.
PROBLEMS_READ = frozenset({
    "query_counts",
    "search_schools",
    "search_mock_exam_brands",
    "get_ids_by_mock_brands",
    "get_unique_years",
    "fetch_random_problems",
    "search_problems",
    "check_duplicate_exam",
    "search_exams_grouped",
    "get_naesin_score_thresholds",
    "get_subject_unit_codes",
    "get_unit_stats",
    "get_problems_by_files",
    "get_all_problem_ids",
    # is_excluded / source 등 problems 테이블 단독 READ
})


class FirestoreEngine:
    """problems 캐시 + Firestore 개인 데이터 하이브리드.

    Phase 4-A: problems READ 만 캐시로 라우팅. 그 외는 LocalDBEngine 그대로.
    Phase 4-B 이후: 개인 데이터를 Firestore 직접 호출로 교체.
    """

    def __init__(self, local_db_path: str,
                 firestore_client=None,
                 cache_path: Optional[str] = None,
                 verbose: bool = True):
        from backend.data_cache import ProblemsCache
        from backend.db_engine import LocalDBEngine

        self.verbose = verbose
        self.db_path = local_db_path  # 개인데이터 폴백용

        # Firestore 클라이언트 확보
        if firestore_client is None:
            firestore_client = self._init_default_firestore()
        self.fs = firestore_client

        # 캐시 매니저 — 부팅 시 동기화
        self.cache = ProblemsCache(self.fs, cache_path=cache_path, verbose=verbose)
        self._log("부팅 동기화 시작")
        self.cache.ensure_synced()
        self._log(f"캐시 준비 완료 ({self.cache.count()}건 @ {self.cache.cache_path})")

        # 캐시용 LocalDBEngine — problems READ 위임 대상
        # (init_user_tables 부수효과로 캐시 파일에 빈 user 테이블이 생기지만
        #  사용되지 않으므로 무해. 4-D 캐시 무효화 단계에서 정리 검토.)
        self.cache_engine = LocalDBEngine(self.cache.cache_path)

        # 폴백 엔진 — 그 외 모든 메서드 (개인데이터, problems WRITE 등)
        self.local_engine = LocalDBEngine(local_db_path)

    # ----- 공통 -------------------------------------------------------
    def _log(self, msg: str):
        if self.verbose:
            print(f"[FirestoreEngine] {msg}")

    @staticmethod
    def _init_default_firestore():
        """firebase_admin 이 이미 초기화돼 있다고 가정."""
        from firebase_admin import firestore
        return firestore.client()

    # ----- 라우팅 -----------------------------------------------------
    def __getattr__(self, name):
        """instance 에 없는 속성 호출 시 라우팅.

        - problems READ → cache_engine
        - 그 외          → local_engine
        """
        # __init__ 실행 중 self.cache 등 접근하다 AttributeError 나면
        # 무한 재귀 방지용으로 sentinel 검사 먼저.
        if name in ("cache", "cache_engine", "local_engine", "fs"):
            raise AttributeError(name)

        if name in PROBLEMS_READ:
            return getattr(self.cache_engine, name)
        return getattr(self.local_engine, name)

    # ----- 동기화 명시 호출 (수동 새로고침용) ------------------------
    def resync_cache(self) -> int:
        """수동 동기화 — 4-D 캐시 무효화 시 사용."""
        return self.cache.incremental_sync()

    def force_full_resync(self) -> int:
        """캐시 비우고 전체 재다운로드."""
        return self.cache.full_sync()

    # ─────────────────────────────────────────────────────────────────
    # Phase 4-B: 개인 데이터 READ (Firestore 직접)
    # ─────────────────────────────────────────────────────────────────
    # 모든 메서드는 LocalDBEngine 의 시그니처/반환값과 100% 호환.
    # 차이점: id 는 int (str(id) 인 doc.id 를 int 로 변환), datetime 은
    # SQLite 풍 'YYYY-MM-DD HH:MM:SS' 문자열로 정규화.

    @staticmethod
    def _fmt_dt(v) -> Optional[str]:
        """Firestore datetime → SQLite TEXT 형식 ('YYYY-MM-DD HH:MM:SS').
        None / 빈값은 그대로 None."""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return v
        try:
            return v.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(v)

    @staticmethod
    def _doc_id_int(doc_id: str) -> int:
        """saved_tests / user_directories / problem_scores 의 doc.id 는
        SQLite 시절의 int auto-increment 를 문자열화한 값. int 로 환원."""
        try:
            return int(doc_id)
        except (TypeError, ValueError):
            return doc_id  # 신규 Firestore auto-id 일 경우 (4-C 이후)

    # ----- 폴더 ----------------------------------------------------------
    def _folder_doc_to_row(self, snap) -> Dict:
        """user_directories doc → SQLite row dict."""
        d = snap.to_dict() or {}
        return {
            "id": self._doc_id_int(snap.id),
            "user_id": d.get("user_id"),
            "name": d.get("name"),
            "parent_id": d.get("parent_id"),
            "is_protected": 1 if d.get("is_protected") else 0,
            "created_at": self._fmt_dt(d.get("created_at")),
        }

    def get_folders(self, user_id: str = "default") -> List[Dict]:
        q = self.fs.collection("user_directories").where(filter=FieldFilter("user_id", "==", user_id))
        rows = [self._folder_doc_to_row(s) for s in q.stream()]
        rows.sort(key=lambda r: (r["id"] if isinstance(r["id"], int) else 0))
        return rows

    def is_folder_protected(self, folder_id: int) -> bool:
        snap = self.fs.collection("user_directories").document(str(folder_id)).get()
        if not snap.exists:
            return False
        return bool((snap.to_dict() or {}).get("is_protected"))

    def get_protected_folder_id(self, name: str, user_id: str):
        q = (self.fs.collection("user_directories")
                .where(filter=FieldFilter("user_id", "==", user_id))
                .where(filter=FieldFilter("name", "==", name))
                .where(filter=FieldFilter("is_protected", "==", True))
                .limit(1))
        for s in q.stream():
            return self._doc_id_int(s.id)
        return None

    def get_folder_test_count(self, folder_id: int) -> int:
        # SQLite 원본도 직접 폴더만 카운트 (children 미사용 버그 그대로) → 동일하게.
        q = self.fs.collection("saved_tests").where(filter=FieldFilter("directory_id", "==", folder_id))
        return sum(1 for _ in q.stream())

    def get_all_subfolder_ids(self, folder_id: int) -> list:
        result = []

        def collect(fid):
            result.append(fid)
            q = self.fs.collection("user_directories").where(filter=FieldFilter("parent_id", "==", fid))
            children = [self._doc_id_int(s.id) for s in q.stream()]
            for cid in children:
                collect(cid)

        collect(folder_id)
        return result

    def is_folder_empty(self, folder_id: int) -> bool:
        all_ids = self.get_all_subfolder_ids(folder_id)
        # Firestore 'in' 은 30개 한도 — 분할
        for chunk in _chunk(all_ids, 30):
            q = self.fs.collection("saved_tests").where(filter=FieldFilter("directory_id", "in", list(chunk)))
            for _ in q.stream():
                return False
        return True

    # ----- 시험지 --------------------------------------------------------
    def _test_doc_to_row(self, snap) -> Dict:
        """saved_tests doc → SQLite row dict.
        SQLite 시절 problem_ids/metadata 는 JSON 문자열이었음 → 캐스팅."""
        import json as _json
        d = snap.to_dict() or {}
        pids = d.get("problem_ids") or []
        if not isinstance(pids, str):
            pids = _json.dumps(pids, ensure_ascii=False)
        meta = d.get("metadata") or {}
        if not isinstance(meta, str):
            meta = _json.dumps(meta, ensure_ascii=False)
        return {
            "id": self._doc_id_int(snap.id),
            "user_id": d.get("user_id"),
            "directory_id": d.get("directory_id"),
            "title": d.get("title"),
            "unit_summary": d.get("unit_summary"),
            "problem_ids": pids,
            "metadata": meta,
            "created_at": self._fmt_dt(d.get("created_at")),
            "updated_at": self._fmt_dt(d.get("updated_at")),
        }

    def get_tests(self, directory_id: int = None, user_id: str = "default") -> List[Dict]:
        q = self.fs.collection("saved_tests").where(filter=FieldFilter("user_id", "==", user_id))
        if directory_id is None:
            # Firestore 에서는 None 비교가 까다로움. SQLite 마이그레이션은
            # NULL → None 으로 보존 → 'directory_id == None' 동등성 작동.
            q = q.where(filter=FieldFilter("directory_id", "==", None))
        else:
            q = q.where(filter=FieldFilter("directory_id", "==", directory_id))
        rows = [self._test_doc_to_row(s) for s in q.stream()]
        # created_at DESC 정렬 (None 은 뒤로)
        rows.sort(key=lambda r: (r["created_at"] is None, r["created_at"] or ""), reverse=True)
        return rows

    def get_test_detail(self, test_id: int, user_id: str = "default") -> Optional[Dict]:
        import json as _json
        snap = self.fs.collection("saved_tests").document(str(test_id)).get()
        if not snap.exists:
            return None
        d = snap.to_dict() or {}
        if d.get("user_id") != user_id:
            return None  # 본인 소유 아님
        test = self._test_doc_to_row(snap)

        # problem_ids 는 dict 안에서 다시 list 로 풀어야 함 (LocalDBEngine 와 동일)
        p_ids = d.get("problem_ids") or []
        if isinstance(p_ids, str):
            try:
                p_ids = _json.loads(p_ids)
            except Exception:
                p_ids = []

        # 캐시에서 problems 적재 (LocalDBEngine 의 SQL 그대로 재사용)
        problems = []
        if p_ids:
            with self.cache.connect() as conn:
                ph = ",".join(["?"] * len(p_ids))
                rows = conn.execute(
                    f"SELECT * FROM problems WHERE id IN ({ph})", p_ids
                ).fetchall()
            order_map = {pid: i for i, pid in enumerate(p_ids)}
            raw = [dict(r) for r in rows]
            raw.sort(key=lambda r: order_map.get(r.get("id"), 9999))
            for r in raw:
                # 캐시 자체 컬럼 updated_at 은 GUI 가 쓰지 않음 → 제거 권장
                r.pop("updated_at", None)
                for field in ("pos_start", "pos_end"):
                    val = r.get(field)
                    if isinstance(val, str):
                        try:
                            r[field] = _json.loads(val)
                        except Exception:
                            r[field] = None
                problems.append(r)
        test["problems"] = problems
        return test

    def get_all_tests_sorted(self, user_id: str = "default") -> List[Dict]:
        # 1) 모든 시험지
        q = self.fs.collection("saved_tests").where(filter=FieldFilter("user_id", "==", user_id))
        tests = [self._test_doc_to_row(s) for s in q.stream()]
        # 2) 폴더 이름 매핑 (LEFT JOIN 대용)
        folders = self.get_folders(user_id)
        name_map = {f["id"]: f["name"] for f in folders}
        # 3) 표 형식 정규화 (SQLite 와 동일 키만)
        out = []
        for t in tests:
            out.append({
                "id": t["id"],
                "title": t["title"],
                "unit_summary": t["unit_summary"],
                "directory_id": t["directory_id"],
                "created_at": t["created_at"],
                "folder_name": name_map.get(t["directory_id"]),
            })
        out.sort(key=lambda r: (r["created_at"] is None, r["created_at"] or ""), reverse=True)
        return out

    def get_user_storage_stats(self, user_id: str = "default") -> Dict:
        total_tests = sum(1 for _ in
            self.fs.collection("saved_tests").where(filter=FieldFilter("user_id", "==", user_id)).stream())
        # SQLite 원본: '폴더 전체 개수 + 루트 시험지 수'.
        all_folders = sum(1 for _ in
            self.fs.collection("user_directories").where(filter=FieldFilter("user_id", "==", user_id)).stream())
        root_tests = sum(1 for _ in
            self.fs.collection("saved_tests")
              .where(filter=FieldFilter("user_id", "==", user_id))
              .where(filter=FieldFilter("directory_id", "==", None)).stream())
        return {"total_tests": total_tests, "root_items": all_folders + root_tests}

    # ----- 점수 ----------------------------------------------------------
    def get_scores_for_test(self, test_id: int) -> Dict[str, int]:
        q = self.fs.collection("problem_scores").where(filter=FieldFilter("test_id", "==", test_id))
        out = {}
        for s in q.stream():
            d = s.to_dict() or {}
            pid = d.get("problem_id")
            if pid is None:
                continue
            out[pid] = 1 if d.get("is_correct") else 0
        return out

    def get_correct_rate(self, problem_id: str):
        q = self.fs.collection("problem_scores").where(filter=FieldFilter("problem_id", "==", problem_id))
        total = 0
        correct = 0
        for s in q.stream():
            total += 1
            if (s.to_dict() or {}).get("is_correct"):
                correct += 1
        if total == 0:
            return None
        return correct / total

    def get_correct_rates_bulk(self, problem_ids: List[str]) -> Dict[str, float]:
        if not problem_ids:
            return {}
        result = {pid: None for pid in problem_ids}
        # Firestore 'in' 30 한도 → 분할 + per-pid 카운트
        # 효율: 각 batch 가 모든 score 를 가져오고 client 측 group by.
        for chunk in _chunk(problem_ids, 30):
            q = self.fs.collection("problem_scores").where(filter=FieldFilter("problem_id", "in", list(chunk)))
            agg: Dict[str, list] = {pid: [0, 0] for pid in chunk}  # [total, correct]
            for s in q.stream():
                d = s.to_dict() or {}
                pid = d.get("problem_id")
                if pid in agg:
                    agg[pid][0] += 1
                    if d.get("is_correct"):
                        agg[pid][1] += 1
            for pid, (total, correct) in agg.items():
                result[pid] = (correct / total) if total else None
        return result

    def get_problem_ids_by_rate(self, min_rate: float, max_rate: float) -> List[str]:
        # 전체 score 스캔 (개인데이터, 총량 ~수천 건 수준)
        agg: Dict[str, list] = {}  # pid -> [total, correct]
        for s in self.fs.collection("problem_scores").stream():
            d = s.to_dict() or {}
            pid = d.get("problem_id")
            if pid is None:
                continue
            slot = agg.setdefault(pid, [0, 0])
            slot[0] += 1
            if d.get("is_correct"):
                slot[1] += 1
        out = []
        for pid, (total, correct) in agg.items():
            if total == 0:
                continue
            rate = correct / total
            if min_rate <= rate <= max_rate:
                out.append(pid)
        return out

    def get_problem_ids_with_scores(self) -> List[str]:
        seen = set()
        for s in self.fs.collection("problem_scores").stream():
            pid = (s.to_dict() or {}).get("problem_id")
            if pid is not None:
                seen.add(pid)
        return list(seen)

    # ----- 선호도 --------------------------------------------------------
    def get_preferences_bulk(self, user_id: str, problem_ids: list) -> dict:
        if not problem_ids:
            return {}
        from backend.firestore_pref_id import pref_doc_id
        # doc.id 직접 lookup — get_all 이용 (배치 read)
        refs = [self.fs.collection("problem_preferences").document(
                    pref_doc_id(user_id, pid)) for pid in problem_ids]
        out = {}
        # firestore_v1 batch get — get_all
        try:
            snaps = list(self.fs.get_all(refs))
        except Exception:
            snaps = [r.get() for r in refs]
        for snap in snaps:
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            pid = d.get("problem_id")
            pref = d.get("preference")
            if pid is not None and pref is not None:
                out[str(pid)] = pref
        return out

    def get_all_preference_user_ids(self) -> list:
        seen = set()
        for s in self.fs.collection("problem_preferences").stream():
            uid = (s.to_dict() or {}).get("user_id")
            if uid:
                seen.add(uid)
        return list(seen)

    def get_problem_ids_by_preference(self, user_ids: list, preferences: list,
                                      candidate_ids: list = None) -> set:
        if not user_ids or not preferences:
            return set()
        pref_set = set(preferences)

        # 모든 대상 사용자의 preferences 적재 (수십~수백 건 가정)
        pref_map: Dict[str, set] = {}
        for chunk in _chunk(list(user_ids), 30):
            q = self.fs.collection("problem_preferences").where(filter=FieldFilter("user_id", "in", list(chunk)))
            for s in q.stream():
                d = s.to_dict() or {}
                pid = d.get("problem_id")
                pref = d.get("preference")
                if pid is None or pref is None:
                    continue
                pref_map.setdefault(str(pid), set()).add(pref)

        if candidate_ids is None:
            return {pid for pid, prefs in pref_map.items() if prefs & pref_set}

        result = set()
        for pid in candidate_ids:
            spid = str(pid)
            if spid in pref_map:
                if pref_map[spid] & pref_set:
                    result.add(spid)
            else:
                if "Soso" in pref_set:
                    result.add(spid)
        return result


def _chunk(seq, n):
    """길이 n 단위로 쪼개기. Firestore 'in' 30 한도 등에 사용."""
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ─────────────────────────────────────────────────────────────────────
# Phase 4-C: 개인 데이터 WRITE (Firestore 직접)
# ─────────────────────────────────────────────────────────────────────
# 정책:
#   - saved_tests / user_directories / problem_scores 의 doc.id 는
#     Phase 3 마이그레이션과 호환되게 'int 시퀀스의 문자열' 형식 유지.
#     → _counters/{collection_name}.next_id 도큐먼트로 트랜잭션 채번.
#   - problem_preferences 는 firestore_pref_id.pref_doc_id(uid, pid) 그대로.
#   - SQLite (problem_bank.db) 에는 더 이상 쓰지 않음. user_id 기준 admin uid 단일화.

def _scan_max_legacy_id(fs_client, collection: str) -> int:
    """카운터 부트스트랩용. Phase 3 마이그레이션 데이터의 max(int(doc.id)) 추정."""
    mx = 0
    for s in fs_client.collection(collection).stream():
        try:
            v = int(s.id)
            if v > mx:
                mx = v
        except (TypeError, ValueError):
            continue
    return mx


def next_int_doc_id(fs_client, collection_name: str) -> int:
    """모듈 레벨 헬퍼 — `_counters/{collection}.next_id` 트랜잭션 카운터로 int doc.id 발급.
    `FirestoreEngine._next_int_id` 와 동일 채널 (인스턴스 없이 호출하고 싶을 때 사용)."""
    from firebase_admin import firestore as _fs2
    counter_ref = fs_client.collection("_counters").document(collection_name)

    @_fs2.transactional
    def _txn(transaction):
        snap = counter_ref.get(transaction=transaction)
        if snap.exists and (snap.to_dict() or {}).get("next_id") is not None:
            cur = (snap.to_dict() or {}).get("next_id")
        else:
            cur = _scan_max_legacy_id(fs_client, collection_name) + 1
        transaction.set(counter_ref, {"next_id": cur + 1})
        return cur

    return _txn(fs_client.transaction())


def ensure_protected_folder(fs_client, user_id: str, name: str = "오답") -> int:
    """사용자에게 보호 폴더가 없으면 생성. 멱등 — 이미 있으면 그 id 반환.
    신규 사용자 발급 (`user_admin.create_user`) 직후 호출."""
    q = (fs_client.collection("user_directories")
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("name", "==", name))
            .where(filter=FieldFilter("is_protected", "==", True))
            .limit(1))
    for s in q.stream():
        try:
            return int(s.id)
        except (TypeError, ValueError):
            break  # int 변환 실패한 잔재는 무시, 새로 발급

    from firebase_admin import firestore as _fs2
    new_id = next_int_doc_id(fs_client, "user_directories")
    fs_client.collection("user_directories").document(str(new_id)).set({
        "user_id": user_id,
        "name": name,
        "parent_id": None,
        "is_protected": True,
        "created_at": _fs2.SERVER_TIMESTAMP,
    })
    return new_id


# 4-C WRITE 메서드들을 FirestoreEngine 에 monkey-patch
def _install_write_methods():
    import json as _json
    from firebase_admin import firestore as _fs

    # ───── 폴더 ─────
    def create_folder(self, name: str, user_id: str = "default",
                      parent_id: int = None) -> Dict:
        try:
            new_id = self._next_int_id("user_directories",
                                       bootstrap_lookup=_scan_max_legacy_id)
            ref = self.fs.collection("user_directories").document(str(new_id))
            ref.set({
                "user_id": user_id,
                "name": name,
                "parent_id": parent_id,
                "is_protected": False,
                "created_at": _fs.SERVER_TIMESTAMP,
            })
            return {"success": True, "id": new_id}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def rename_folder(self, folder_id: int, new_name: str) -> bool:
        try:
            self.fs.collection("user_directories").document(str(folder_id)).update({
                "name": new_name,
            })
            return True
        except Exception:
            return False

    def delete_folder(self, folder_id: int) -> Dict:
        if self.is_folder_protected(folder_id):
            return {"success": False, "message": "보호된 폴더는 삭제할 수 없습니다."}
        if not self.is_folder_empty(folder_id):
            return {"success": False,
                    "message": "폴더(또는 하위 폴더) 안에 시험지가 있어 삭제할 수 없습니다.\n"
                               "시험지를 모두 삭제하거나 이동한 후 다시 시도하세요."}
        all_ids = self.get_all_subfolder_ids(folder_id)
        try:
            batch = self.fs.batch()
            for fid in reversed(all_ids):  # 가장 깊은 것부터
                batch.delete(self.fs.collection("user_directories").document(str(fid)))
            batch.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ───── 시험지 ─────
    def save_test(self, test_data: Dict, user_id: str = "default") -> Dict:
        try:
            dir_id = test_data.get("directory_id")
            is_insert = "id" not in test_data or not test_data.get("id")

            # 한도 검증 (insert 시에만)
            if is_insert:
                stats = self.get_user_storage_stats(user_id)
                if stats["total_tests"] >= 1000:
                    return {"success": False,
                            "message": "총 시험지 저장 한도(1000개)를 초과했습니다."}
                if dir_id is None:
                    root_test_cnt = sum(1 for _ in
                        self.fs.collection("saved_tests")
                          .where(filter=FieldFilter("user_id", "==", user_id))
                          .where(filter=FieldFilter("directory_id", "==", None)).stream())
                    folder_cnt = sum(1 for _ in
                        self.fs.collection("user_directories")
                          .where(filter=FieldFilter("user_id", "==", user_id)).stream())
                    if (root_test_cnt + folder_cnt) >= 30:
                        return {"success": False,
                                "message": "최상위 경로에는 최대 30개 항목만 저장 가능합니다."}
                else:
                    sub_cnt = sum(1 for _ in
                        self.fs.collection("saved_tests")
                          .where(filter=FieldFilter("user_id", "==", user_id))
                          .where(filter=FieldFilter("directory_id", "==", dir_id)).stream())
                    if sub_cnt >= 50:
                        return {"success": False,
                                "message": "폴더 내에는 최대 50개 시험지만 저장 가능합니다."}

            # problem_ids / metadata 정규화 — Firestore 는 native list/map
            p_ids = test_data["problem_ids"]
            if isinstance(p_ids, str):
                try:
                    p_ids = _json.loads(p_ids)
                except Exception:
                    p_ids = []
            meta = test_data.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}

            if is_insert:
                new_id = self._next_int_id("saved_tests",
                                           bootstrap_lookup=_scan_max_legacy_id)
                self.fs.collection("saved_tests").document(str(new_id)).set({
                    "user_id": user_id,
                    "directory_id": dir_id,
                    "title": test_data["title"],
                    "unit_summary": test_data.get("unit_summary", ""),
                    "problem_ids": p_ids,
                    "metadata": meta,
                    "created_at": _fs.SERVER_TIMESTAMP,
                    "updated_at": _fs.SERVER_TIMESTAMP,
                })
                return {"success": True, "id": new_id}
            else:
                tid = test_data["id"]
                self.fs.collection("saved_tests").document(str(tid)).update({
                    "title": test_data["title"],
                    "unit_summary": test_data.get("unit_summary", ""),
                    "directory_id": dir_id,
                    "problem_ids": p_ids,
                    "metadata": meta,
                    "updated_at": _fs.SERVER_TIMESTAMP,
                })
                return {"success": True, "id": tid}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e)}

    def delete_test(self, test_id: int) -> bool:
        try:
            # 시험지 삭제 + 연관 problem_scores 도 같이 정리 (SQLite FK 없음 → 명시적)
            tid_int = int(test_id) if not isinstance(test_id, int) else test_id
            batch = self.fs.batch()
            batch.delete(self.fs.collection("saved_tests").document(str(tid_int)))
            # 연관 점수
            for s in (self.fs.collection("problem_scores")
                        .where(filter=FieldFilter("test_id", "==", tid_int)).stream()):
                batch.delete(s.reference)
            batch.commit()
            return True
        except Exception as e:
            print(f"[FirestoreEngine] delete_test 오류: {e}")
            return False

    # ───── 선호도 ─────
    def set_preference(self, user_id: str, problem_id, preference) -> bool:
        from backend.firestore_pref_id import pref_doc_id
        ref = self.fs.collection("problem_preferences").document(
            pref_doc_id(user_id, problem_id))
        try:
            if preference is None:
                ref.delete()
            else:
                ref.set({
                    "user_id": user_id,
                    "problem_id": str(problem_id),
                    "preference": preference,
                    "updated_at": _fs.SERVER_TIMESTAMP,
                })
            return True
        except Exception as e:
            print(f"[FirestoreEngine] set_preference 오류: {e}")
            return False

    # ───── 채점 ─────
    def save_scores(self, test_id: int, scores: Dict[str, int]) -> bool:
        try:
            tid_int = int(test_id) if not isinstance(test_id, int) else test_id
            # 기존 점수 삭제
            existing = list(self.fs.collection("problem_scores")
                              .where(filter=FieldFilter("test_id", "==", tid_int)).stream())
            # Firestore batch 한도 = 500 ops → 분할
            BATCH_LIMIT = 400
            ops = []
            for s in existing:
                ops.append(("delete", s.reference, None))
            for pid, val in scores.items():
                # 점수 doc.id 는 auto-id (외부 참조 없음)
                ref = self.fs.collection("problem_scores").document()
                ops.append(("set", ref, {
                    "test_id": tid_int,
                    "problem_id": str(pid),
                    "is_correct": bool(int(val)),
                    "scored_at": _fs.SERVER_TIMESTAMP,
                }))
            for chunk in _chunk(ops, BATCH_LIMIT):
                batch = self.fs.batch()
                for op, ref, data in chunk:
                    if op == "delete":
                        batch.delete(ref)
                    else:
                        batch.set(ref, data)
                batch.commit()
            return True
        except Exception as e:
            print(f"[FirestoreEngine] save_scores 오류: {e}")
            return False

    # ───── int id 채번 (캐시: bootstrap 한 번만 스캔) ─────
    def _next_int_id(self, collection_name: str, bootstrap_lookup=None) -> int:
        from firebase_admin import firestore as _fs2
        counter_ref = self.fs.collection("_counters").document(collection_name)

        @_fs2.transactional
        def _txn(transaction):
            snap = counter_ref.get(transaction=transaction)
            if snap.exists:
                cur = (snap.to_dict() or {}).get("next_id")
                if cur is None:
                    cur = (bootstrap_lookup(self.fs, collection_name)
                           if bootstrap_lookup else 0) + 1
            else:
                base = (bootstrap_lookup(self.fs, collection_name)
                        if bootstrap_lookup else 0)
                cur = base + 1
            transaction.set(counter_ref, {"next_id": cur + 1})
            return cur

        return _txn(self.fs.transaction())

    def ensure_protected_folder_method(self, user_id: str, name: str = "오답") -> int:
        """엔진 메서드 — 모듈 레벨 `ensure_protected_folder` 위임. 멱등."""
        return ensure_protected_folder(self.fs, user_id, name)

    # 클래스 본체에 부착
    FirestoreEngine.create_folder = create_folder
    FirestoreEngine.rename_folder = rename_folder
    FirestoreEngine.delete_folder = delete_folder
    FirestoreEngine.save_test = save_test
    FirestoreEngine.delete_test = delete_test
    FirestoreEngine.set_preference = set_preference
    FirestoreEngine.save_scores = save_scores
    FirestoreEngine._next_int_id = _next_int_id
    FirestoreEngine.ensure_protected_folder = ensure_protected_folder_method


_install_write_methods()


# ─────────────────────────────────────────────────────────────────────
# Phase 4-D: problems WRITE (admin only) + 캐시 무효화
# ─────────────────────────────────────────────────────────────────────
# 정책:
#   - 단일 진실의 원천 = Firestore. 먼저 Firestore 에 적용 후 로컬 캐시 갱신.
#   - 캐시(write-through): cache_engine(LocalDBEngine on cache.sqlite) 의 동일
#     메서드를 그대로 호출 → SQL 일관성 유지. 추가로 watermark 조정용
#     updated_at(epoch) 도 같이 갱신해서 다음 incremental_sync 가 정상 동작.
#   - Firestore batch 한도 = 500 ops → 분할 helper 사용.
#   - admin only — Security Rules 가 보장 (앞단은 메뉴 숨김으로 차단).

_FS_BATCH_LIMIT = 400  # 안전 마진


def _install_problems_write_methods():
    import time as _time
    from firebase_admin import firestore as _fs

    def _bump_cache_updated_at(self, problem_ids):
        """캐시 측 updated_at(epoch float) 을 현재 시각으로 갱신.
        다음 incremental_sync 가 watermark 기준으로 동일 변경을 다시 받지
        않도록 하기 위함."""
        ids = [pid for pid in problem_ids if pid is not None]
        if not ids:
            return
        now = _time.time()
        with self.cache.connect() as conn:
            for chunk in _chunk(ids, 500):
                ph = ",".join(["?"] * len(chunk))
                conn.execute(
                    f"UPDATE problems SET updated_at=? WHERE id IN ({ph})",
                    [now] + list(chunk),
                )
            conn.commit()

    # ───── update_problem_meta ─────
    def update_problem_meta(self, problem_id, field, value, unit_name=None):
        allowed = {"difficulty", "unit_code"}
        if field not in allowed:
            raise ValueError(f"수정 불가 필드: {field}")
        ref = self.fs.collection("problems").document(str(problem_id))
        try:
            if field == "unit_code":
                ref.update({
                    "unit_code": value,
                    "middle_unit": unit_name or value,
                    "unit_code_locked": 1,
                    "updated_at": _fs.SERVER_TIMESTAMP,
                })
            else:  # difficulty
                ref.update({
                    "difficulty": value,
                    "difficulty_locked": 1,
                    "updated_at": _fs.SERVER_TIMESTAMP,
                })
        except Exception as e:
            print(f"[FirestoreEngine] update_problem_meta 오류: {e}")
            return
        # 캐시 동기화 — LocalDBEngine 의 SQL 그대로 재사용
        try:
            self.cache_engine.update_problem_meta(str(problem_id), field, value, unit_name)
            self._bump_cache_updated_at([str(problem_id)])
        except Exception as e:
            print(f"[FirestoreEngine] update_problem_meta cache sync 오류: {e}")

    # ───── set_exclusion_status ─────
    def set_exclusion_status(self, problem_ids, excluded):
        if not problem_ids:
            return 0
        # AUDIT 로그 — LocalDBEngine 와 동일 형식 유지
        try:
            import traceback as _tb, datetime as _dt, os as _os
            stack = _tb.extract_stack()
            callers = []
            for fr in stack[-4:-1]:
                callers.append(f"{_os.path.basename(fr.filename)}:{fr.lineno} {fr.name}")
            ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            action = "EXCLUDE" if excluded else "RESTORE"
            sample = list(problem_ids[:3])
            line = (f"[EXCL_AUDIT {ts}] {action} count={len(problem_ids)} "
                    f"sample={sample} callers={' <- '.join(callers)} via=Firestore")
            print(line)
            try:
                log_path = _os.path.join(_os.path.dirname(self.db_path), "exclusion_audit.log")
                with open(log_path, "a", encoding="utf-8") as _f:
                    _f.write(line + "\n")
            except Exception:
                pass
        except Exception:
            pass

        val = 1 if excluded else 0
        ids = [str(pid) for pid in problem_ids]
        # Firestore batch update — 분할
        try:
            for chunk in _chunk(ids, _FS_BATCH_LIMIT):
                batch = self.fs.batch()
                for pid in chunk:
                    batch.update(
                        self.fs.collection("problems").document(pid),
                        {"is_excluded": val, "updated_at": _fs.SERVER_TIMESTAMP},
                    )
                batch.commit()
        except Exception as e:
            print(f"[FirestoreEngine] set_exclusion_status 오류: {e}")
            return 0
        # 캐시 동기화 — LocalDBEngine 의 AUDIT 중복 로그 차단
        import os as _os2
        _prev = _os2.environ.get("EXCL_AUDIT_SUPPRESS")
        _os2.environ["EXCL_AUDIT_SUPPRESS"] = "1"
        try:
            self.cache_engine.set_exclusion_status(ids, excluded)
            self._bump_cache_updated_at(ids)
        except Exception as e:
            print(f"[FirestoreEngine] set_exclusion_status cache sync 오류: {e}")
        finally:
            if _prev is None:
                _os2.environ.pop("EXCL_AUDIT_SUPPRESS", None)
            else:
                _os2.environ["EXCL_AUDIT_SUPPRESS"] = _prev
        return len(ids)

    # ───── delete_problems ─────
    def delete_problems(self, problem_ids):
        if not problem_ids:
            return 0
        ids = [str(pid) for pid in problem_ids]
        deleted = 0
        try:
            for chunk in _chunk(ids, _FS_BATCH_LIMIT):
                batch = self.fs.batch()
                for pid in chunk:
                    batch.delete(self.fs.collection("problems").document(pid))
                batch.commit()
                deleted += len(chunk)
        except Exception as e:
            print(f"[FirestoreEngine] delete_problems 오류: {e}")
            return deleted
        # 캐시 즉시 삭제 (incremental_sync 는 deleted 도큐먼트를 추적 못 함)
        try:
            self.cache.delete_many(ids)
        except Exception as e:
            print(f"[FirestoreEngine] delete_problems cache 정리 오류: {e}")
        return deleted

    # ───── delete_exam (메타 일치) ─────
    def delete_exam(self, meta):
        check_fields = ["school", "year", "grade", "semester",
                         "exam_type", "subject"]
        # 캐시에서 후보 id 조회 — Firestore 에서 동적 AND 쿼리는 인덱스 부담
        with self.cache.connect() as conn:
            conds, params = [], []
            for f in check_fields:
                v = meta.get(f, "")
                if v:
                    conds.append(f"{f}=?")
                    params.append(v)
            if not conds:
                return 0
            rows = conn.execute(
                f"SELECT id FROM problems WHERE {' AND '.join(conds)}", params
            ).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return 0
        return self.delete_problems(ids)

    # ───── delete_exams_by_filenames ─────
    def delete_exams_by_filenames(self, file_names):
        if not file_names:
            return 0
        # 캐시에서 file_name IN ... 으로 id 조회
        with self.cache.connect() as conn:
            ph = ",".join(["?"] * len(file_names))
            rows = conn.execute(
                f"SELECT id FROM problems WHERE file_name IN ({ph})",
                list(file_names),
            ).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return 0
        return self.delete_problems(ids)

    # ───── bulk_update_field — 일괄 안전 수정 (admin 복구용) ─────
    # 2026-05-23 추가. 직접 batch.update 로 인한 캐시 stale 사고 재발 방지용.
    # 사용 예 (mapped_unit_code 기준 복구):
    #   updates = [{"id": doc_id, "unit_code": new_uc} for ...]
    #   engine.bulk_update_field(updates)
    def bulk_update_field(self, updates):
        """일괄 필드 갱신 (Firestore batch + write-through 캐시).

        updates: [{"id": str, "필드명": 값, ...}, ...]
                 'id' 필수, 그 외는 갱신할 필드. allowed = {unit_code, mapped_unit_code,
                 difficulty, middle_unit, large_unit, subject, year, grade, semester,
                 exam_type, curriculum, school, problem_type, tags, is_excluded,
                 difficulty_locked, unit_code_locked}.
        반환: 성공한 문서 수.
        ★ 안전 패턴: updated_at=SERVER_TIMESTAMP 자동 추가 + 캐시 즉시 갱신.
        """
        if not updates:
            return 0
        ALLOWED = {
            "unit_code", "mapped_unit_code", "difficulty", "middle_unit",
            "large_unit", "subject", "year", "grade", "semester", "exam_type",
            "curriculum", "school", "problem_type", "tags", "is_excluded",
            "difficulty_locked", "unit_code_locked",
        }
        # 1) Firestore batch update
        ok = 0
        try:
            for chunk in _chunk(updates, _FS_BATCH_LIMIT):
                batch = self.fs.batch()
                for u in chunk:
                    pid = u.get("id")
                    if not pid:
                        continue
                    payload = {k: v for k, v in u.items() if k != "id" and k in ALLOWED}
                    if not payload:
                        continue
                    payload["updated_at"] = _fs.SERVER_TIMESTAMP
                    batch.update(self.fs.collection("problems").document(str(pid)), payload)
                batch.commit()
                ok += len(chunk)
        except Exception as e:
            print(f"[FirestoreEngine] bulk_update_field Firestore 오류: {e}")
            return ok
        # 2) 캐시 동기화 — 같은 필드를 SQLite 에도 반영 + updated_at 갱신
        import time as _time
        try:
            with self.cache.connect() as conn:
                for u in updates:
                    pid = u.get("id")
                    if not pid:
                        continue
                    payload = {k: v for k, v in u.items() if k != "id" and k in ALLOWED}
                    if not payload:
                        continue
                    set_clause = ", ".join(f"{k}=?" for k in payload) + ", updated_at=?"
                    params = list(payload.values()) + [_time.time(), str(pid)]
                    conn.execute(f"UPDATE problems SET {set_clause} WHERE id=?", params)
                conn.commit()
        except Exception as e:
            print(f"[FirestoreEngine] bulk_update_field 캐시 동기화 오류: {e}")
        return ok

    # 클래스 본체에 부착
    FirestoreEngine._bump_cache_updated_at = _bump_cache_updated_at
    FirestoreEngine.update_problem_meta = update_problem_meta
    FirestoreEngine.set_exclusion_status = set_exclusion_status
    FirestoreEngine.delete_problems = delete_problems
    FirestoreEngine.delete_exam = delete_exam
    FirestoreEngine.delete_exams_by_filenames = delete_exams_by_filenames
    FirestoreEngine.bulk_update_field = bulk_update_field


_install_problems_write_methods()


# ─────────────────────────────────────────────────────────────────────
# Phase 5: 인덱서 직접 쓰기 (admin only) — Firestore + write-through 캐시
# ─────────────────────────────────────────────────────────────────────
# 정책:
#   - hwp_metadata_parser_v2._post_process_file 의 sqlite3 직접 INSERT 와
#     naive _sync_to_firebase 를 엔진 라우팅으로 일원화.
#   - 단일 진실의 원천 = Firestore. 먼저 batch upsert → 캐시 즉시 동기화.
#   - 잠금/제외 상태 보존: 기존 도큐먼트의 difficulty_locked / unit_code_locked
#     이 1 이면 인덱싱 결과의 difficulty / unit_code / middle_unit 무시.
#     is_excluded 는 항상 기존값 유지.
#   - admin only — Firestore Security Rules 가 보장.

def _install_indexer_write_methods():
    import time as _time
    import json as _json
    from firebase_admin import firestore as _fs

    def ingest_indexed_problems(self, items):
        """인덱서 결과를 Firestore + 로컬 캐시에 upsert (batch).

        items: [asdict(ProblemRecord)] 형식. 'problem_id' → doc id.
        반환: Firestore 에 기록된 문항 수.
        """
        if not items:
            return 0

        # 1) 잠금/제외 상태 보존 — 캐시 SQLite 에서 일괄 조회 (Firestore READ 0)
        #    캐시는 incremental_sync 로 Firestore 와 동기화되므로 lock 진실의 원천.
        pids = []
        for item in items:
            pid = item.get("problem_id") or item.get("id")
            if pid:
                pids.append(str(pid))
        existing_locks = {}  # pid -> (d_locked, u_locked, excl, diff, uc, mu)
        if pids:
            try:
                with self.cache.connect() as conn:
                    for chunk in _chunk(pids, 500):
                        qmark = ",".join(["?"] * len(chunk))
                        rows = conn.execute(
                            f"SELECT id, difficulty_locked, unit_code_locked, "
                            f"is_excluded, difficulty, unit_code, middle_unit "
                            f"FROM problems WHERE id IN ({qmark})",
                            chunk,
                        ).fetchall()
                        for r in rows:
                            existing_locks[r[0]] = (
                                int(r[1] or 0), int(r[2] or 0), int(r[3] or 0),
                                r[4], r[5], r[6],
                            )
            except Exception as e:
                print(f"[FirestoreEngine] ingest 캐시 lock 조회 오류: {e}")

        prepared = []  # [(pid, fs_payload, cache_payload)]
        for item in items:
            pid = item.get("problem_id") or item.get("id")
            if not pid:
                continue
            pid = str(pid)

            pnum = item.get("endnote_index")
            src = item.get("source", "")
            if src == "MOCK_EXAM" and pnum is not None:
                exam_num = pnum if pnum <= 22 else (pnum - 22 - 1) % 8 + 23
            else:
                exam_num = None

            ex = existing_locks.get(pid)
            if ex is not None:
                d_locked, u_locked, excl, old_diff, old_uc, old_mu = ex
                final_diff = old_diff if d_locked else item.get("difficulty")
                final_uc   = old_uc   if u_locked else item.get("unit_code")
                final_mu   = old_mu   if u_locked else item.get("middle_unit")
            else:
                d_locked = 0
                u_locked = 0
                excl = 0
                final_diff = item.get("difficulty")
                final_uc   = item.get("unit_code")
                final_mu   = item.get("middle_unit")

            fs_payload = {
                "id": pid,
                "file_name": item.get("file_name"),
                "endnote_index": item.get("endnote_index"),
                "school": item.get("school"),
                "year": item.get("year"),
                "grade": item.get("grade"),
                "semester": item.get("semester"),
                "exam_type": item.get("exam_type"),
                "subject": item.get("subject"),
                "curriculum": item.get("curriculum"),
                "unit_code": final_uc,
                "mapped_unit_code": item.get("mapped_unit_code"),
                "difficulty": final_diff,
                "problem_type": item.get("problem_type"),
                "pos_start": item.get("pos_start", []),
                "pos_end": item.get("pos_end", []),
                "large_unit": item.get("large_unit"),
                "middle_unit": final_mu,
                "file_hash": item.get("file_hash"),
                "search_text": item.get("search_text"),
                "is_excluded": excl,
                "source": src,
                "problem_number": pnum,
                "exam_number": exam_num,
                "tags": item.get("tags", ""),
                "difficulty_locked": d_locked,
                "unit_code_locked": u_locked,
                "indexed_at": item.get("indexed_at"),
                "updated_at": _fs.SERVER_TIMESTAMP,
            }

            # 캐시 페이로드 — pos_start/pos_end JSON string, updated_at epoch
            cache_payload = dict(fs_payload)
            cache_payload["pos_start"] = _json.dumps(item.get("pos_start", []))
            cache_payload["pos_end"] = _json.dumps(item.get("pos_end", []))
            cache_payload["updated_at"] = _time.time()

            prepared.append((pid, fs_payload, cache_payload))

        if not prepared:
            return 0

        # 2) Firestore batch upsert (set, full doc 작성 → merge=False)
        count = 0
        try:
            for chunk in _chunk(prepared, _FS_BATCH_LIMIT):
                batch = self.fs.batch()
                for pid, fs_payload, _cache_payload in chunk:
                    batch.set(self.fs.collection("problems").document(pid), fs_payload)
                batch.commit()
                count += len(chunk)
        except Exception as e:
            print(f"[FirestoreEngine] ingest_indexed_problems Firestore 오류: {e}")
            return count

        # 3) Write-through 캐시 — 부분 실패는 다음 incremental_sync 가 복구
        for pid, _fs_payload, cache_payload in prepared:
            try:
                self.cache.upsert_one(cache_payload)
            except Exception as e:
                print(f"[FirestoreEngine] ingest 캐시 동기화 오류 ({pid}): {e}")

        return count

    FirestoreEngine.ingest_indexed_problems = ingest_indexed_problems


_install_indexer_write_methods()
