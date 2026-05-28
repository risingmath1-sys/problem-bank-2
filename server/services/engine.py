"""데이터 엔진 싱글톤. 서버 라이프타임 동안 1개 인스턴스 재사용."""
from pathlib import Path
from typing import Optional

from backend.data_engine import make_engine

_engine = None


def get_engine():
    """FirestoreEngine(또는 LocalDBEngine) 싱글톤 반환."""
    global _engine
    if _engine is None:
        # 기존 backend가 사용하던 SQLite 캐시(personal data fallback) 위치
        local_db_path = str(Path(__file__).resolve().parent.parent.parent / "problem_bank.db")
        _engine = make_engine(local_db_path=local_db_path, verbose=False)
    return _engine
