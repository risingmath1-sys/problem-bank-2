"""출제 API — 랜덤 출제 요청 / 진행률 / 다운로드."""
import json
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from server import config
from server.auth_dep import require_user, SessionUser
from server.services.engine import get_engine
from server.services import source_files
from server.services import exam_session
from server.workers.job_queue import Job, get_queue

router = APIRouter(prefix="/api/exam", tags=["exam"])
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


def _build_filters(
    sources, unit_codes, difficulties, problem_type, school, year,
) -> dict:
    f: dict = {}
    if sources:
        f["source"] = {"in": sources} if len(sources) > 1 else sources[0]
    if unit_codes:
        f["unit_code"] = {"in": unit_codes} if len(unit_codes) > 1 else unit_codes[0]
    if difficulties:
        f["difficulty"] = {"in": difficulties} if len(difficulties) > 1 else difficulties[0]
    if problem_type == "객관식":
        f["problem_type"] = "객관식"
    elif problem_type == "주관식":
        f["problem_type"] = {"in": ["주관식", "서술형", "단답형"]}
    if school:
        f["school"] = {"like": f"%{school}%"}
    if year:
        f["year"] = year
    return f


@router.post("/random", response_class=HTMLResponse)
async def random_exam(
    request: Request,
    sources: List[str] = Form(default_factory=list),
    unit_codes: List[str] = Form(default_factory=list),
    difficulties: List[str] = Form(default_factory=list),
    problem_type: Optional[str] = Form(None),
    school: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    qty: int = Form(10, ge=1, le=200),
    exam_title: Optional[str] = Form(""),
    user: SessionUser = Depends(require_user),
):
    """필터 + qty → 문제 추첨 → 큐 enqueue → progress partial 반환."""
    filters = _build_filters(sources, unit_codes, difficulties, problem_type, school, year)
    if not filters:
        return HTMLResponse(
            '<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">필터를 1개 이상 선택해 주세요.</div>',
            status_code=200,
        )

    engine = get_engine()
    criteria_list = [{"filters": filters, "qty": qty}]
    problems = engine.fetch_random_problems(criteria_list, exclude_ids=[], include_excluded=False)

    if not problems:
        return HTMLResponse(
            '<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">조건에 맞는 문제가 없습니다.</div>',
            status_code=200,
        )

    # 파일 경로 검증 (main_gui.py:4596-4641 포팅) — file_name → 절대경로 해석.
    validated, pre_skipped = source_files.validate_problems(problems)
    if not validated:
        missing = ", ".join(s.get("file_name") or str(s.get("id")) for s in pre_skipped[:10])
        more = "" if len(pre_skipped) <= 10 else f" 외 {len(pre_skipped)-10}개"
        return HTMLResponse(
            f'<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">'
            f'추첨된 {len(problems)}문제 모두 원본 HWP 파일을 찾을 수 없습니다.<br>'
            f'<span class="text-xs">예: {missing}{more}</span><br>'
            f'<span class="text-xs text-slate-400">서버 설정 NAEGIWANGBANK_HWP_SOURCE_DIR 또는 settings.json source_hwp_dir 확인.</span>'
            f'</div>',
            status_code=200,
        )

    job = Job(
        id=uuid.uuid4().hex[:12],
        user_id=user.uid,
        problems=validated,
        options={
            "exam_title": exam_title or "",
            "exam_unit": "",
            "exclude_tags": False,
            "stealth_mode": True,
        },
    )
    # ★ total 은 사용자가 "요청한" 전체 수 (validate에서 걸러진 것 포함)
    #   — 로컬 main_gui.py:4768 의 _original_total = len(_problems) 와 동등
    job.total = len(validated) + len(pre_skipped)
    job.skipped = list(pre_skipped)
    queue = get_queue()
    await queue.submit(job)

    return templates.TemplateResponse(
        request, "partials/exam_progress.html",
        {"job": job},
    )


def _load_units_for_expand():
    path = config.BASE_DIR / "backend" / "unit_hierarchy.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _expand_unit_to_codes(u_type: str, code: str, version: str) -> list:
    """대단원이면 자식 중단원 코드들, 중단원이면 자기 자신 1개."""
    if u_type != "large":
        return [code]
    units = _load_units_for_expand()
    for subj in units.get(version, []):
        for large in subj.get("large_units", []):
            if large["code"] == code:
                return [m["code"] for m in large.get("medium_units", [])]
    return []


@router.post("/random_multi", response_class=HTMLResponse)
async def random_exam_multi(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """다중 기준 랜덤 출제 — 로컬 _go_to_step_3 (main_gui.py:3496) 의 criteria_list 방식.

    Form 입력:
      units: ["type:code:version", ...]  (Step 2에서 이어진 hidden input)
      alloc_<key>: 단원별 수량 (key 는 step2_table 에서 발급한 것)
      exam_title: 시험지 제목 (선택)
    """
    form = await request.form()

    raw_units = form.getlist("units")
    selected = []
    for s in raw_units:
        parts = (s or "").split(":")
        if len(parts) == 3 and parts[0] in ("large", "medium"):
            selected.append({"type": parts[0], "code": parts[1], "version": parts[2]})
    if not selected:
        return HTMLResponse(
            '<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            '단원 선택이 유실되었습니다. 처음부터 다시 시도해주세요.</div>'
        )

    # 우측 패널 필터 (R-2 ~ R-7) — pages.py 와 같은 마커 기반 파싱.
    from server.routes.pages import (
        _parse_filter_form, _get_pref_filter_ids, _get_brand_filter_ids,
        _get_rate_filter_ids, _apply_year_filter,
    )
    fs = _parse_filter_form(form)

    view_level = fs["view_level"]
    diffs_active = fs["active_difficulties"] if view_level else []
    view_type = fs["view_type"]
    types_active = fs["active_types"] if view_type else []
    pref_ids = _get_pref_filter_ids(fs, user.uid)
    brand_ids = _get_brand_filter_ids(fs)
    rate_ids = _get_rate_filter_ids(fs)

    def _row_filters(unit_codes, lvl, typ):
        f: dict = {}
        if isinstance(unit_codes, list):
            f["unit_code"] = {"in": unit_codes} if len(unit_codes) > 1 else unit_codes[0]
        else:
            f["unit_code"] = unit_codes
        if lvl:
            f["difficulty"] = lvl
        if typ == "0":
            f["problem_type"] = "객관식"
        elif typ == "1":
            f["problem_type"] = {"in": ["주관식", "서술형", "단답형"]}
        sources = fs.get("sources_for_query")
        if sources is not None:
            if not sources:
                f["source"] = "__NONE__"
            elif len(sources) == 1:
                f["source"] = sources[0]
            else:
                f["source"] = {"in": sources}
        _apply_year_filter(f, fs)
        # 학교 (R-7) — schools_for_query: 풀네임 확장 리스트. None=미적용, []=강제 0.
        sq = fs.get("schools_for_query")
        if sq is not None:
            if not sq:
                f["school"] = "__NONE__"
            elif len(sq) == 1:
                f["school"] = sq[0]
            else:
                f["school"] = {"in": sq}
        # 문항번호 (R-7)
        if fs.get("pnum_option_on") and fs.get("active_problem_numbers"):
            f["problem_number"] = {"in": fs["active_problem_numbers"]}
        # 선호도 + 브랜드 + 정답률 — id 제약 교집합
        id_set = None
        for ids in (pref_ids, brand_ids, rate_ids):
            if ids is None:
                continue
            s = set(ids)
            id_set = s if id_set is None else (id_set & s)
        if id_set is not None:
            if not id_set:
                f["id"] = "__NONE__"
            else:
                from server.routes.pages import _apply_id_constraint
                _apply_id_constraint(f, get_engine(), id_set)
        return f

    # alloc 키 형식: alloc_<utype>_<code>_<version>_<lvl_or_>_<type_or_>
    if view_level and not diffs_active:
        target_levels = []
    elif view_level:
        target_levels = diffs_active
    else:
        target_levels = [None]
    if view_type and not types_active:
        target_types = []
    elif view_type:
        target_types = types_active
    else:
        target_types = [None]

    criteria_list = []
    total_qty = 0
    for u in selected:
        codes = _expand_unit_to_codes(u["type"], u["code"], u["version"])
        if not codes:
            continue
        unit_filter = codes if len(codes) > 1 else codes[0]
        for lvl in target_levels:
            for typ in target_types:
                key = f"{u['type']}_{u['code']}_{u['version']}_{lvl or '_'}_{typ or '_'}"
                try:
                    qty = int(form.get(f"alloc_{key}") or 0)
                except (TypeError, ValueError):
                    qty = 0
                if qty <= 0:
                    continue
                criteria_list.append({"filters": _row_filters(unit_filter, lvl, typ), "qty": qty})
                total_qty += qty

    if total_qty == 0:
        return HTMLResponse(
            '<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            '문항 수량을 1개 이상 입력해주세요.</div>'
        )
    if total_qty > 200:
        return HTMLResponse(
            f'<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            f'총 문항 수가 200을 초과합니다 (입력: {total_qty}).</div>'
        )

    engine = get_engine()

    # 일회성 제외 (제외설정 다이얼로그) — 로컬 _oneshot_excluded_problem_ids 동등
    draft_for_excl = exam_session.get_draft(user.uid)
    exclude_ids = list(getattr(draft_for_excl, "oneshot_excluded_problem_ids", set()) or [])

    problems = engine.fetch_random_problems(
        criteria_list, exclude_ids=exclude_ids,
        include_excluded=fs.get("include_excluded", False),
    )

    # 최신기출 우선선택 — 추첨 후 year desc 정렬해 상위만 잘라내는 것은 fetch 가
    # qty 만큼 이미 잘랐으므로, 여기서는 추첨 결과를 year desc 로 재정렬해 사용자에게 노출.
    if fs.get("recent_first") and problems:
        def _y(p):
            try:
                return int(p.get("year") or 0)
            except (TypeError, ValueError):
                return 0
        problems.sort(key=_y, reverse=True)

    if not problems:
        return HTMLResponse(
            '<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            '조건에 맞는 문항을 찾을 수 없습니다.</div>'
        )

    validated, pre_skipped = source_files.validate_problems(problems)
    if not validated:
        missing = ", ".join(s.get("file_name") or str(s.get("id")) for s in pre_skipped[:10])
        more = "" if len(pre_skipped) <= 10 else f" 외 {len(pre_skipped)-10}개"
        return HTMLResponse(
            f'<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            f'추첨된 {len(problems)}문제 모두 원본 HWP 파일을 찾을 수 없습니다.<br>'
            f'<span class="text-xs">예: {missing}{more}</span></div>'
        )

    # 정렬 적용 — 로컬 _apply_sort (main_gui.py:3802) 포팅.
    from server.routes.pages import _apply_problem_sort
    validated = _apply_problem_sort(validated, form)

    exam_title = (form.get("exam_title") or "").strip()
    exclude_tags = (form.get("exclude_tags") or "") == "1"

    # ── Step 3 (출제 문항 확인) 으로 이동 — 로컬 main_gui.py:3486~ 와 동등.
    # append 모드 자동 결정: draft.total > 0 이면 append, 아니면 new.
    # ("append_mode=0" 명시 시는 강제 reset.)
    draft = exam_session.get_draft(user.uid)
    explicit_mode = (form.get("append_mode") or "").strip()
    if explicit_mode == "0":
        draft.reset()
    elif explicit_mode == "1":
        pass  # append
    else:
        # 자동: draft 비었으면 reset 동등 (no-op)
        if draft.total == 0:
            draft.reset()
    draft.append_batch(validated)
    draft.pre_skipped = list(pre_skipped) + list(draft.pre_skipped or [])
    if exam_title:
        draft.exam_title = exam_title
    draft.exclude_tags = exclude_tags
    # [랜덤추가] 용 form 백업 — 로컬 _save_step2_filter_state 동등.
    # alloc_*, units, 우측 필터까지 전부 그대로 보존.
    draft.last_form_items = list(form.multi_items())

    from server.routes.pages import _render_step3
    return _render_step3(request, user.uid)


@router.post("/random_finalize", response_class=HTMLResponse)
async def random_exam_finalize(
    request: Request,
    exam_title: Optional[str] = Form(""),
    exclude_tags: Optional[str] = Form(""),
    user: SessionUser = Depends(require_user),
):
    """Step 3 [다음] — draft 의 문제들로 실제 HWP 출제 시작."""
    draft = exam_session.get_draft(user.uid)
    if draft.total == 0:
        return HTMLResponse(
            '<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            '출제할 문항이 없습니다. 처음부터 다시 시도해주세요.</div>'
        )

    problems = draft.all_problems
    pre_skipped = list(draft.pre_skipped or [])

    # 자동 단원 요약 (로컬 main_gui.py:4379-4381 포팅).
    units_set = {p.get("middle_unit") or "" for p in problems if p.get("middle_unit")}
    if not units_set:
        units_set = {p.get("large_unit") or "Unknown" for p in problems}
    units_list = [u for u in units_set if u]
    if len(units_list) > 1:
        exam_unit = f"{units_list[0]} 외 {len(units_list)-1}개"
    elif units_list:
        exam_unit = units_list[0]
    else:
        exam_unit = "미지정"

    final_title = (exam_title or "").strip() or draft.exam_title
    final_exclude_tags = ((exclude_tags or "") == "1") or draft.exclude_tags

    job = Job(
        id=uuid.uuid4().hex[:12],
        user_id=user.uid,
        problems=problems,
        options={
            "exam_title": final_title,
            "exam_unit": exam_unit,
            "exclude_tags": final_exclude_tags,
            "stealth_mode": True,
        },
    )
    # ★ total 은 사용자가 "요청한" 전체 수 (pre_skipped 포함) — 로컬 동등성
    job.total = len(problems) + len(pre_skipped)
    job.skipped = list(pre_skipped)
    queue = get_queue()
    await queue.submit(job)

    # 큐 등록 후 draft 비우기 (사용자가 새 출제 누르면 깨끗한 상태)
    exam_session.reset_draft(user.uid)

    return templates.TemplateResponse(
        request, "partials/random_step3.html",
        {"job": job, "skipped_count": len(pre_skipped)},
    )


@router.post("/original", response_class=HTMLResponse)
async def original_exam(
    request: Request,
    file_name: str = Form(...),
    exam_title: Optional[str] = Form(""),
    problem_ids: List[str] = Form(default_factory=list),
    exclude_tags: Optional[str] = Form(""),
    fast_answer_key: Optional[str] = Form(""),
    user: SessionUser = Depends(require_user),
):
    """파일 단위 원본 출제 — 선택된 문제만(또는 전체) 그대로 출제.
    추가 옵션: exclude_tags (내신기출 태그 미포함), fast_answer_key (정답지 자동 추가).
    로컬 main_gui.py:4544-4566 동등.
    """
    engine = get_engine()
    problems = engine.get_problems_by_files([file_name])
    if not problems:
        return HTMLResponse(
            '<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">파일에 등록된 문제가 없습니다.</div>',
            status_code=200,
        )

    # 선택된 문제 id 가 있으면 해당 문제만 사용 (원본 순서 유지)
    if problem_ids:
        sel = {str(p): True for p in problem_ids if p}
        problems = [p for p in problems if str(p.get("id")) in sel]
        if not problems:
            return HTMLResponse(
                '<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">선택된 문제가 파일과 일치하지 않습니다.</div>',
                status_code=200,
            )

    validated, pre_skipped = source_files.validate_problems(problems)
    if not validated:
        missing = ", ".join(s.get("file_name") or str(s.get("id")) for s in pre_skipped[:5])
        return HTMLResponse(
            f'<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">'
            f'문제 {len(problems)}개 모두 원본 HWP 파일을 찾을 수 없습니다.<br>'
            f'<span class="text-xs">예: {missing}</span></div>',
            status_code=200,
        )

    # 자동 단원 요약 (로컬 main_gui.py:4563-4568 포팅)
    # 로컬과 동등: middle_unit 우선, 없으면 large_unit
    units_set = {
        (p.get("middle_unit", "") or p.get("large_unit", ""))
        for p in validated
    }
    units_set.discard("")  # 빈 문자열 제거
    units_list = sorted(units_set)
    if len(units_list) > 1:
        exam_unit = f"{units_list[0]} 외 {len(units_list)-1}개"
    elif units_list:
        exam_unit = units_list[0]
    else:
        exam_unit = ""

    # exclude_tags 는 NAESIN_A/N 인 경우에만 의미 있음 — 다른 소스는 무시.
    has_naesin = any((p.get("source") or "") in ("NAESIN_A", "NAESIN_N") for p in validated)
    excl_tags_val = ((exclude_tags or "") == "1") and has_naesin
    fast_key_val = (fast_answer_key or "") == "1"

    job = Job(
        id=uuid.uuid4().hex[:12],
        user_id=user.uid,
        problems=validated,
        options={
            "exam_title": exam_title or file_name.rsplit(".", 1)[0],
            "exam_unit": exam_unit,  # ✅ 로컬과 동등하게 자동 계산
            "exclude_tags": excl_tags_val,
            "fast_answer_key": fast_key_val,
            "stealth_mode": True,
        },
    )
    job.total = len(validated) + len(pre_skipped)
    job.skipped = list(pre_skipped)
    queue = get_queue()
    await queue.submit(job)

    return templates.TemplateResponse(
        request, "partials/exam_progress.html",
        {"job": job},
    )


@router.post("/library", response_class=HTMLResponse)
async def library_exam(
    request: Request,
    test_id: int = Form(...),
    exam_title: Optional[str] = Form(""),
    exclude_tags: Optional[str] = Form(""),
    fast_answer_key: Optional[str] = Form(""),
    user: SessionUser = Depends(require_user),
):
    """저장된 시험지(saved_tests)를 그대로 출제."""
    engine = get_engine()
    detail = engine.get_test_detail(test_id, user.uid)
    if not detail or not detail.get("problems"):
        return HTMLResponse(
            '<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">시험지를 찾을 수 없거나 권한이 없습니다.</div>',
            status_code=200,
        )
    problems = detail["problems"]
    validated, pre_skipped = source_files.validate_problems(problems)
    if not validated:
        return HTMLResponse(
            f'<div class="bg-red-900/40 border border-red-700 text-red-200 rounded-xl p-4">'
            f'시험지 {len(problems)}문제 모두 원본 HWP 파일을 찾을 수 없습니다.</div>',
            status_code=200,
        )

    has_naesin = any((p.get("source") or "") in ("NAESIN_A", "NAESIN_N") for p in validated)
    excl_tags_val = ((exclude_tags or "") == "1") and has_naesin
    fast_key_val = (fast_answer_key or "") == "1"

    job = Job(
        id=uuid.uuid4().hex[:12],
        user_id=user.uid,
        problems=validated,
        options={
            "exam_title": exam_title or detail.get("title") or "",
            "exam_unit": detail.get("unit_summary") or "",
            "exclude_tags": excl_tags_val,
            "fast_answer_key": fast_key_val,
            "stealth_mode": True,
        },
    )
    job.total = len(validated) + len(pre_skipped)
    job.skipped = list(pre_skipped)
    queue = get_queue()
    await queue.submit(job)

    return templates.TemplateResponse(
        request, "partials/exam_progress.html",
        {"job": job},
    )


@router.get("/{job_id}/progress", response_class=HTMLResponse)
def progress(request: Request, job_id: str, user: SessionUser = Depends(require_user)):
    """진행률 partial — HTMX 폴링용."""
    queue = get_queue()
    job = queue.get(job_id)
    if not job:
        return HTMLResponse(
            '<div class="bg-slate-800 border border-slate-700 rounded-xl p-4 text-slate-400">작업을 찾을 수 없습니다.</div>',
            status_code=200,
        )
    return templates.TemplateResponse(request, "partials/exam_progress.html", {"job": job})


@router.get("/{job_id}/download")
def download(job_id: str, user: SessionUser = Depends(require_user)):
    queue = get_queue()
    job = queue.get(job_id)
    if not job or not job.result_path:
        raise HTTPException(404, "결과 파일을 찾을 수 없습니다.")
    p = Path(job.result_path)
    if not p.exists():
        raise HTTPException(404, "파일이 만료되었거나 삭제되었습니다.")
    return FileResponse(
        path=str(p),
        filename=p.name,
        media_type="application/octet-stream",
    )
