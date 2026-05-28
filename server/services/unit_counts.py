"""unit_code 별 문제 수 집계 — 로컬 main_gui._compute_unit_counts 의 서버 포팅.

GROUP BY 한 방으로 끝낸다. Firestore 엔진은 캐시 SQLite(.cache.cache_path) 를
경유하므로 SQLite 가 항상 사용 가능하다.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Optional

from server.services.engine import get_engine


def _engine_db_path() -> Optional[str]:
    eng = get_engine()
    cache = getattr(eng, "cache", None)
    if cache is not None and getattr(cache, "cache_path", None):
        return str(cache.cache_path)
    db_path = getattr(eng, "db_path", None)
    return str(db_path) if db_path else None


def compute_unit_counts(filters: Optional[dict] = None) -> Dict[str, int]:
    """주어진 필터 하에서 unit_code 별 COUNT(*) 를 단일 GROUP BY 로 반환.

    빈 unit_code 는 키 ""로 합산된다.
    """
    db_path = _engine_db_path()
    if not db_path:
        return {}

    f = dict(filters or {})
    f.pop("_rate_ids", None)
    f.pop("unit_code", None)
    brand_ids = f.pop("_brand_ids", None)

    conds, params = [], []
    for k, v in f.items():
        if v is None or v == "":
            continue
        if isinstance(v, list):
            if not v:
                continue
            conds.append(f"{k} IN ({','.join(['?'] * len(v))})")
            params.extend(v)
        elif isinstance(v, dict):
            op_handlers = {
                "eq": "=", "ne": "!=", "gt": ">", "gte": ">=",
                "lt": "<", "lte": "<=", "like": "LIKE",
            }
            for op, val in v.items():
                if op in op_handlers:
                    conds.append(f"{k} {op_handlers[op]} ?")
                    params.append(val)
                elif op == "in":
                    if not val:
                        continue
                    conds.append(f"{k} IN ({','.join(['?'] * len(val))})")
                    params.extend(val)
                elif op == "not_in":
                    if not val:
                        continue
                    conds.append(f"{k} NOT IN ({','.join(['?'] * len(val))})")
                    params.extend(val)
        else:
            conds.append(f"{k} = ?")
            params.append(v)

    if brand_ids is not None:
        if not brand_ids:
            return {}
        conds.append(f"id IN ({','.join(['?'] * len(brand_ids))})")
        params.extend(brand_ids)

    conds.append("is_excluded = 0")

    sql = (
        "SELECT unit_code, COUNT(*) FROM problems WHERE "
        + " AND ".join(conds)
        + " GROUP BY unit_code"
    )
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            return {row[0] or "": row[1] for row in cur.fetchall()}
        finally:
            conn.close()
    except Exception as e:
        print(f"[unit_counts] 집계 실패: {e}")
        return {}
