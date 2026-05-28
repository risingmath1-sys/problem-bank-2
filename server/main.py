"""FastAPI 진입점.

실행:
  uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload   (개발)
  uvicorn server.main:app --host 0.0.0.0 --port 8000 --workers 1  (운영)

📌 운영 역할 분리 정책 (2026-05-23 확정):
  - 문제 출제 = SC (이 서버) — 출제 관련 코드는 server/ 위주로 손볼 것
  - 문제 등록(인덱싱) = 로컬 (backend/main_gui.py + HWP COM)
  - server/routes/api_register.py 는 원격 트리거 용도로만 유지 (관리자 편의)
  - 자세한 내용: 서버클라이언트_설계도.md § 0-B / system_architecture.md "핵심 원칙"
"""
import sys
import os
from pathlib import Path

# ★ SQLite-only 모드 강제 (2026-05-26 결정: Firestore 폐기, problem_bank.db 단일 마스터)
#   - LocalDBEngine 사용 (캐시/Firestore 미러 미사용)
#   - Firestore 코드는 dead code 로 보존 (롤백 가능)
#   - 단, Firebase Auth (로그인) 는 backend/auth.py 에서 그대로 사용
os.environ.setdefault("DATA_ENGINE", "sqlite")

# backend.* import 가능하게 프로젝트 루트를 sys.path 에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from server import config
from server.routes import api_admin, api_auth, api_exam, api_library, api_manage, api_meta, api_problems, api_register, api_users, pages
from server.workers.job_queue import get_queue

# Firebase Admin 초기화 (기존 backend/firebase_init 활용)
from backend.firebase_init import init_admin_sdk, KeyNotFoundError
try:
    init_admin_sdk()
    print("[main] Firebase Admin SDK 초기화 완료")
except KeyNotFoundError as e:
    print(f"[main] FATAL: Firebase 키 누락 — {e}")
    sys.exit(1)

# 캐시 주기 sync 주기 (초). 환경변수 NAEGIWANGBANK_CACHE_SYNC_INTERVAL 로 조정 가능.
_CACHE_SYNC_INTERVAL = int(os.environ.get("NAEGIWANGBANK_CACHE_SYNC_INTERVAL", "300"))  # 기본 5분


async def _periodic_cache_sync():
    """주기적으로 incremental_sync 호출 — 다른 PC 인덱싱/Firestore 직접 변경 반영용.

    incremental_sync 는 watermark(max updated_at) 이후 변경분만 받음.
    변경 없으면 거의 0 비용. 변경 있으면 그 양만큼만 받음.
    """
    from server.services.engine import get_engine
    while True:
        try:
            await asyncio.sleep(_CACHE_SYNC_INTERVAL)
            engine = get_engine()
            cache = getattr(engine, "cache", None)
            if cache is None:
                continue  # LocalDBEngine 모드 등 캐시 없으면 스킵
            n = cache.incremental_sync()
            if n > 0:
                print(f"[periodic_sync] {n}건 갱신")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[periodic_sync] 실패: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """워커 시작/종료."""
    queue = get_queue()
    queue.start(asyncio.get_running_loop())
    print("[main] HWP job worker 시작")

    sync_task = asyncio.create_task(_periodic_cache_sync())
    print(f"[main] 캐시 주기 sync 시작 (주기 {_CACHE_SYNC_INTERVAL}초)")

    yield

    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    print("[main] 캐시 주기 sync 종료")

    await queue.stop()
    print("[main] HWP job worker 종료")


app = FastAPI(
    title="상승 Solution",
    version="2.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

app.include_router(pages.router)
app.include_router(api_auth.router)
app.include_router(api_meta.router)
app.include_router(api_problems.router)
app.include_router(api_exam.router)
app.include_router(api_manage.router)
app.include_router(api_library.router)
app.include_router(api_users.router)
app.include_router(api_register.router)
app.include_router(api_admin.router)


@app.get("/healthz")
def healthz():
    import sqlite3
    from server.services.engine import get_engine
    try:
        engine = get_engine()
        db_path = getattr(engine, "db_path", None)
        if db_path:
            with sqlite3.connect(db_path, timeout=2.0) as conn:
                conn.execute("SELECT 1").fetchone()
        return {"ok": True, "service": "naegiwangbank-server", "db": "ok"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "service": "naegiwangbank-server",
                     "error": f"{type(e).__name__}: {e}"},
        )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None) or {},
    )
