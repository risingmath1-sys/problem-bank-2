"""관리자 전용 API — 캐시 sync 수동 트리거 등."""
from fastapi import APIRouter, Depends, HTTPException

from server.auth_dep import require_admin, SessionUser
from server.services.engine import get_engine

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/cache/sync/incremental")
def sync_incremental(_: SessionUser = Depends(require_admin)):
    """캐시 incremental_sync 즉시 트리거.

    watermark(max updated_at) 이후 변경분만 받음.
    인덱싱이 다른 PC 에서 일어났거나, Firestore 직접 수정 후
    (updated_at 갱신된 경우) 즉시 반영하고 싶을 때 호출.
    """
    engine = get_engine()
    cache = getattr(engine, "cache", None)
    if cache is None:
        raise HTTPException(status_code=503, detail="캐시 모드가 아닙니다 (LocalDBEngine)")
    try:
        n = cache.incremental_sync()
        return {"ok": True, "synced": n}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sync 실패: {e}")


@router.post("/cache/sync/full")
def sync_full(_: SessionUser = Depends(require_admin)):
    """캐시 full_sync — 전체 다운로드 (캐시 초기화 후 적재).

    incremental 이 못 잡는 변경(예: updated_at 안 박힌 직접 batch update)이 있을 때.
    비용: 전체 약 50,000건 → 약 50초. 평소엔 incremental 만으로 충분.
    """
    engine = get_engine()
    cache = getattr(engine, "cache", None)
    if cache is None:
        raise HTTPException(status_code=503, detail="캐시 모드가 아닙니다")
    try:
        n = cache.full_sync()
        return {"ok": True, "synced": n}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"full_sync 실패: {e}")


@router.get("/cache/status")
def cache_status(_: SessionUser = Depends(require_admin)):
    """캐시 현황 — 건수, watermark, 마지막 sync 시각."""
    engine = get_engine()
    cache = getattr(engine, "cache", None)
    if cache is None:
        return {"mode": "no-cache"}
    try:
        return {
            "mode": "firestore+cache",
            "count": cache.count(),
            "max_updated_at": cache.max_updated_at(),
            "cache_path": cache.cache_path,
            "last_full_sync": cache.get_meta("last_full_sync"),
            "last_incremental_sync": cache.get_meta("last_incremental_sync"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
