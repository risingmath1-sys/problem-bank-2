"""문제 등록 API — 인덱싱 워크플로 (admin 전용).

엔드포인트:
  POST /api/register/start                  — 인덱싱 잡 enqueue → progress partial
  GET  /api/register/{job_id}/progress      — 진행률 partial (폴링)
  GET  /partial/register/schema/{source}    — 소스별 schema 폼 partial (HTMX 동적 렌더)
"""
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server import config
from server.auth_dep import require_admin, SessionUser
from server.workers.job_queue import Job, get_queue

router = APIRouter(tags=["register"])
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))

VALID_SOURCES = {"NAESIN_A", "NAESIN_N", "SUNEUNG_SPECIAL", "SUNEUNG_COMPLETE", "MOCK_EXAM", "TEXTBOOK"}


def _get_indexer_safe(source: str):
    from backend.indexer_registry import get_indexer
    return get_indexer(source)


def _load_curriculum_keys() -> list:
    import json
    path = config.BASE_DIR / "backend" / "curriculum_config.json"
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("curriculums", {}).keys())
    except Exception:
        return []


def _subjects_for_curriculum(curr_name: str) -> list:
    import json
    if not curr_name:
        return []
    path = config.BASE_DIR / "backend" / "curriculum_config.json"
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        body = data.get("curriculums", {}).get(curr_name, {}) or {}
        return body.get("subjects") or []
    except Exception:
        return []


@router.get("/partial/register/schema/{source}", response_class=HTMLResponse)
def partial_register_schema(
    request: Request, source: str,
    user: SessionUser = Depends(require_admin),
):
    """소스별 인덱서 schema 의 fields 를 동적으로 렌더 (사이드 폼)."""
    if source not in VALID_SOURCES:
        return HTMLResponse('<div class="text-rose-300 text-xs">잘못된 소스입니다.</div>')
    indexer = _get_indexer_safe(source)
    if indexer is None:
        return HTMLResponse(
            '<div class="bg-amber-900/30 border border-amber-700 text-amber-200 rounded-xl p-3 text-sm">'
            f'⚠ {source} 인덱서가 미구현입니다 (예: TEXTBOOK).</div>'
        )
    schema = indexer.get_schema() or {}
    fields = schema.get("fields") or []
    return templates.TemplateResponse(
        request, "partials/register_schema.html",
        {
            "source": source,
            "label": schema.get("label", source),
            "fields": fields,
            "curriculum_keys": _load_curriculum_keys(),
        },
    )


@router.get("/partial/register/subjects", response_class=HTMLResponse)
def partial_register_subjects(
    request: Request, curriculum: str = "",
    user: SessionUser = Depends(require_admin),
):
    """교육과정 변경 시 과목 드롭다운 옵션만 갱신 (HTMX hx-target)."""
    subs = _subjects_for_curriculum(curriculum)
    opts = '<option value="">(선택)</option>' + "".join(
        f'<option value="{s}">{s}</option>' for s in subs
    )
    return HTMLResponse(opts)


@router.post("/api/register/start", response_class=HTMLResponse)
async def register_start(
    request: Request,
    user: SessionUser = Depends(require_admin),
):
    """인덱싱 잡 시작. Form:
      source       : 소스 코드
      target_path  : 서버 측 폴더/파일 절대 경로
      is_folder    : "1" / "0"
      force_reindex: "1" / "0"
      stealth_mode : "1" / "0" (기본 1)
      그 외 schema fields(db_key 기반): year/subject/curriculum 등 → common_meta 로 전달
    """
    form = await request.form()
    source = (form.get("source") or "").strip()
    target_path = (form.get("target_path") or "").strip()
    if source not in VALID_SOURCES:
        return HTMLResponse('<div class="text-rose-300 text-xs">잘못된 소스입니다.</div>')
    if not target_path:
        return HTMLResponse(
            '<div class="text-rose-300 text-xs">서버 측 폴더/파일 경로를 입력하세요.</div>'
        )
    if not os.path.exists(target_path):
        return HTMLResponse(
            f'<div class="text-rose-300 text-xs">경로를 찾을 수 없습니다: {target_path}</div>'
        )
    is_folder = (form.get("is_folder") or "1") == "1"
    if is_folder and not os.path.isdir(target_path):
        return HTMLResponse(
            '<div class="text-rose-300 text-xs">폴더 경로가 아닙니다 (파일을 등록하려면 단일 파일 모드로 변경).</div>'
        )
    if (not is_folder) and (not os.path.isfile(target_path)):
        return HTMLResponse(
            '<div class="text-rose-300 text-xs">파일 경로가 아닙니다.</div>'
        )

    indexer = _get_indexer_safe(source)
    if indexer is None:
        return HTMLResponse(
            '<div class="text-amber-300 text-xs">⚠ 이 소스는 인덱서가 미구현입니다.</div>'
        )

    # Schema 의 db_key 를 기준으로 form 값을 common_meta 로 빌드
    schema = indexer.get_schema() or {}
    common_meta: dict = {}
    for f in schema.get("fields") or []:
        db_key = f.get("db_key") or f.get("key")
        if not db_key:
            continue
        # form 의 키는 db_key 또는 key 이름
        v = form.get(db_key) if form.get(db_key) is not None else form.get(f.get("key") or "")
        if v is not None:
            common_meta[db_key] = (v or "").strip() if isinstance(v, str) else v
    # source 는 항상 박아둠 (parser 가 사용)
    common_meta["source"] = source

    # required 검증
    required_db_key = ""
    try:
        required_db_key = indexer.get_required_db_key() or ""
    except Exception:
        pass
    if required_db_key and not common_meta.get(required_db_key):
        return HTMLResponse(
            f'<div class="text-rose-300 text-xs">필수 필드 누락: {required_db_key}</div>'
        )

    job = Job(
        id=uuid.uuid4().hex[:12],
        user_id=user.uid,
        kind="indexing",
        problems=[],
        options={
            "source": source,
            "target_path": target_path,
            "is_folder": is_folder,
            "force_reindex": (form.get("force_reindex") or "0") == "1",
            "stealth_mode": (form.get("stealth_mode") or "1") == "1",
            "common_meta": common_meta,
        },
    )
    queue = get_queue()
    await queue.submit(job)

    return templates.TemplateResponse(
        request, "partials/register_progress.html",
        {"job": job},
    )


@router.get("/api/register/{job_id}/progress", response_class=HTMLResponse)
def register_progress(
    request: Request, job_id: str,
    user: SessionUser = Depends(require_admin),
):
    """진행률 partial — HTMX 폴링용. 완료/실패 시 hx-trigger 를 빼고 결과 표시."""
    queue = get_queue()
    job = queue.get(job_id)
    if not job or job.kind != "indexing":
        return HTMLResponse(
            '<div class="bg-slate-800 border border-slate-700 rounded-xl p-3 text-slate-400">작업을 찾을 수 없습니다.</div>'
        )
    return templates.TemplateResponse(
        request, "partials/register_progress.html",
        {"job": job},
    )
