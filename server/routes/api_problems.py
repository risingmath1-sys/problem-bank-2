"""문제 검색 API — 필터 → JSON."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from server.auth_dep import require_user, SessionUser
from server.services.engine import get_engine

router = APIRouter(prefix="/api/problems", tags=["problems"])

# 응답 시 클라이언트에 노출할 필드만 추림 (메타 위주, 본문/좌표는 제외)
_PUBLIC_FIELDS = (
    "id", "source", "school", "year", "grade", "semester",
    "exam_type", "subject", "unit_code", "mapped_unit_code",
    "large_unit", "middle_unit", "difficulty", "problem_type",
    "endnote_index", "file_name", "is_excluded",
)


def _slim(row: dict) -> dict:
    return {k: row.get(k) for k in _PUBLIC_FIELDS}


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@router.get("")
def list_problems(
    source: Optional[str] = Query(None, description="단일 source (예: NAESIN_A)"),
    unit_codes: Optional[str] = Query(None, description="중단원 코드 CSV (예: A1,A2)"),
    difficulties: Optional[str] = Query(None, description="난이도 코드 CSV (예: A,B)"),
    problem_type: Optional[str] = Query(None),
    school: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    _: SessionUser = Depends(require_user),
):
    """필터 → 문제 목록 (검색 정렬: year DESC, school, grade, id)."""
    engine = get_engine()
    filters: dict = {}
    if source:
        filters["source"] = source
    if school:
        filters["school"] = school  # search_problems가 LIKE 처리
    if year:
        filters["year"] = year
    if problem_type:
        filters["problem_type"] = problem_type
    # 단일값/리스트 모두 처리: 리스트면 search_problems 가 안 잡으니 query_counts 스타일로 직접 처리 X
    # MVP: 리스트는 첫 항목만 사용. 다중 선택은 클라이언트가 여러 번 쿼리하거나, 후속 패치에서 별도 엔드포인트.
    unit_list = _split_csv(unit_codes)
    diff_list = _split_csv(difficulties)
    if len(unit_list) == 1:
        filters["unit_code"] = unit_list[0]
    if len(diff_list) == 1:
        filters["difficulty"] = diff_list[0]

    rows = engine.search_problems(filters, limit=limit)

    # 다중 선택 클라이언트-사이드 필터링 (MVP 단순 구현)
    if len(unit_list) > 1:
        s = set(unit_list)
        rows = [r for r in rows if r.get("unit_code") in s]
    if len(diff_list) > 1:
        s = set(diff_list)
        rows = [r for r in rows if r.get("difficulty") in s]

    return {
        "total": len(rows),
        "problems": [_slim(r) for r in rows],
    }


@router.get("/count")
def count_problems(
    source: Optional[str] = Query(None),
    unit_codes: Optional[str] = Query(None),
    difficulties: Optional[str] = Query(None),
    problem_type: Optional[str] = Query(None),
    school: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    _: SessionUser = Depends(require_user),
):
    """필터 매칭 문제 수만 반환 (UI 미리보기용)."""
    engine = get_engine()
    filters: dict = {}
    if source:
        filters["source"] = source
    if year:
        filters["year"] = year
    if problem_type:
        filters["problem_type"] = problem_type
    if school:
        filters["school"] = {"like": f"%{school}%"}

    unit_list = _split_csv(unit_codes)
    diff_list = _split_csv(difficulties)
    if unit_list:
        filters["unit_code"] = {"in": unit_list}
    if diff_list:
        filters["difficulty"] = {"in": diff_list}

    return {"count": engine.query_counts(filters)}
