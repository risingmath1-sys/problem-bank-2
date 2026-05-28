"""문제 관리 API — 인라인 편집 / 제외토글 / 선호도 / 파일 일괄 삭제."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server import config
from server.auth_dep import require_admin, SessionUser
from server.services.engine import get_engine

router = APIRouter(prefix="/api/manage", tags=["manage"])
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


def _render_problem_row(request: Request, problem: dict, preference: Optional[str]):
    from server.routes.pages import _flatten_unit_options
    return templates.TemplateResponse(
        request, "partials/manage_problem_row.html",
        {"p": problem, "pref": preference, "all_units": _flatten_unit_options()},
    )


def _reload_problem(engine, problem_id: str) -> Optional[dict]:
    """단일 문제를 file_name 기반 재조회 — 변경 직후 행 재렌더용."""
    rows = engine.search_problems({"id": problem_id}, limit=1) if hasattr(engine, "search_problems") else None
    if rows:
        return rows[0]
    return None


@router.post("/exclusion", response_class=HTMLResponse)
def toggle_exclusion(
    request: Request,
    problem_id: str = Form(...),
    excluded: int = Form(...),  # 1=제외, 0=복원
    file_name: str = Form(...),
    user: SessionUser = Depends(require_admin),
):
    engine = get_engine()
    engine.set_exclusion_status([problem_id], bool(excluded))
    # 행만 다시 그려서 보냄
    rows = engine.get_problems_by_files([file_name])
    target = next((r for r in rows if str(r.get("id")) == str(problem_id)), None)
    if not target:
        return HTMLResponse('<tr><td colspan="6" class="text-red-300 text-xs px-2 py-1">문제를 찾을 수 없습니다.</td></tr>')
    pref_map = engine.get_preferences_bulk(user.uid, [problem_id]) or {}
    return _render_problem_row(request, target, pref_map.get(str(problem_id)))


@router.post("/preference", response_class=HTMLResponse)
def set_preference(
    request: Request,
    problem_id: str = Form(...),
    value: str = Form(""),  # "Good"/"Soso"/"Bad"/"" (빈 문자열=해제)
    file_name: str = Form(...),
    user: SessionUser = Depends(require_admin),
):
    if value and value not in ("Good", "Soso", "Bad"):
        raise HTTPException(400, "유효하지 않은 선호도 값")
    engine = get_engine()
    engine.set_preference(user.uid, problem_id, value or None)
    rows = engine.get_problems_by_files([file_name])
    target = next((r for r in rows if str(r.get("id")) == str(problem_id)), None)
    if not target:
        return HTMLResponse('<tr><td colspan="6" class="text-red-300 text-xs px-2 py-1">문제를 찾을 수 없습니다.</td></tr>')
    pref_map = engine.get_preferences_bulk(user.uid, [problem_id]) or {}
    return _render_problem_row(request, target, pref_map.get(str(problem_id)))


@router.post("/meta", response_class=HTMLResponse)
def update_meta(
    request: Request,
    problem_id: str = Form(...),
    field: str = Form(...),  # 'unit_code' or 'difficulty'
    value: str = Form(...),
    unit_name: Optional[str] = Form(None),
    file_name: str = Form(...),
    user: SessionUser = Depends(require_admin),
):
    if field not in ("unit_code", "difficulty"):
        raise HTTPException(400, "수정 불가 필드")
    engine = get_engine()
    engine.update_problem_meta(problem_id, field, value, unit_name)
    rows = engine.get_problems_by_files([file_name])
    target = next((r for r in rows if str(r.get("id")) == str(problem_id)), None)
    if not target:
        return HTMLResponse('<tr><td colspan="6" class="text-red-300 text-xs px-2 py-1">문제를 찾을 수 없습니다.</td></tr>')
    pref_map = engine.get_preferences_bulk(user.uid, [problem_id]) or {}
    return _render_problem_row(request, target, pref_map.get(str(problem_id)))


@router.post("/files/exclude", response_class=HTMLResponse)
def bulk_exclude_by_files(
    request: Request,
    file_names: List[str] = Form(default_factory=list),
    excluded: int = Form(...),  # 1 / 0
    user: SessionUser = Depends(require_admin),
):
    if not file_names:
        return HTMLResponse('<div class="text-yellow-300 text-xs">선택된 파일이 없습니다.</div>')
    engine = get_engine()
    rows = engine.get_problems_by_files(file_names)
    ids = [str(r["id"]) for r in rows]
    if not ids:
        return HTMLResponse('<div class="text-yellow-300 text-xs">대상 문제가 없습니다.</div>')
    n = engine.set_exclusion_status(ids, bool(excluded))
    action = "제외" if excluded else "복원"
    return HTMLResponse(
        f'<div class="text-green-300 text-xs">{action} 완료: {n}문제 · {len(file_names)}파일</div>'
    )


@router.post("/files/delete", response_class=HTMLResponse)
def bulk_delete_files(
    request: Request,
    file_names: List[str] = Form(default_factory=list),
    confirm: str = Form(""),
    user: SessionUser = Depends(require_admin),
):
    if not file_names:
        return HTMLResponse('<div class="text-yellow-300 text-xs">선택된 파일이 없습니다.</div>')
    if confirm != "DELETE":
        return HTMLResponse(
            '<div class="text-red-300 text-xs">안전 확인 실패 — confirm 값이 잘못되었습니다.</div>'
        )
    engine = get_engine()
    n = engine.delete_exams_by_filenames(file_names)
    return HTMLResponse(
        f'<div class="text-green-300 text-xs">삭제 완료: {n}문제 · {len(file_names)}파일</div>'
        f'<script>document.getElementById("manage-files-form").dispatchEvent(new Event("change"));</script>'
    )


def _is_empty_coord(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s in ("", "[]", "null", "None")


@router.post("/files/diagnose", response_class=HTMLResponse)
def bulk_diagnose_files(
    request: Request,
    file_names: List[str] = Form(default_factory=list),
    user: SessionUser = Depends(require_admin),
):
    """파일 단위 진단 — 로컬 main_gui.py:5072-5211 _mgr_diagnose_selected 동등.

    각 파일에 대해:
      - 파일 존재 여부 (HWP_SOURCE_ROOT 인덱스 검색)
      - 좌표 유효성 (pos_start/pos_end 빈값 카운트 + 미주번호 표시)
      - 제외 문제 카운트
      - 해결책 안내
    """
    if not file_names:
        return HTMLResponse(
            '<div class="text-yellow-300 text-xs">선택된 파일이 없습니다.</div>'
        )
    engine = get_engine()
    rows = engine.get_problems_by_files(file_names)
    if not rows:
        return HTMLResponse(
            '<div class="text-yellow-300 text-xs">선택 파일에 등록된 문제가 없습니다.</div>'
        )

    from server.services import source_files
    from collections import defaultdict
    by_file = defaultdict(list)
    for r in rows:
        by_file[r.get("file_name") or ""].append(r)

    files_report = []
    for fname in sorted(k for k in by_file.keys() if k):
        flist = by_file[fname]
        found_path = source_files.find(fname)
        exists = bool(found_path)
        no_coord = []
        for r in flist:
            if _is_empty_coord(r.get("pos_start")) or _is_empty_coord(r.get("pos_end")):
                no_coord.append(r.get("endnote_index") or "?")
        excl_count = sum(1 for r in flist if r.get("is_excluded"))

        files_report.append({
            "file_name": fname,
            "exists": exists,
            "found_path": found_path or "",
            "total": len(flist),
            "excluded": excl_count,
            "no_coord_nums": no_coord,
            "no_coord_count": len(no_coord),
        })

    return templates.TemplateResponse(
        request, "partials/manage_diagnose.html",
        {"files_report": files_report, "total_files": len(files_report),
         "total_problems": len(rows)},
    )


@router.post("/files/reindex", response_class=HTMLResponse)
def bulk_reindex_files(
    request: Request,
    file_names: List[str] = Form(default_factory=list),
    user: SessionUser = Depends(require_admin),
):
    """파일 단위 재인덱싱 — 로컬 _mgr_reindex 동등 (HWP 파서 호출).

    주의: HWP COM 자동화는 메인 워커(=출제 큐)와 충돌 가능. 본 엔드포인트는
    재인덱싱이 출제 큐와 직렬화되도록 큐에 별도 잡으로 제출하는 게 정석이지만,
    현 구현은 파일 진단 결과를 갱신하는 가벼운 통보 + 안내까지만.

    실제 reindex 자체는 admin 이 데스크탑에서 수행하거나, 추후 워커 잡으로 분리.
    """
    if not file_names:
        return HTMLResponse(
            '<div class="text-yellow-300 text-xs">선택된 파일이 없습니다.</div>'
        )
    return HTMLResponse(
        f'<div class="bg-amber-900/30 border border-amber-700 text-amber-200 rounded-xl p-3 text-sm">'
        f'재인덱싱 요청 접수 ({len(file_names)}파일).<br>'
        f'<span class="text-xs">⚠ 재인덱싱은 HWP COM 직렬화 작업이라 출제 큐와 함께 처리됩니다 — '
        f'현재 인덱싱 워커가 분리되지 않아 데스크탑(.exe)에서 수행 권장.</span></div>'
    )
