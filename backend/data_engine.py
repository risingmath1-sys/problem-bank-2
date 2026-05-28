# -*- coding: utf-8 -*-
"""
Phase 4-A: 데이터 엔진 팩토리 + 추상 인터페이스 가이드.

목적:
  GUI 코드 (main_gui.py 등) 가 SQLite/Firestore 어느 쪽이든 동일한 메서드
  시그니처로 호출할 수 있도록 단일 진입점 제공.

토글:
  환경변수 DATA_ENGINE 으로 즉시 전환:
    DATA_ENGINE=sqlite     → LocalDBEngine (default, 2026-05-26 부터)
    DATA_ENGINE=firestore  → FirestoreEngine (legacy 캐시+Firestore 하이브리드 — rollback 용)

  ★ 2026-05-26 정책 변경:
    - SQLite-only 가 정본 (problem_bank.db)
    - Firestore 코드는 dead code 로 보존 (롤백 가능)
    - Firebase Auth (로그인) 는 backend/auth.py 에서 그대로 사용

사용:
  from backend.data_engine import make_engine
  engine = make_engine(local_db_path="problem_bank.db")
  rows = engine.get_problems_by_files([...])    # 어느 엔진이든 동일 호출

설계 원본:
  로그인시스템설계도.md §5 Phase 4
  로그인시스템_작업현황.md Phase 4
"""
import os
from typing import Optional


def get_engine_mode() -> str:
    """현재 토글 값. 'sqlite' (기본, 2026-05-26~) | 'firestore' (legacy rollback)."""
    return (os.environ.get("DATA_ENGINE") or "sqlite").strip().lower()


def make_engine(local_db_path: str, firestore_client=None,
                cache_path: Optional[str] = None, verbose: bool = True):
    """
    엔진 팩토리.

    Args:
        local_db_path: 기존 SQLite 파일 경로 (problem_bank.db).
                       sqlite 모드에서는 이걸 그대로 LocalDBEngine 에 넘김.
                       firestore 모드에서도 4-A 단계에서는 personal data
                       fallback 용으로 필요.
        firestore_client: 선택. 미지정 시 firestore 모드일 때 자동 생성.
                          (firebase_admin 이 이미 초기화돼 있다고 가정.)
        cache_path: 선택. problems 캐시 SQLite 위치. 미지정 시 default.
        verbose: 캐시/엔진 로그 출력 여부.
    """
    mode = get_engine_mode()
    if mode == "firestore":
        from backend.firestore_engine import FirestoreEngine
        return FirestoreEngine(
            local_db_path=local_db_path,
            firestore_client=firestore_client,
            cache_path=cache_path,
            verbose=verbose,
        )

    if mode != "sqlite":
        print(f"[data_engine] 알 수 없는 DATA_ENGINE='{mode}' → sqlite 로 폴백 (2026-05-26 정책)")

    from backend.db_engine import LocalDBEngine
    return LocalDBEngine(local_db_path)
