# -*- coding: utf-8 -*-
"""
Phase 3/4: problem_preferences 컬렉션 doc.id 생성 규칙.

Firestore doc.id 제한:
  - '/' 금지, 빈문자열 금지, '__xxx__' 패턴 금지, 길이 1~1500.
  - problem_id 는 한글/특수문자 포함 가능 → URL-safe base64 로 안전화.

규약 (migrate_user_data_to_firestore.py 와 일치):
  doc.id = "{uid}_{base64_problem_id}"
"""
import base64


def safe_problem_id(problem_id: str) -> str:
    """problem_id → URL-safe base64 (= 패딩 제거)."""
    return base64.urlsafe_b64encode(str(problem_id).encode("utf-8")).decode("ascii").rstrip("=")


def pref_doc_id(user_id: str, problem_id) -> str:
    """problem_preferences/{uid}_{base64_pid}."""
    return f"{user_id}_{safe_problem_id(problem_id)}"
