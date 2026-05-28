"""메타데이터 API — 통계, 단원 트리, 학교, 년도."""
import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, Query

from server.auth_dep import require_user, SessionUser
from server.services.engine import get_engine

router = APIRouter(prefix="/api/meta", tags=["meta"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UNIT_HIERARCHY_PATH = PROJECT_ROOT / "unit_hierarchy.json"
CURRICULUM_CONFIG_PATH = PROJECT_ROOT / "backend" / "curriculum_config.json"

SOURCES = ["NAESIN_A", "NAESIN_N", "SUNEUNG_SPECIAL", "SUNEUNG_COMPLETE", "MOCK_EXAM"]


@router.get("/stats")
def stats(_: SessionUser = Depends(require_user)):
    """홈에 표시할 통계 — 총 문제 수 + 소스별 카운트."""
    engine = get_engine()
    by_source = {src: engine.query_counts({"source": src}) for src in SOURCES}
    total = sum(by_source.values())
    return {"total": total, "by_source": by_source}


@router.get("/units")
def units(_: SessionUser = Depends(require_user)):
    """단원 트리(unit_hierarchy.json) 통째로."""
    with UNIT_HIERARCHY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@router.get("/curriculum")
def curriculum(_: SessionUser = Depends(require_user)):
    """과목/단원 매핑(curriculum_config.json) 통째로."""
    with CURRICULUM_CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@router.get("/schools")
def schools(
    keyword: str = Query("", min_length=0, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    _: SessionUser = Depends(require_user),
) -> List[str]:
    """학교명 검색 (LIKE %keyword%)."""
    engine = get_engine()
    return engine.search_schools(keyword, limit=limit)


@router.get("/years")
def years(_: SessionUser = Depends(require_user)) -> List[str]:
    """DB에 존재하는 distinct 년도 (내림차순)."""
    engine = get_engine()
    return engine.get_unique_years()
