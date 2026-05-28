"""시험지 관리 (Library) — 폴더/시험지 CRUD."""
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server import config
from server.auth_dep import require_user, SessionUser
from server.services.engine import get_engine

router = APIRouter(prefix="/api/library", tags=["library"])
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


def _ok(payload: dict | None = None) -> dict:
    base = {"success": True}
    if payload:
        base.update(payload)
    return base


def _err(message: str, status: int = 400):
    return HTMLResponse(
        f'<div class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-3 text-sm">{message}</div>',
        status_code=status,
    )


# ───── 폴더 ─────
@router.post("/folder", response_class=HTMLResponse)
async def folder_create(
    request: Request,
    name: str = Form(...),
    parent_id: Optional[str] = Form(None),
    user: SessionUser = Depends(require_user),
):
    name = (name or "").strip()
    if not name:
        return _err("폴더 이름을 입력하세요.")
    pid: Optional[int]
    if parent_id and parent_id != "root":
        try:
            pid = int(parent_id)
        except ValueError:
            pid = None
    else:
        pid = None
    engine = get_engine()
    res = engine.create_folder(name, user.uid, parent_id=pid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "폴더 생성 실패")
    # 폴더 트리 재조회
    folders = engine.get_folders(user.uid)
    from server.routes.pages import _build_folder_tree
    return templates.TemplateResponse(
        request, "partials/library_folders.html",
        {"tree": _build_folder_tree(folders)},
    )


@router.patch("/folder/{folder_id}", response_class=HTMLResponse)
async def folder_rename(
    request: Request,
    folder_id: int,
    name: str = Form(...),
    user: SessionUser = Depends(require_user),
):
    new_name = (name or "").strip()
    if not new_name:
        return _err("폴더 이름을 입력하세요.")
    engine = get_engine()
    if not engine.rename_folder(folder_id, new_name):
        return _err("폴더 이름 변경 실패")
    folders = engine.get_folders(user.uid)
    from server.routes.pages import _build_folder_tree
    return templates.TemplateResponse(
        request, "partials/library_folders.html",
        {"tree": _build_folder_tree(folders)},
    )


@router.delete("/folder/{folder_id}", response_class=HTMLResponse)
async def folder_delete(
    request: Request,
    folder_id: int,
    user: SessionUser = Depends(require_user),
):
    engine = get_engine()
    res = engine.delete_folder(folder_id) or {}
    if not res.get("success"):
        return _err(res.get("message") or "폴더 삭제 실패")
    folders = engine.get_folders(user.uid)
    from server.routes.pages import _build_folder_tree
    return templates.TemplateResponse(
        request, "partials/library_folders.html",
        {"tree": _build_folder_tree(folders)},
    )


# ───── 시험지 ─────
@router.post("/test/{test_id}/rename", response_class=HTMLResponse)
async def test_rename(
    request: Request,
    test_id: int,
    title: str = Form(...),
    unit_summary: Optional[str] = Form(""),
    user: SessionUser = Depends(require_user),
):
    title = (title or "").strip()
    if not title:
        return _err("시험지 제목을 입력하세요.")
    engine = get_engine()
    detail = engine.get_test_detail(test_id, user.uid)
    if not detail:
        return _err("시험지를 찾을 수 없거나 권한이 없습니다.", status=404)
    payload = {
        "id": test_id,
        "title": title,
        "unit_summary": (unit_summary or "").strip(),
        "directory_id": detail.get("directory_id"),
        "problem_ids": [p["id"] for p in (detail.get("problems") or []) if p.get("id")],
        "metadata": detail.get("metadata") or {},
    }
    res = engine.save_test(payload, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "저장 실패")
    detail = engine.get_test_detail(test_id, user.uid)
    # 2026-05-23: pref_map / folders / unit_options 누락 시 선호도 버튼 등이 망가짐.
    # pages.py:partial_library_test_preview 와 동일 컨텍스트로 통일.
    folders = engine.get_folders(user.uid)
    from server.routes.pages import _load_unit_mappings
    unit_mappings = _load_unit_mappings()
    unit_options = [{"code": k, "name": v} for k, v in unit_mappings.items()]
    problem_ids = [p.get("id") for p in (detail.get("problems") or []) if p.get("id") is not None]
    try:
        pref_map = engine.get_preferences_bulk(user.uid, problem_ids) or {}
    except Exception:
        pref_map = {}
    return templates.TemplateResponse(
        request, "partials/library_test_preview.html",
        {
            "test": detail,
            "folders": folders,
            "unit_options": unit_options,
            "pref_map": pref_map,
            "is_admin": (user.role == "admin"),
            "user_display": user.display_id or user.uid,
        },
    )


@router.post("/test/{test_id}/move", response_class=HTMLResponse)
async def test_move(
    request: Request,
    test_id: int,
    folder_id: Optional[str] = Form(None),
    user: SessionUser = Depends(require_user),
):
    engine = get_engine()
    detail = engine.get_test_detail(test_id, user.uid)
    if not detail:
        return _err("시험지를 찾을 수 없거나 권한이 없습니다.", status=404)
    if folder_id and folder_id != "root":
        try:
            dir_id = int(folder_id)
        except ValueError:
            dir_id = None
    else:
        dir_id = None
    payload = {
        "id": test_id,
        "title": detail.get("title", ""),
        "unit_summary": detail.get("unit_summary", ""),
        "directory_id": dir_id,
        "problem_ids": [p["id"] for p in (detail.get("problems") or []) if p.get("id")],
        "metadata": detail.get("metadata") or {},
    }
    res = engine.save_test(payload, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "이동 실패")
    detail = engine.get_test_detail(test_id, user.uid)
    # 2026-05-23: 동일 — pref_map / folders / unit_options 누락 방지
    folders = engine.get_folders(user.uid)
    from server.routes.pages import _load_unit_mappings
    unit_mappings = _load_unit_mappings()
    unit_options = [{"code": k, "name": v} for k, v in unit_mappings.items()]
    problem_ids = [p.get("id") for p in (detail.get("problems") or []) if p.get("id") is not None]
    try:
        pref_map = engine.get_preferences_bulk(user.uid, problem_ids) or {}
    except Exception:
        pref_map = {}
    return templates.TemplateResponse(
        request, "partials/library_test_preview.html",
        {
            "test": detail,
            "folders": folders,
            "unit_options": unit_options,
            "pref_map": pref_map,
            "is_admin": (user.role == "admin"),
            "user_display": user.display_id or user.uid,
        },
    )


@router.post("/test/{test_id}/duplicate", response_class=HTMLResponse)
async def test_duplicate(
    request: Request,
    test_id: int,
    folder_id: Optional[str] = Form(None),
    title_suffix: Optional[str] = Form(" (복사본)"),
    user: SessionUser = Depends(require_user),
):
    """선택 시험지를 다른(또는 같은) 폴더에 복사 — main_gui.py:6720 _lib_copy_test 포팅."""
    engine = get_engine()
    detail = engine.get_test_detail(test_id, user.uid)
    if not detail:
        return _err("시험지를 찾을 수 없거나 권한이 없습니다.", status=404)
    if folder_id and folder_id != "root":
        try:
            dir_id = int(folder_id)
        except ValueError:
            dir_id = None
    else:
        dir_id = None
    p_ids = [p["id"] for p in (detail.get("problems") or []) if p.get("id")]
    if not p_ids:
        return _err("원본 시험지에 문제가 없습니다.")
    new_title = (detail.get("title") or "") + (title_suffix or "")
    res = engine.save_test({
        "title": new_title,
        "unit_summary": detail.get("unit_summary", ""),
        "directory_id": dir_id,
        "problem_ids": p_ids,
        "metadata": detail.get("metadata") or {},
    }, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "복사 실패")
    return HTMLResponse(
        f'<div class="bg-emerald-900/40 border border-emerald-700 text-emerald-200 rounded-xl p-3 text-sm">'
        f'시험지 복사 완료 → "{new_title}" (id={res.get("id")})</div>'
    )


@router.delete("/test/{test_id}")
async def test_delete(
    test_id: int,
    user: SessionUser = Depends(require_user),
):
    engine = get_engine()
    detail = engine.get_test_detail(test_id, user.uid)
    if not detail:
        raise HTTPException(404, "시험지를 찾을 수 없거나 권한이 없습니다.")
    if not engine.delete_test(test_id):
        raise HTTPException(500, "삭제 실패")
    return HTMLResponse(
        '<div class="text-slate-500 text-sm">시험지가 삭제되었습니다. 좌측에서 다시 선택하세요.</div>'
    )


@router.post("/save_original", response_class=HTMLResponse)
async def save_original(
    request: Request,
    file_name: str = Form(...),
    title: str = Form(...),
    unit_summary: Optional[str] = Form(""),
    folder_id: Optional[str] = Form(None),
    problem_ids: list[str] = Form(default_factory=list),
    user: SessionUser = Depends(require_user),
):
    """원본출제 파일 → 시험지로 저장."""
    title = (title or "").strip()
    if not title:
        return _err("시험지 제목을 입력하세요.")
    engine = get_engine()
    file_problems = engine.get_problems_by_files([file_name])
    if not file_problems:
        return _err("파일에 등록된 문제가 없습니다.", status=404)
    if problem_ids:
        sel = {str(p): True for p in problem_ids if p}
        file_problems = [p for p in file_problems if str(p.get("id")) in sel]
    p_ids = [p.get("id") for p in file_problems if p.get("id")]
    if not p_ids:
        return _err("저장할 문제가 없습니다.")
    if folder_id and folder_id != "root":
        try:
            dir_id = int(folder_id)
        except ValueError:
            dir_id = None
    else:
        dir_id = None
    res = engine.save_test({
        "title": title,
        "unit_summary": (unit_summary or "").strip(),
        "directory_id": dir_id,
        "problem_ids": p_ids,
        "metadata": {},
    }, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "저장 실패")
    return HTMLResponse(
        f'<div class="bg-emerald-900/40 border border-emerald-700 text-emerald-200 rounded-xl p-3 text-sm">'
        f'시험지 "{title}" 저장됨 (id={res.get("id")}).</div>'
    )


@router.post("/save_random_draft", response_class=HTMLResponse)
async def save_random_draft(
    request: Request,
    title: str = Form(...),
    unit_summary: Optional[str] = Form(""),
    folder_id: Optional[str] = Form(None),
    user: SessionUser = Depends(require_user),
):
    """랜덤출제 Step 4 [테스트저장] — 출제 큐 등록 없이 draft 의 문항을 시험지로 저장.
    로컬 _open_save_dialog_step4 (main_gui.py:4390) 동등.
    """
    from server.services import exam_session
    title = (title or "").strip()
    if not title:
        return _err("시험지 제목을 입력하세요.")
    draft = exam_session.get_draft(user.uid)
    if draft.total == 0:
        return _err("저장할 문항이 없습니다.")
    p_ids = [p.get("id") for p in draft.all_problems if p.get("id")]
    if not p_ids:
        return _err("저장할 문항이 없습니다.")
    if folder_id and folder_id != "root":
        try:
            dir_id = int(folder_id)
        except ValueError:
            dir_id = None
    else:
        dir_id = None
    engine = get_engine()
    res = engine.save_test({
        "title": title,
        "unit_summary": (unit_summary or "").strip(),
        "directory_id": dir_id,
        "problem_ids": p_ids,
        "metadata": {"source": "random_draft"},
    }, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "저장 실패")
    # draft 의 exam_title 도 갱신 (저장 후 출제 시 제목 자동 채움).
    # ※ 저장 후 reset 하지 않음 — 사용자가 [저장] → [테스트출제] 흐름을 자주 사용함.
    #    draft 정리는 [마침]/[닫기]→home, 또는 새 [랜덤출제] 진입 시 자동 처리됨.
    draft.exam_title = title
    return HTMLResponse(
        f'<div class="bg-emerald-900/40 border border-emerald-700 text-emerald-200 rounded-xl p-3 text-sm">'
        f'✓ 시험지 "{title}" 저장됨 (id={res.get("id")}). 시험지관리 탭에서 확인 가능.</div>'
    )


@router.post("/save_random_job/{job_id}", response_class=HTMLResponse)
async def save_random_job(
    request: Request,
    job_id: str,
    title: str = Form(...),
    unit_summary: Optional[str] = Form(""),
    folder_id: Optional[str] = Form(None),
    user: SessionUser = Depends(require_user),
):
    """랜덤출제 결과 (Job) → 시험지로 저장."""
    title = (title or "").strip()
    if not title:
        return _err("시험지 제목을 입력하세요.")
    from server.workers.job_queue import get_queue
    job = get_queue().get(job_id)
    if not job or job.user_id != user.uid:
        return _err("작업을 찾을 수 없습니다.", status=404)
    if folder_id and folder_id != "root":
        try:
            dir_id = int(folder_id)
        except ValueError:
            dir_id = None
    else:
        dir_id = None
    p_ids = [p.get("id") for p in (job.problems or []) if p.get("id")]
    if not p_ids:
        return _err("저장할 문제가 없습니다.")
    engine = get_engine()
    summary = (unit_summary or "").strip() or job.options.get("exam_unit") or ""
    res = engine.save_test({
        "title": title,
        "unit_summary": summary,
        "directory_id": dir_id,
        "problem_ids": p_ids,
        "metadata": {},
    }, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "저장 실패")
    return HTMLResponse(
        f'<div class="bg-emerald-900/40 border border-emerald-700 text-emerald-200 rounded-xl p-3 text-sm">'
        f'시험지 "{title}" 저장됨 (id={res.get("id")}).</div>'
    )


# ───── 시험지 목록 일괄 작업 (복수 선택) ─────
# 로컬 main_gui.py:6634 (delete) / 6663 (move) / 6759 (copy) 동등
def _render_lib_tests(request: Request, user: SessionUser,
                     folder_id: Optional[str], sort: str, q: str,
                     flash: dict | None = None) -> HTMLResponse:
    """library_tests.html partial 재렌더 — pages.partial_library_tests 와 동일 로직."""
    engine = get_engine()
    if not folder_id or folder_id == "root":
        fid = None
    else:
        try:
            fid = int(folder_id)
        except ValueError:
            fid = None
    tests = engine.get_tests(directory_id=fid, user_id=user.uid)
    import json as _json
    for t in tests:
        try:
            t["_count"] = len(_json.loads(t.get("problem_ids") or "[]"))
        except Exception:
            t["_count"] = 0
    kw = (q or "").strip().lower()
    if kw:
        tests = [
            t for t in tests
            if kw in (t.get("title") or "").lower()
            or kw in (t.get("unit_summary") or "").lower()
        ]
    if sort == "title":
        tests.sort(key=lambda t: t.get("title") or "")
    else:
        tests.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    folders = engine.get_folders(user.uid)
    return templates.TemplateResponse(
        request, "partials/library_tests.html",
        {
            "tests": tests,
            "folder_id": folder_id or "root",
            "sort": sort,
            "q": q or "",
            "folders": folders,
            "flash": flash,
        },
    )


@router.post("/tests/bulk_delete", response_class=HTMLResponse)
async def tests_bulk_delete(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """복수 시험지 삭제. Form: test_ids[]=int, folder_id, sort, q.
    응답: 결과 flash + 갱신된 library_tests partial."""
    form = await request.form()
    test_ids_raw = form.getlist("test_ids")
    folder_id = form.get("folder_id") or "root"
    sort = form.get("sort") or "created"
    q = form.get("q") or ""

    test_ids: list[int] = []
    for v in test_ids_raw:
        try:
            test_ids.append(int(v))
        except (TypeError, ValueError):
            pass
    if not test_ids:
        return _render_lib_tests(request, user, folder_id, sort, q,
                                 flash={"level": "warn", "msg": "선택된 시험지가 없습니다."})

    engine = get_engine()
    ok = 0
    fail: list[tuple[int, str]] = []
    for tid in test_ids:
        try:
            detail = engine.get_test_detail(tid, user.uid)
            if not detail:
                fail.append((tid, "권한/없음"))
                continue
            if engine.delete_test(tid):
                ok += 1
            else:
                fail.append((tid, "삭제 실패"))
        except Exception as e:
            fail.append((tid, str(e)))

    if not fail:
        msg = f"{ok}개 삭제 완료"
        level = "success"
    else:
        msg = f"{ok}/{len(test_ids)} 삭제됨 (실패 {len(fail)}건)"
        level = "warn"
    return _render_lib_tests(request, user, folder_id, sort, q,
                             flash={"level": level, "msg": msg})


@router.post("/tests/bulk_move", response_class=HTMLResponse)
async def tests_bulk_move(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """복수 시험지 폴더 이동. Form: test_ids[], target_folder_id, folder_id, sort, q."""
    form = await request.form()
    test_ids_raw = form.getlist("test_ids")
    target_folder_id = form.get("target_folder_id") or "root"
    folder_id = form.get("folder_id") or "root"
    sort = form.get("sort") or "created"
    q = form.get("q") or ""

    test_ids: list[int] = []
    for v in test_ids_raw:
        try:
            test_ids.append(int(v))
        except (TypeError, ValueError):
            pass
    if not test_ids:
        return _render_lib_tests(request, user, folder_id, sort, q,
                                 flash={"level": "warn", "msg": "선택된 시험지가 없습니다."})

    if target_folder_id == "root":
        target_dir_id = None
    else:
        try:
            target_dir_id = int(target_folder_id)
        except ValueError:
            target_dir_id = None

    engine = get_engine()
    ok = 0
    fail: list[tuple[int, str]] = []
    for tid in test_ids:
        try:
            detail = engine.get_test_detail(tid, user.uid)
            if not detail:
                fail.append((tid, "권한/없음"))
                continue
            payload = {
                "id": tid,
                "title": detail.get("title", ""),
                "unit_summary": detail.get("unit_summary", ""),
                "directory_id": target_dir_id,
                "problem_ids": [p["id"] for p in (detail.get("problems") or []) if p.get("id")],
                "metadata": detail.get("metadata") or {},
            }
            res = engine.save_test(payload, user.uid) or {}
            if res.get("success"):
                ok += 1
            else:
                fail.append((tid, res.get("message") or "이동 실패"))
        except Exception as e:
            fail.append((tid, str(e)))

    if not fail:
        msg = f"{ok}개 이동 완료"
        level = "success"
    else:
        msg = f"{ok}/{len(test_ids)} 이동됨 (실패 {len(fail)}건)"
        level = "warn"
    return _render_lib_tests(request, user, folder_id, sort, q,
                             flash={"level": level, "msg": msg})


@router.post("/tests/bulk_duplicate", response_class=HTMLResponse)
async def tests_bulk_duplicate(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """복수 시험지 폴더 복사. Form: test_ids[], target_folder_id, folder_id, sort, q."""
    form = await request.form()
    test_ids_raw = form.getlist("test_ids")
    target_folder_id = form.get("target_folder_id") or "root"
    folder_id = form.get("folder_id") or "root"
    sort = form.get("sort") or "created"
    q = form.get("q") or ""

    test_ids: list[int] = []
    for v in test_ids_raw:
        try:
            test_ids.append(int(v))
        except (TypeError, ValueError):
            pass
    if not test_ids:
        return _render_lib_tests(request, user, folder_id, sort, q,
                                 flash={"level": "warn", "msg": "선택된 시험지가 없습니다."})

    if target_folder_id == "root":
        target_dir_id = None
    else:
        try:
            target_dir_id = int(target_folder_id)
        except ValueError:
            target_dir_id = None

    engine = get_engine()
    ok = 0
    fail: list[tuple[int, str]] = []
    for tid in test_ids:
        try:
            detail = engine.get_test_detail(tid, user.uid)
            if not detail:
                fail.append((tid, "권한/없음"))
                continue
            p_ids = [p["id"] for p in (detail.get("problems") or []) if p.get("id")]
            if not p_ids:
                fail.append((tid, "원본 문제 없음"))
                continue
            payload = {
                "title": detail.get("title", "") or "",
                "unit_summary": detail.get("unit_summary", ""),
                "directory_id": target_dir_id,
                "problem_ids": p_ids,
                "metadata": detail.get("metadata") or {},
            }
            res = engine.save_test(payload, user.uid) or {}
            if res.get("success"):
                ok += 1
            else:
                fail.append((tid, res.get("message") or "복사 실패"))
        except Exception as e:
            fail.append((tid, str(e)))

    if not fail:
        msg = f"{ok}개 복사 완료"
        level = "success"
    else:
        msg = f"{ok}/{len(test_ids)} 복사됨 (실패 {len(fail)}건)"
        level = "warn"
    return _render_lib_tests(request, user, folder_id, sort, q,
                             flash={"level": level, "msg": msg})


# ───── 문항 보기 인라인 편집 (단원/난이도/선호도/시험지내 삭제) ─────
# 로컬 main_gui.py:6402-6469 _make_inline_editor + 6536 _make_pref_handler + 6560 _make_delete_handler 동등
@router.patch("/problem/{pid}/meta", response_class=HTMLResponse)
async def problem_meta_update(
    request: Request,
    pid: str,
    field: str = Form(...),
    code: str = Form(""),
    name: Optional[str] = Form(""),
    user: SessionUser = Depends(require_user),
):
    """문제 메타데이터 인라인 편집. field='unit_code'|'difficulty'.
    응답: 새 표시 텍스트 (HTML 조각, label에 그대로 swap)."""
    field = (field or "").strip()
    code = (code or "").strip()
    name = (name or "").strip()
    if field not in ("unit_code", "difficulty"):
        return _err("허용되지 않은 필드", status=400)
    engine = get_engine()
    try:
        if field == "difficulty":
            engine.update_problem_meta(str(pid), "difficulty", code)
        else:  # unit_code
            engine.update_problem_meta(str(pid), "unit_code", code, name)
    except Exception as e:
        return _err(f"저장 실패: {e}", status=500)

    # 응답: 새 표시 텍스트만 (label에 hx-swap=innerHTML 로 들어감)
    if field == "difficulty":
        level_map = {"A": "최상", "B": "상", "C": "중", "D": "하"}
        display = f"{code}: {level_map.get(code, '')}" if code in level_map else code
    else:
        display = name or code or ""
    return HTMLResponse(display)


@router.post("/problem/{pid}/preference", response_class=HTMLResponse)
async def problem_preference_set(
    request: Request,
    pid: str,
    preference: str = Form(""),
    safe_id: str = Form(""),
    user: SessionUser = Depends(require_user),
):
    """선호도 토글. preference='Good'|'Soso'|'Bad'|'' (해제).
    응답: 갱신된 3색 토글 버튼 HTML (선호도 셀 전체 교체).
    2026-05-23: pid 가 한글/[,] 포함 시 CSS selector 깨짐 방지용 safe_id 사용.
    (Pydantic V2 가 leading underscore 거부하여 이름은 underscore 없이 'safe_id'.)
    """
    pref = (preference or "").strip()
    if pref and pref not in ("Good", "Soso", "Bad"):
        return _err("허용되지 않은 선호도", status=400)
    engine = get_engine()
    try:
        engine.set_preference(user.uid, str(pid), pref or None)
    except Exception as e:
        return _err(f"선호도 저장 실패: {e}", status=500)
    return templates.TemplateResponse(
        request, "partials/library_pref_buttons.html",
        {"pid": pid, "current": pref or None, "safe_id": (safe_id or None)},
    )


@router.delete("/test/{tid}/problem/{pid}", response_class=HTMLResponse)
async def test_problem_remove(
    request: Request,
    tid: int,
    pid: str,
    user: SessionUser = Depends(require_user),
):
    """이 시험지의 problem_ids 에서만 pid 제거 (DB 문제 자체는 유지).
    로컬 main_gui.py:6560 _make_delete_handler 동등.
    응답: 새로 렌더한 preview partial (행 번호 재정렬)."""
    engine = get_engine()
    detail = engine.get_test_detail(tid, user.uid)
    if not detail:
        return _err("시험지를 찾을 수 없거나 권한이 없습니다.", status=404)

    cur_pids = [p.get("id") for p in (detail.get("problems") or []) if p.get("id") is not None]
    new_pids = [x for x in cur_pids if str(x) != str(pid)]
    if len(new_pids) == len(cur_pids):
        return _err("해당 문제를 찾을 수 없습니다.", status=404)

    payload = {
        "id": tid,
        "title": detail.get("title", ""),
        "unit_summary": detail.get("unit_summary", ""),
        "directory_id": detail.get("directory_id"),
        "problem_ids": new_pids,
        "metadata": detail.get("metadata") or {},
    }
    res = engine.save_test(payload, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "삭제 실패", status=500)

    # 새로 렌더 — preview 전체를 swap
    detail = engine.get_test_detail(tid, user.uid)
    folders = engine.get_folders(user.uid)
    from server.routes.pages import _load_unit_mappings
    unit_mappings = _load_unit_mappings()
    unit_options = [{"code": k, "name": v} for k, v in unit_mappings.items()]
    problem_ids = [p.get("id") for p in (detail.get("problems") or []) if p.get("id") is not None]
    try:
        pref_map = engine.get_preferences_bulk(user.uid, problem_ids) or {}
    except Exception:
        pref_map = {}
    return templates.TemplateResponse(
        request, "partials/library_test_preview.html",
        {
            "test": detail,
            "folders": folders,
            "unit_options": unit_options,
            "pref_map": pref_map,
            "is_admin": (user.role == "admin"),
            "user_display": user.display_id or user.uid,
        },
    )


# ───── 오답 만들기 (채점) — 로컬 main_gui.py:6925-6944 + ScoringDialog 동등 ─────
@router.get("/test/{tid}/scoring", response_class=HTMLResponse)
def scoring_open(
    request: Request,
    tid: int,
    user: SessionUser = Depends(require_user),
):
    """채점 화면 partial — O/X 토글 + [적용] 버튼."""
    engine = get_engine()
    detail = engine.get_test_detail(tid, user.uid)
    if not detail or not detail.get("problems"):
        return _err("시험지를 찾을 수 없습니다.", status=404)
    existing = engine.get_scores_for_test(tid) or {}
    return templates.TemplateResponse(
        request, "partials/library_scoring.html",
        {"test": detail, "existing": existing},
    )


@router.post("/test/{tid}/save_wrong", response_class=HTMLResponse)
async def scoring_save_wrong(
    request: Request,
    tid: int,
    user: SessionUser = Depends(require_user),
):
    """채점 점수 저장 + 오답(X 문항) 시험지 자동 저장.

    Form: score_<pid>=1 (O) | 0 (X). 누락된 pid 는 1(O) 처리.
    오답 시험지는 "오답" 보호 폴더에 저장. 제목 = "{원래제목}의 오답".
    """
    form = await request.form()
    engine = get_engine()
    detail = engine.get_test_detail(tid, user.uid)
    if not detail:
        return _err("시험지를 찾을 수 없습니다.", status=404)
    problems = detail.get("problems") or []
    if not problems:
        return _err("문항이 없습니다.")

    scores: dict[str, int] = {}
    wrong_pids: list = []
    for p in problems:
        pid = p.get("id")
        key = f"score_{pid}"
        v = form.get(key)
        if v is None:
            scores[str(pid)] = 1
            continue
        s = 1 if str(v) == "1" else 0
        scores[str(pid)] = s
        if s == 0:
            wrong_pids.append(pid)

    # 점수 저장 (모든 문항)
    try:
        engine.save_scores(tid, scores)
    except Exception as e:
        return _err(f"채점 저장 실패: {e}")

    if not wrong_pids:
        return HTMLResponse(
            '<div class="bg-emerald-900/40 border border-emerald-700 text-emerald-200 rounded-xl p-3 text-sm">'
            '✓ 채점 저장 완료 — 오답 없음 (모두 O).</div>'
        )

    # 오답 폴더 보장 + 시험지 저장
    try:
        wrong_fid = engine.get_protected_folder_id("오답", user.uid)
        if not wrong_fid and hasattr(engine, "ensure_protected_folder_method"):
            wrong_fid = engine.ensure_protected_folder_method(user.uid, "오답")
    except Exception:
        wrong_fid = None

    wa_title = f"{detail.get('title') or ''}의 오답"
    res = engine.save_test({
        "title": wa_title,
        "unit_summary": detail.get("unit_summary") or "",
        "directory_id": wrong_fid,
        "problem_ids": wrong_pids,
        "metadata": {"source_test_id": tid, "type": "wrong_answers"},
    }, user.uid) or {}
    if not res.get("success"):
        return _err(res.get("message") or "오답 시험지 저장 실패")

    return HTMLResponse(
        f'<div class="bg-emerald-900/40 border border-emerald-700 text-emerald-200 rounded-xl p-3 text-sm">'
        f'✓ 채점 저장 + 오답 시험지 "{wa_title}" 저장됨 ({len(wrong_pids)}문항, id={res.get("id")}).<br>'
        f'<span class="text-xs">시험지관리 탭의 "오답" 폴더에서 확인하세요.</span></div>'
    )
