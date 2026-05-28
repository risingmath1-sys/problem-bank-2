"""HTMX 페이지 라우트 — 로그인 / 홈 / partial."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from server import config
from server.auth_dep import get_optional_user, require_user, SessionUser
from server.services.engine import get_engine

SOURCES = ["NAESIN_A", "NAESIN_N", "SUNEUNG_SPECIAL", "SUNEUNG_COMPLETE", "MOCK_EXAM"]
SOURCE_LABELS = {
    "NAESIN_A": "내신기출 A",
    "NAESIN_N": "내신기출 B",
    "SUNEUNG_SPECIAL": "수능특강",
    "SUNEUNG_COMPLETE": "수능완성",
    "MOCK_EXAM": "모의고사",
}

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: SessionUser = Depends(get_optional_user)):
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/", response_class=HTMLResponse)
def home(request: Request, user: SessionUser = Depends(get_optional_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    # 홈 진입 = 한 작업 사이클 종료 의미. [마침]/[닫기] 등에서 home 으로 돌아올 때
    # 미저장 draft 가 살아 있으면 다음 [랜덤출제] 시 누적됨 → 여기서 한 번 더 정리.
    from server.services import exam_session
    exam_session.reset_draft(user.uid)
    return templates.TemplateResponse(
        request, "home.html",
        {"user": user},
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, user: SessionUser = Depends(get_optional_user)):
    """사용자 관리 (admin 전용). 로컬 main_gui.py:6950+ 동등."""
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user},
    )


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: SessionUser = Depends(get_optional_user)):
    """문제 등록 (admin 전용) — 6개 소스 카드. 로컬 main_gui.py:430-520 동등."""
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request, "register.html",
        {"user": user},
    )


@router.get("/register/{source}", response_class=HTMLResponse)
def register_source_page(
    request: Request, source: str,
    user: SessionUser = Depends(get_optional_user),
):
    """소스 선택 후 폼 — 로컬 main_gui.py:551-709 _build_reg_form 동등.

    HWP COM 인덱싱은 서버 워커 직렬화 필요 — 현재는 admin 데스크탑(.exe) 권장 안내.
    """
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse("/", status_code=302)
    valid = {"NAESIN_A", "NAESIN_N", "SUNEUNG_SPECIAL", "SUNEUNG_COMPLETE", "MOCK_EXAM", "TEXTBOOK"}
    if source not in valid:
        return RedirectResponse("/register", status_code=302)
    return templates.TemplateResponse(
        request, "register_form.html",
        {"user": user, "source": source, "source_label": SOURCE_LABELS.get(source, source)},
    )


@router.get("/partial/stats", response_class=HTMLResponse)
def partial_stats(request: Request, user: SessionUser = Depends(require_user)):
    """홈 통계 카드 HTML 조각."""
    engine = get_engine()
    by_source = [
        {"key": src, "label": SOURCE_LABELS[src], "count": engine.query_counts({"source": src})}
        for src in SOURCES
    ]
    total = sum(s["count"] for s in by_source)
    return templates.TemplateResponse(
        request, "partials/stats.html",
        {"user": user, "total": total, "by_source": by_source},
    )


@router.get("/partial/source_folder", response_class=HTMLResponse)
def partial_source_folder(request: Request, user: SessionUser = Depends(require_user)):
    """원본 HWP 폴더 경로 표시 + (admin) 변경 form. 로컬 main_gui.py:287-302 동등."""
    if user.role != "admin":
        return HTMLResponse('<div class="text-xs text-slate-500">관리자 전용</div>')
    import os
    cur = str(config.HWP_SOURCE_ROOT)
    exists = os.path.isdir(cur)
    env_lock = bool(os.environ.get("NAEGIWANGBANK_HWP_SOURCE_DIR"))
    return templates.TemplateResponse(
        request, "partials/source_folder.html",
        {"current": cur, "exists": exists, "env_lock": env_lock},
    )


@router.post("/api/source_folder", response_class=HTMLResponse)
async def update_source_folder(
    request: Request,
    new_path: str = Form(...),
    user: SessionUser = Depends(require_user),
):
    """admin: settings.json 의 source_hwp_dir 갱신 + 메모리 reload."""
    if user.role != "admin":
        return HTMLResponse(
            '<div class="text-rose-300 text-xs">관리자 권한이 필요합니다.</div>',
            status_code=403,
        )
    import os, json
    new_path = (new_path or "").strip()
    if not new_path:
        return HTMLResponse(
            '<div class="text-amber-300 text-xs">경로를 입력해주세요.</div>',
            status_code=200,
        )
    if os.environ.get("NAEGIWANGBANK_HWP_SOURCE_DIR"):
        return HTMLResponse(
            '<div class="text-amber-300 text-xs">환경변수로 고정된 경로는 변경 불가. NAEGIWANGBANK_HWP_SOURCE_DIR 해제 후 재시도.</div>',
        )
    settings_path = config.BASE_DIR / "settings.json"
    data = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
    data["source_hwp_dir"] = new_path
    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return HTMLResponse(f'<div class="text-rose-300 text-xs">저장 실패: {e}</div>')
    # in-memory 갱신
    from pathlib import Path as _P
    config.HWP_SOURCE_ROOT = _P(new_path)
    # 변경 후 partial 다시 렌더
    return partial_source_folder(request, user)


# ─────────── 랜덤 출제 ───────────
import json
from typing import Optional, List
from fastapi import Form

DIFFICULTY_CODES = [("A", "최상"), ("B", "상"), ("C", "중"), ("D", "하")]


def _load_units():
    path = config.BASE_DIR / "backend" / "unit_hierarchy.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _build_unit_categories():
    """로컬 _refresh_unit_tree 와 동일한 4-level 구조를 빌드해 dict 로 반환.

    구조:
      [{ name, subjects: [{ name, total, large_units: [{ code, name, total, version,
         medium_units: [{ code, name, count }] }] }] }]
    """
    from server.services.unit_counts import compute_unit_counts

    units = _load_units()
    counts = compute_unit_counts({})

    categories = []

    # ── 고등수학 (2022 개정 only — 로컬과 동일) ──
    high = {"name": "고등수학", "subjects": []}
    for subj in units.get("2022", []):
        subj_node = {
            "name": f"{subj['subject']} (2022개정)",
            "total": 0,
            "large_units": [],
        }
        for large in subj.get("large_units", []):
            lu = {
                "code": large["code"],
                "name": large["name"],
                "version": "2022",
                "total": 0,
                "medium_units": [],
            }
            for medium in large.get("medium_units", []):
                c = counts.get(medium["code"], 0)
                lu["medium_units"].append({
                    "code": medium["code"],
                    "name": medium["name"],
                    "count": c,
                })
                lu["total"] += c
            subj_node["large_units"].append(lu)
            subj_node["total"] += lu["total"]
        high["subjects"].append(subj_node)
    categories.append(high)

    # ── 중등수학 (있을 때만) ──
    if "middle" in units:
        mid = {"name": "중등수학", "subjects": []}
        for subj in units["middle"]:
            subj_node = {
                "name": subj["subject"],
                "total": 0,
                "large_units": [],
            }
            for large in subj.get("large_units", []):
                lu = {
                    "code": large["code"],
                    "name": large["name"],
                    "version": "middle",
                    "total": 0,
                    "medium_units": [],
                }
                for medium in large.get("medium_units", []):
                    c = counts.get(medium["code"], 0)
                    lu["medium_units"].append({
                        "code": medium["code"],
                        "name": medium["name"],
                        "count": c,
                    })
                    lu["total"] += c
                subj_node["large_units"].append(lu)
                subj_node["total"] += lu["total"]
            mid["subjects"].append(subj_node)
        categories.append(mid)

    return categories


@router.get("/random", response_class=HTMLResponse)
def random_exam_page(request: Request, user: SessionUser = Depends(get_optional_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    # 새 출제 진입 = 이전 세션 종료 의미. 누적된 draft (문항/필터/정렬옵션 등) 전부 정리.
    # (last_sort_options 만은 reset_draft 안에서 이월됨 — 사용자 취향 보존)
    # 랜덤추가 경로는 /partial/random/step3_to_step2 라 이 가드를 거치지 않음 → draft 유지.
    from server.services import exam_session
    exam_session.reset_draft(user.uid)
    return templates.TemplateResponse(
        request, "random_exam.html",
        {
            "user": user,
            "categories": _build_unit_categories(),
        },
    )


def _parse_units_form(raw_list):
    """체크박스 value `type:code:version` 리스트 → [{type,code,version}] 정규화."""
    out = []
    for s in raw_list or []:
        parts = (s or "").split(":")
        if len(parts) == 3 and parts[0] in ("large", "medium"):
            out.append({"type": parts[0], "code": parts[1], "version": parts[2]})
    return out


def _find_unit_name(code, version):
    """로컬 _find_unit_name (main_gui.py:3384) 포팅."""
    units = _load_units()
    for subj in units.get(version, []) if version else []:
        for large in subj.get("large_units", []):
            if large["code"] == code:
                return large["name"]
            for medium in large.get("medium_units", []):
                if medium["code"] == code:
                    return medium["name"]
    # version 미지정 fallback — 모든 버전 검색
    for v in units:
        for subj in units.get(v, []):
            for large in subj.get("large_units", []):
                if large["code"] == code:
                    return large["name"]
                for medium in large.get("medium_units", []):
                    if medium["code"] == code:
                        return medium["name"]
    return code


def _get_medium_codes_for_large(large_code, version):
    """로컬 _get_medium_codes_for_large (main_gui.py:3397) 포팅."""
    units = _load_units()
    for subj in units.get(version, []):
        for large in subj.get("large_units", []):
            if large["code"] == large_code:
                return [m["code"] for m in large.get("medium_units", [])]
    return []


DIFFICULTY_LABELS = {"A": "최상", "B": "상", "C": "중", "D": "하"}
TYPE_LABELS = {"0": "객관식", "1": "주관식"}
DEFAULT_SOURCES = ["NAESIN_A", "NAESIN_N", "SUNEUNG_SPECIAL", "SUNEUNG_COMPLETE", "MOCK_EXAM"]
ALL_PREFS = [("Good", "Good"), ("Soso", "Soso"), ("Bad", "Bad")]


def _get_pref_filter_ids(filter_state, current_user_id):
    """로컬 _get_pref_filter_ids (main_gui.py:1859) 포팅.

    None → 필터 비활성 (전체).
    set()  → 필터 활성이지만 매칭 0건.
    set 매칭 ID → 필터 활성, 매칭된 problem_id 집합.
    """
    if not filter_state.get("pref_filter_on"):
        return None
    selected_prefs = filter_state.get("active_prefs") or []
    if not selected_prefs:
        return set()
    scope = filter_state.get("pref_scope") or "mine"
    engine = get_engine()
    if scope == "mine":
        user_ids = [current_user_id]
    else:
        user_ids = list(engine.get_all_preference_user_ids() or [])
        if current_user_id not in user_ids:
            user_ids.append(current_user_id)
    if "Soso" in selected_prefs:
        candidate_ids = engine.get_all_problem_ids()
    else:
        candidate_ids = None
    return engine.get_problem_ids_by_preference(user_ids, selected_prefs, candidate_ids=candidate_ids)


def _get_rate_filter_ids(filter_state):
    """정답률 필터 → 매칭 problem id set. None=비활성."""
    if not filter_state.get("rate_use"):
        return None
    try:
        mn = float(filter_state.get("rate_min") or 0)
        mx = float(filter_state.get("rate_max") or 100)
    except (TypeError, ValueError):
        return None
    if mn < 0 or mx > 100 or mn > mx:
        return None
    engine = get_engine()
    try:
        ids = engine.get_problem_ids_by_rate(mn / 100.0, mx / 100.0)
    except Exception as e:
        print(f"[rate filter] 실패: {e}")
        return set()
    return set(ids or [])


def _get_brand_filter_ids(filter_state):
    """모의고사 브랜드 필터 → 매칭되는 problem id set.
    None=비활성, set()=활성 but 0건, set=매칭 ids.
    """
    if not filter_state.get("brand_option_on"):
        return None
    brands = filter_state.get("active_brands") or []
    if not brands:
        return set()
    engine = get_engine()
    try:
        ids = engine.get_ids_by_mock_brands(brands)
    except Exception as e:
        print(f"[brand filter] 실패: {e}")
        return set()
    return set(ids or [])


def _parse_problem_numbers(text):
    """'30, 45 46' → [30, 45, 46]. 1~9999 범위 외 제외."""
    nums = []
    for part in (text or "").replace(",", " ").split():
        try:
            n = int(part)
            if 1 <= n <= 9999:
                nums.append(n)
        except ValueError:
            pass
    return nums


def _apply_year_filter(f: dict, filter_state):
    """년도 필터 → filter dict 에 반영. 활성 + 선택값 있을 때만."""
    if not filter_state.get("year_filter_on"):
        return
    years = filter_state.get("active_years") or []
    if not years:
        return
    mode = filter_state.get("year_mode") or "exclude"
    if mode == "include":
        f["year"] = {"in": years} if len(years) > 1 else years[0]
    else:  # exclude
        f["year"] = {"not_in": years}


def _row_query_count(engine, unit_codes_or_code, lvl_code, type_code, filter_state, pref_ids, brand_ids, rate_ids,
                     oneshot_excluded_ids=None):
    """로컬 _query_count_for_row (main_gui.py:3299) 의 R-2~R-7 범위 포팅.
    oneshot_excluded_ids: 제외설정 다이얼로그에서 체크된 시험지들의 문제 id set
    (로컬 main_gui.py:3378-3409 동등 — 가능 문제수에서 차감)."""
    f: dict = {}
    if isinstance(unit_codes_or_code, list):
        if not unit_codes_or_code:
            return 0
        f["unit_code"] = {"in": unit_codes_or_code} if len(unit_codes_or_code) > 1 else unit_codes_or_code[0]
    else:
        f["unit_code"] = unit_codes_or_code
    if lvl_code:
        f["difficulty"] = lvl_code
    if type_code == "0":
        f["problem_type"] = "객관식"
    elif type_code == "1":
        f["problem_type"] = {"in": ["주관식", "서술형", "단답형"]}
    sources = filter_state.get("sources_for_query")  # None=미적용, []=강제0, [..]=in
    if sources is not None:
        if not sources:
            return 0
        f["source"] = {"in": sources} if len(sources) > 1 else sources[0]
    _apply_year_filter(f, filter_state)
    # 학교 (R-7)
    if filter_state.get("school_option_on") and filter_state.get("active_schools"):
        f["school"] = {"in": filter_state["active_schools"]}
    # 문항번호 (R-7)
    if filter_state.get("pnum_option_on") and filter_state.get("active_problem_numbers"):
        f["problem_number"] = {"in": filter_state["active_problem_numbers"]}
    # 선호도 + 브랜드 + 정답률 — 모두 id 제약. 교집합으로 처리.
    id_constraint = None
    for ids in (pref_ids, brand_ids, rate_ids):
        if ids is None:
            continue
        s = set(ids)
        id_constraint = s if id_constraint is None else (id_constraint & s)
    # 일회성 제외 — id_constraint 있으면 set difference, 없으면 not_in 필터로 적용
    oneshot = set(oneshot_excluded_ids) if oneshot_excluded_ids else set()
    if id_constraint is not None:
        if oneshot:
            id_constraint = id_constraint - oneshot
        if not id_constraint:
            return 0
        _apply_id_constraint(f, engine, id_constraint)
    elif oneshot:
        f["id"] = {"not_in": list(oneshot)}
    include_excl = filter_state.get("include_excluded", False)
    try:
        result = engine.query_counts(f, include_excluded=include_excl)
    except TypeError:
        result = engine.query_counts(f)
    except Exception as e:
        print(f"[step2 row count] 실패: {e}")
        return 0
    # ⚠️ DEBUG (임시) — 0 반환 시 어떤 필터로 호출됐는지 추적
    if result == 0:
        f_dbg = {k: (f"<set:{len(v.get('in', []))}개>" if isinstance(v, dict) and 'in' in v and len(v.get('in', [])) > 100 else v) for k, v in f.items()}
        print(f"[step2 0건] filter={f_dbg} pref_ids={'None' if pref_ids is None else f'set({len(pref_ids)})'} include_excl={include_excl}")
    return result


def _build_step2_rows(selected, filter_state, current_user_id, initial_allocs=None):
    """선택 단원 리스트 → 좌측 테이블 행 리스트 + 합계.
    로컬 _refresh_step_2_list (main_gui.py:3196) 포팅.

    filter_state 는 _parse_filter_form 결과.
    initial_allocs 는 {alloc_<key>: value} dict — 매칭되는 key 의 행에 사전 채움 (랜덤추가 복원).
    """
    engine = get_engine()

    view_level = filter_state["view_level"]
    view_type = filter_state["view_type"]

    if view_level:
        target_levels = [(c, DIFFICULTY_LABELS[c])
                         for c in (filter_state["active_difficulties"] or [])
                         if c in DIFFICULTY_LABELS]
    else:
        target_levels = [(None, "전체")]
    if view_type:
        target_types = [(c, TYPE_LABELS[c])
                        for c in (filter_state["active_types"] or [])
                        if c in TYPE_LABELS]
    else:
        target_types = [(None, "전체")]

    pref_ids = _get_pref_filter_ids(filter_state, current_user_id)
    brand_ids = _get_brand_filter_ids(filter_state)
    rate_ids = _get_rate_filter_ids(filter_state)

    # 일회성 제외 (제외설정 다이얼로그) — 로컬 main_gui.py:3378 동등.
    # draft 에서 가져와 _row_query_count 로 전달 → 가능 문제수에서 차감.
    from server.services import exam_session
    draft = exam_session.get_draft(current_user_id)
    oneshot_excluded_ids = set(getattr(draft, "oneshot_excluded_problem_ids", set()) or set())

    rows = []
    total = 0
    for u in selected:
        code = u["code"]
        version = u["version"]
        u_type = u["type"]
        name = _find_unit_name(code, version)
        if u_type == "large":
            kids = _get_medium_codes_for_large(code, version)
            unit_filter = kids if kids else ["__NONE__"]
        else:
            unit_filter = code

        if not target_levels or not target_types:
            rows.append({
                "key": f"{u_type}_{code}_{version}__none__none",
                "unit_label": name,
                "is_large": u_type == "large",
                "level_label": "—" if not target_levels else "전체",
                "type_label": "—" if not target_types else "전체",
                "avail": 0,
                "disabled": True,
                "initial_qty": "0",
            })
            continue

        for lvl_code, lvl_name in target_levels:
            for type_code, type_name in target_types:
                avail = _row_query_count(engine, unit_filter, lvl_code, type_code,
                                         filter_state, pref_ids, brand_ids, rate_ids,
                                         oneshot_excluded_ids=oneshot_excluded_ids)
                key = f"{u_type}_{code}_{version}_{lvl_code or '_'}_{type_code or '_'}"
                init_val = "0"
                if initial_allocs:
                    raw = initial_allocs.get(f"alloc_{key}")
                    if raw not in (None, ""):
                        try:
                            n = int(raw)
                            if n > avail:
                                n = avail
                            if n < 0:
                                n = 0
                            init_val = str(n)
                        except (TypeError, ValueError):
                            init_val = "0"
                rows.append({
                    "key": key,
                    "unit_label": name,
                    "is_large": u_type == "large",
                    "level_label": lvl_name,
                    "type_label": type_name,
                    "avail": avail,
                    "disabled": False,
                    "initial_qty": init_val,
                })
                total += avail
    return rows, total


def _parse_filter_form(form):
    """form 에서 R-2~R-5 우측 메뉴 필터 값 추출.

    `filter_panel=1` hidden 마커가 있으면 폼이 패널에서 제출됐다는 뜻 →
      누락된 체크박스는 'unchecked' 로 취급.
    없으면 (Step 1 → 2 최초 진입) → 합리적 기본값 적용.
    """
    initialized = (form.get("filter_panel") or "") == "1"

    # 1. 소스
    if initialized:
        source_on = (form.get("source_filter_on") or "") == "1"
    else:
        source_on = True  # 초기 진입 → 소스 필터 ON (전체 체크)
    if initialized:
        src_active = form.getlist("sources") if source_on else []
    else:
        src_active = list(DEFAULT_SOURCES)
    if source_on:
        sources_for_query = list(src_active)  # 전부 해제 → [] (강제 0건)
    else:
        sources_for_query = None  # 비활성 → 필터 미적용

    # 2. 수준 (+ 정답률)
    view_level = initialized and (form.get("view_level") or "") == "1"
    diffs_active = form.getlist("difficulties") if view_level else list(DIFFICULTY_LABELS.keys())
    rate_use = initialized and (form.get("rate_use") or "") == "1"
    try:
        rate_min = int(form.get("rate_min") or 0)
    except ValueError:
        rate_min = 0
    try:
        rate_max = int(form.get("rate_max") or 100)
    except ValueError:
        rate_max = 100

    # 3. 형식
    view_type = initialized and (form.get("view_type") or "") == "1"
    types_active = form.getlist("types") if view_type else list(TYPE_LABELS.keys())

    # 4. 선호도
    # 로컬 동작: Good/Soso/Bad 모두 초기값 True (main_gui.py:108-110, 2700).
    # 첫 진입 시(initialized=False) 만 기본값으로 모두 체크 — 페이지에 그 상태로
    # 렌더링되어, 사용자가 "문항선호도" 마스터를 켜는 순간 form 에 자동 포함된다.
    # initialized=True 면 form 의 값 그대로 (사용자가 명시적으로 해제한 것 존중).
    pref_on = initialized and (form.get("pref_filter_on") or "") == "1"
    if initialized:
        prefs_active = form.getlist("prefs")
    else:
        prefs_active = ["Good", "Soso", "Bad"]
    pref_scope = form.get("pref_scope") or "mine"

    # 5. 년도
    year_on = initialized and (form.get("year_filter_on") or "") == "1"
    years_active = form.getlist("years") if year_on else []
    year_mode = form.get("year_mode") or "exclude"

    # 6. 출제 제외
    include_excluded = initialized and (form.get("include_excluded") or "") == "1"

    # 6.5. 최신기출 우선선택 — 로컬 메모리 메뉴 5번 (년도 필터 위)
    recent_first = initialized and (form.get("recent_first") or "") == "1"

    # 8. 상세 필터 (R-7)
    detail_open = (form.get("detail_open") or "") == "1"
    school_on = initialized and (form.get("school_option_on") or "") == "1"
    schools = form.getlist("schools") if school_on else []
    brand_on = initialized and (form.get("brand_option_on") or "") == "1"
    brands = form.getlist("brands") if brand_on else []
    pnum_on = initialized and (form.get("pnum_option_on") or "") == "1"
    pnum_text = form.get("pnum_text") or ""
    pnums = _parse_problem_numbers(pnum_text) if pnum_on else []

    return {
        "source_filter_on": source_on,
        "active_sources": src_active if source_on else DEFAULT_SOURCES,
        "sources_for_query": sources_for_query,
        "view_level": view_level,
        "active_difficulties": diffs_active,
        "rate_use": rate_use,
        "rate_min": rate_min,
        "rate_max": rate_max,
        "view_type": view_type,
        "active_types": types_active,
        "pref_filter_on": pref_on,
        "active_prefs": prefs_active,
        "pref_scope": pref_scope,
        "year_filter_on": year_on,
        "active_years": years_active,
        "year_mode": year_mode,
        "include_excluded": include_excluded,
        "recent_first": recent_first,
        "detail_open": detail_open,
        "school_option_on": school_on,
        "active_schools": schools,
        "brand_option_on": brand_on,
        "active_brands": brands,
        "pnum_option_on": pnum_on,
        "pnum_text": pnum_text,
        "active_problem_numbers": pnums,
    }


@router.post("/partial/random/step2", response_class=HTMLResponse)
async def partial_random_step2(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """Step 1 → Step 2: 선택된 단원들로 좌측 단원별 테이블 + 우측 메뉴 패널 렌더."""
    form = await request.form()
    selected = _parse_units_form(form.getlist("units"))
    if not selected:
        return HTMLResponse(
            '<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            '출제할 단원을 최소 하나 이상 선택해주세요.'
            '</div>'
        )
    f = _parse_filter_form(form)
    rows, total_avail = _build_step2_rows(selected, f, user.uid)
    units_payload = [f"{u['type']}:{u['code']}:{u['version']}" for u in selected]
    engine = get_engine()
    try:
        all_years = engine.get_unique_years() or []
    except Exception:
        all_years = []
    from server.services import exam_session
    draft = exam_session.get_draft(user.uid)
    return templates.TemplateResponse(
        request, "partials/random_step2.html",
        {
            "rows": rows,
            "total_avail": total_avail,
            "units_payload": units_payload,
            "filter_state": f,
            "DIFFICULTY_LABELS": DIFFICULTY_LABELS,
            "TYPE_LABELS": TYPE_LABELS,
            "SOURCE_LABELS": SOURCE_LABELS,
            "ALL_SOURCES": DEFAULT_SOURCES,
            "ALL_PREFS": ALL_PREFS,
            "ALL_YEARS": all_years,
            "existing_count": draft.total,
        },
    )


@router.get("/partial/random/exclusion_dialog", response_class=HTMLResponse)
def partial_random_exclusion_dialog(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """제외설정 다이얼로그 — 로컬 ExclusionSettingDialog (main_gui.py:7581) 동등.
    Lazy load: 폴더 트리만 미리 로드. 시험지/문항 카운트는 폴더 클릭 시 fetch.
    """
    engine = get_engine()
    folders = engine.get_folders(user.uid) or []
    folder_tree = _build_folder_tree(folders)

    from server.services import exam_session
    draft = exam_session.get_draft(user.uid)
    selected_tids = set(getattr(draft, "oneshot_excluded_test_ids", set()) or set())

    return templates.TemplateResponse(
        request, "partials/random_exclusion_dialog.html",
        {
            "folder_tree": folder_tree,
            "selected_tids": selected_tids,
        },
    )


@router.get("/partial/random/exclusion_folder/{fid}", response_class=HTMLResponse)
def partial_random_exclusion_folder(
    request: Request,
    fid: str,
    user: SessionUser = Depends(require_user),
):
    """폴더 body lazy fetch — 그 폴더의 시험지 + 자식 폴더 헤더만.
    fid='root' → directory_id=None (최상위)."""
    engine = get_engine()
    if fid == "root":
        directory_id = None
    else:
        try:
            directory_id = int(fid)
        except (TypeError, ValueError):
            directory_id = fid  # 비숫자 ID 도 허용 (Firestore string id 대응)
    tests = engine.get_tests(directory_id=directory_id, user_id=user.uid) or []

    test_pid_count: dict = {}
    for t in tests:
        test_pid_count[t["id"]] = len(_test_problem_ids(engine, t["id"], user.uid))

    children: list = []
    if fid != "root":
        all_folders = engine.get_folders(user.uid) or []
        children = [f for f in all_folders if f.get("parent_id") == directory_id]
        children.sort(key=lambda x: x.get("id") or 0)

    from server.services import exam_session
    draft = exam_session.get_draft(user.uid)
    selected_tids = set(getattr(draft, "oneshot_excluded_test_ids", set()) or set())

    return templates.TemplateResponse(
        request, "partials/random_exclusion_folder_body.html",
        {
            "tests": tests,
            "test_pid_count": test_pid_count,
            "children": children,
            "selected_tids": selected_tids,
        },
    )


def _walk_folder_nodes(tree):
    """폴더 트리 평면 순회."""
    for n in tree:
        yield n
        for sub in _walk_folder_nodes(n.get("children") or []):
            yield sub


def _test_problem_ids(engine, tid, uid) -> list:
    """saved_test 의 problem_ids 캐시 (다이얼로그 1회용)."""
    try:
        detail = engine.get_test_detail(tid, uid) or {}
        return [p.get("id") for p in (detail.get("problems") or []) if p.get("id")]
    except Exception:
        return []


@router.post("/partial/random/exclusion_apply", response_class=HTMLResponse)
async def partial_random_exclusion_apply(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """제외설정 적용 — 체크된 시험지의 problem_ids 를 oneshot 제외 set 에 저장."""
    from server.services import exam_session
    form = await request.form()
    selected_tids = [int(x) for x in form.getlist("excl_tid") if x.isdigit()]
    engine = get_engine()
    pids = set()
    for tid in selected_tids:
        pids.update(_test_problem_ids(engine, tid, user.uid))
    draft = exam_session.get_draft(user.uid)
    # ensure attrs exist
    if not hasattr(draft, "oneshot_excluded_test_ids"):
        draft.oneshot_excluded_test_ids = set()
    if not hasattr(draft, "oneshot_excluded_problem_ids"):
        draft.oneshot_excluded_problem_ids = set()
    draft.oneshot_excluded_test_ids = set(selected_tids)
    draft.oneshot_excluded_problem_ids = pids
    # 로컬 _apply (main_gui.py:7735) 동등:
    #  1) 저장 (완료)
    #  2) 다이얼로그 자동 닫힘 → closeExclDialog 이벤트
    #  3) step2 테이블 자동 갱신 → step2Refresh 이벤트
    # comma-separated 형식 — JSON 객체보다 호환성 ↑
    return HTMLResponse(
        content=(
            f'<div class="bg-emerald-900/40 border border-emerald-700 text-emerald-200 rounded-xl p-3 text-sm">'
            f'✓ {len(selected_tids)}개 시험지 / {len(pids)}문항이 이번 출제에서 제외됩니다.</div>'
        ),
        headers={"HX-Trigger": "step2Refresh, closeExclDialog"},
    )


@router.get("/partial/random/school_search", response_class=HTMLResponse)
def partial_random_school_search(
    request: Request,
    q: Optional[str] = None,
    user: SessionUser = Depends(require_user),
):
    """학교명 검색 → 결과 버튼 리스트 (클릭 시 JS 가 태그로 추가)."""
    keyword = (q or "").strip()
    if not keyword:
        return HTMLResponse('<div class="text-xs text-slate-500">검색어를 입력하세요.</div>')
    engine = get_engine()
    try:
        results = engine.search_schools(keyword) or []
    except Exception as e:
        return HTMLResponse(
            f'<div class="text-xs text-rose-400">검색 실패: {e}</div>'
        )
    if not results:
        return HTMLResponse('<div class="text-xs text-slate-500">결과 없음</div>')
    return templates.TemplateResponse(
        request, "partials/random_school_results.html",
        {"schools": results},
    )


@router.post("/partial/random/step2_table", response_class=HTMLResponse)
async def partial_random_step2_table(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """우측 필터 변경 시 좌측 테이블만 재렌더 (HTMX outerHTML swap)."""
    form = await request.form()
    selected = _parse_units_form(form.getlist("units"))
    f = _parse_filter_form(form)
    rows, total_avail = _build_step2_rows(selected, f, user.uid)
    return templates.TemplateResponse(
        request, "partials/random_step2_table.html",
        {"rows": rows, "total_avail": total_avail},
    )


# ─────────── Step 3 (출제 문항 확인) ───────────
LEVEL_LABEL = {"A": "최상", "B": "상", "C": "중", "D": "하"}


def _step3_row(no: int, p: dict) -> dict:
    """Step 3 표시용 1행 가공 — 로컬 _refresh_step_3_list (main_gui.py:3932) 포팅."""
    fname = (p.get("file_name") or "").replace(".hwp", "").replace(".HWP", "")
    num = p.get("endnote_index") or "?"
    source_str = f"{fname}  {num}번"
    unit_val = (p.get("middle_unit") or "").strip()
    unit_code = p.get("unit_code") or ""
    if not unit_val or unit_val == unit_code:
        if unit_code:
            curr = p.get("curriculum") or ""
            mapped = p.get("mapped_unit_code") or ""
            if mapped:
                version = "2022"
            elif "2015" in curr:
                version = "2015"
            elif "2022" in curr:
                version = "2022"
            else:
                version = ""
            found = _find_unit_name(unit_code, version)
            if found and found != unit_code:
                unit_val = found
    lvl_code = p.get("difficulty") or ""
    return {
        "no": no,
        "id": str(p.get("id") or ""),
        "source_str": source_str,
        "unit_name": unit_val or unit_code or "-",
        "level": LEVEL_LABEL.get(lvl_code, lvl_code or "-"),
        "ptype": p.get("problem_type") or "-",
    }


def _render_step3(request: Request, user_id: str):
    """draft → step3 partial."""
    from server.services import exam_session
    draft = exam_session.get_draft(user_id)
    rows = []
    no = 1
    for batch in draft.batches:
        for p in batch:
            rows.append(_step3_row(no, p))
            no += 1
    return templates.TemplateResponse(
        request, "partials/random_step3_preview.html",
        {
            "draft": draft,
            "rows": rows,
            "skipped_count": len(draft.pre_skipped or []),
        },
    )


@router.post("/partial/random/step3_remove", response_class=HTMLResponse)
async def partial_random_step3_remove(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """행 [삭제] 클릭 — 문제 1건 제거 후 step3 재렌더."""
    from server.services import exam_session
    form = await request.form()
    pid = (form.get("problem_id") or "").strip()
    if pid:
        draft = exam_session.get_draft(user.uid)
        draft.remove_problem(pid)
    return _render_step3(request, user.uid)


@router.post("/partial/random/step3_sort", response_class=HTMLResponse)
async def partial_random_step3_sort(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """순서정렬 다이얼로그 [확인] — sort_p1/p2/p3 기준 정렬, 기존 batch 통합."""
    from server.services import exam_session
    form = await request.form()
    draft = exam_session.get_draft(user.uid)
    # 다이얼로그 재오픈 시 직전 옵션 보존 — 정렬 적용 여부와 무관하게 저장.
    opts: dict = {}
    for i in (1, 2, 3):
        opts[f"sort_p{i}"] = form.get(f"sort_p{i}") or "(없음)"
        opts[f"sort_p{i}_rev"] = "1" if form.get(f"sort_p{i}_rev") else ""
    draft.last_sort_options = opts
    flat = draft.all_problems
    if not flat:
        return _render_step3(request, user.uid)
    sorted_flat = _apply_problem_sort(flat, form)
    draft.apply_sort(sorted_flat)
    return _render_step3(request, user.uid)


@router.post("/partial/random/step3_undo_sort", response_class=HTMLResponse)
async def partial_random_step3_undo_sort(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """정렬 취소 — 직전 batch 구조 복원."""
    from server.services import exam_session
    draft = exam_session.get_draft(user.uid)
    draft.undo_sort()
    return _render_step3(request, user.uid)


@router.post("/partial/random/step3_pop_last", response_class=HTMLResponse)
async def partial_random_step3_pop_last(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """[이전] — 마지막 batch (직전 추가분) 제거. batches 비면 step1 으로 redirect."""
    from server.services import exam_session
    draft = exam_session.get_draft(user.uid)
    draft.pop_last_batch()
    if draft.total == 0:
        # 모든 batch 가 사라짐 → step1 으로
        exam_session.reset_draft(user.uid)
        return HTMLResponse(
            '<div id="random-root" hx-get="/random" hx-trigger="load" hx-swap="outerHTML"></div>'
        )
    return _render_step3(request, user.uid)


@router.get("/partial/random/step4", response_class=HTMLResponse)
def partial_random_step4(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """Step 3 [다음] → Step 4 (시험지 저장 및 출제). 로컬 main_gui.py:4185 동등.
    헤더: [테스트저장] [테스트출제] [이전] [마침]
    좌측: 내 시험지 보관함 (폴더 + 시험지 트리, 클릭 시 draft 교체)
    우측: 현재 작업 중 시험지 미리보기 (제목/요약/문항 리스트)
    """
    from server.services import exam_session
    draft = exam_session.get_draft(user.uid)
    if draft.total == 0:
        return HTMLResponse(
            '<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            '출제할 문항이 없습니다. <a href="/random" class="underline">처음부터</a></div>'
        )

    engine = get_engine()
    folders = engine.get_folders(user.uid) or []
    folder_tree = _build_folder_tree(folders)
    root_tests = engine.get_tests(directory_id=None, user_id=user.uid) or []

    rows = []
    no = 1
    for batch in draft.batches:
        for p in batch:
            rows.append(_step3_row(no, p))
            no += 1

    # 자동 단원 요약 — 로컬 동등
    units_set = {p.get("middle_unit") or "" for p in draft.all_problems if p.get("middle_unit")}
    units_set = {u for u in units_set if u}
    if len(units_set) > 1:
        unit_summary_auto = f"{next(iter(units_set))} 외 {len(units_set)-1}개"
    elif units_set:
        unit_summary_auto = next(iter(units_set))
    else:
        unit_summary_auto = "(자동요약)"

    return templates.TemplateResponse(
        request, "partials/random_step4.html",
        {
            "draft": draft,
            "rows": rows,
            "folder_tree": folder_tree,
            "root_tests": root_tests,
            "unit_summary_auto": unit_summary_auto,
            "saved_exam_title": draft.exam_title or "",
            "engine": engine,
            "user_uid": user.uid,
        },
    )


@router.get("/partial/random/step4_explorer", response_class=HTMLResponse)
def partial_random_step4_explorer(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """Step 4 좌측 시험지 보관함 — 폴더 신규 생성 후 갱신용."""
    engine = get_engine()
    folders = engine.get_folders(user.uid) or []
    folder_tree = _build_folder_tree(folders)
    root_tests = engine.get_tests(directory_id=None, user_id=user.uid) or []
    return templates.TemplateResponse(
        request, "partials/random_step4_explorer.html",
        {"folder_tree": folder_tree, "root_tests": root_tests, "engine": engine, "user_uid": user.uid},
    )


@router.post("/partial/random/step4_back_to_step3", response_class=HTMLResponse)
def partial_random_step4_back_to_step3(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """Step 4 [이전] — Step 3 (출제 문항 확인) 화면 복귀. draft 그대로."""
    return _render_step3(request, user.uid)


@router.post("/partial/random/step4_load_test/{tid}", response_class=HTMLResponse)
def partial_random_step4_load_test(
    request: Request,
    tid: int,
    user: SessionUser = Depends(require_user),
):
    """Step 4 좌측 시험지 클릭 → 그 시험지의 문항으로 draft 교체.
    로컬 _on_step4_folder_select (main_gui.py:4311) 동등.
    """
    from server.services import exam_session
    engine = get_engine()
    detail = engine.get_test_detail(tid, user.uid)
    if not detail or not detail.get("problems"):
        return HTMLResponse(
            '<div id="random-root" class="bg-rose-900/40 border border-rose-700 text-rose-200 rounded-xl p-4">'
            '시험지를 찾을 수 없거나 권한이 없습니다.</div>'
        )
    draft = exam_session.get_draft(user.uid)
    draft.reset()
    draft.append_batch(list(detail["problems"]))
    draft.exam_title = detail.get("title") or ""
    # Step 4 화면 다시 렌더 (보관함 + 미리보기 갱신)
    return partial_random_step4(request, user)


@router.get("/partial/random/step3_to_step1", response_class=HTMLResponse)
def partial_random_step3_to_step1(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """[랜덤추가 fallback] — Step 1 (단원 선택) 으로 복귀.
    이전 필터 백업이 없을 때만 사용. draft 유지 → 다음 출제는 append_mode 자동.
    """
    from server.services import exam_session
    draft = exam_session.get_draft(user.uid)

    categories = _build_unit_categories()
    return templates.TemplateResponse(
        request, "random_exam.html",
        {
            "user": user,
            "categories": categories,
            "append_existing_count": draft.total,
        },
    )


@router.get("/partial/random/step3_to_step2", response_class=HTMLResponse)
def partial_random_step3_to_step2(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """[랜덤추가] — Step 2 로 직행 + 이전 필터/단원/alloc 전부 복원.
    로컬 _on_random_add_click (main_gui.py:4024) 동등.

    백업이 없으면 (예외 케이스) Step 1 으로 fallback.
    """
    from starlette.datastructures import FormData
    from server.services import exam_session

    draft = exam_session.get_draft(user.uid)
    if not draft.last_form_items:
        return partial_random_step3_to_step1(request, user)

    saved = FormData(draft.last_form_items)
    selected = _parse_units_form(saved.getlist("units"))
    if not selected:
        return partial_random_step3_to_step1(request, user)

    f = _parse_filter_form(saved)
    initial_allocs = {k: v for k, v in draft.last_form_items if k.startswith("alloc_")}
    rows, total_avail = _build_step2_rows(selected, f, user.uid, initial_allocs=initial_allocs)
    units_payload = [f"{u['type']}:{u['code']}:{u['version']}" for u in selected]
    engine = get_engine()
    try:
        all_years = engine.get_unique_years() or []
    except Exception:
        all_years = []
    return templates.TemplateResponse(
        request, "partials/random_step2.html",
        {
            "rows": rows,
            "total_avail": total_avail,
            "units_payload": units_payload,
            "filter_state": f,
            "DIFFICULTY_LABELS": DIFFICULTY_LABELS,
            "TYPE_LABELS": TYPE_LABELS,
            "SOURCE_LABELS": SOURCE_LABELS,
            "ALL_SOURCES": DEFAULT_SOURCES,
            "ALL_PREFS": ALL_PREFS,
            "ALL_YEARS": all_years,
            "existing_count": draft.total,
        },
    )


def _build_filters(
    sources: List[str],
    unit_codes: List[str],
    difficulties: List[str],
    problem_type: Optional[str],
    school: Optional[str],
    year: Optional[str],
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


@router.post("/partial/random/preview", response_class=HTMLResponse)
def partial_random_preview(
    request: Request,
    sources: List[str] = Form(default_factory=list),
    unit_codes: List[str] = Form(default_factory=list),
    difficulties: List[str] = Form(default_factory=list),
    problem_type: Optional[str] = Form(None),
    school: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    user: SessionUser = Depends(require_user),
):
    """필터로 매칭되는 후보 문제 수만 반환."""
    engine = get_engine()
    filters = _build_filters(sources, unit_codes, difficulties, problem_type, school, year)
    count = engine.query_counts(filters) if filters else 0
    return templates.TemplateResponse(
        request, "partials/random_preview.html",
        {"count": count, "has_filter": bool(filters)},
    )


# ─────────── 원본 출제 ───────────
def _load_curriculum_subjects() -> dict:
    """{교육과정명: [과목, ...]} 로드."""
    path = config.BASE_DIR / "backend" / "curriculum_config.json"
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    out = {}
    for name, body in (data.get("curriculums") or {}).items():
        out[name] = body.get("subjects") or []
    return out


@router.get("/original", response_class=HTMLResponse)
def original_exam_page(request: Request, user: SessionUser = Depends(get_optional_user)):
    import traceback
    try:
        if not user:
            return RedirectResponse("/login", status_code=302)
        print(f"[ORIG-DEBUG] user={user!r}", flush=True)
        curriculums = _load_curriculum_subjects()
        print(f"[ORIG-DEBUG] curriculums keys={list(curriculums.keys())}", flush=True)
        engine = get_engine()
        try:
            all_years = engine.get_unique_years() or []
        except Exception as e:
            print(f"[YEAR-DEBUG] get_unique_years FAILED: {e!r}", flush=True)
            traceback.print_exc()
            all_years = []
        print(f"[ORIG-DEBUG] /original all_years count={len(all_years)} sample={list(all_years)[:5]}", flush=True)
        try:
            return templates.TemplateResponse(
                request, "original_exam.html",
                {
                    "user": user,
                    "sources": [(s, SOURCE_LABELS[s]) for s in SOURCES],
                    "curriculums": curriculums,
                    "curriculum_names": list(curriculums.keys()),
                    "all_years": all_years,
                },
            )
        except Exception as e:
            print(f"[ORIG-DEBUG] template render FAILED: {e!r}", flush=True)
            traceback.print_exc()
            raise
    except Exception as e:
        print(f"[ORIG-DEBUG] OUTER FAILED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        raise


def _build_unit_order_map() -> dict:
    """unit_code → 글로벌 정렬 인덱스 (2022 → 2015 순회 기준)."""
    out: dict = {}
    try:
        units = _load_units()
    except Exception:
        return out
    idx = 0
    seen = set()
    for ver in ("2022", "2015"):
        for subj in units.get(ver, []):
            for lu in subj.get("large_units", []):
                for mu in lu.get("medium_units", []):
                    code = mu.get("code") or ""
                    if code and code not in seen:
                        seen.add(code)
                        out[code] = idx
                        idx += 1
    return out


def _apply_problem_sort(problems: list, form) -> list:
    """sort_p1/sort_p2/sort_p3 (+ _rev 플래그) 기준으로 stable sort.
    main_gui.py:3802 _apply_sort 포팅. P3 → P2 → P1 순으로 stable 적용."""
    if not problems:
        return problems
    criteria = []
    for i in (1, 2, 3):
        kt = (form.get(f"sort_p{i}") or "").strip()
        if not kt or kt == "(없음)":
            continue
        rev = (form.get(f"sort_p{i}_rev") or "") == "1"
        criteria.append((kt, rev))
    if not criteria:
        return problems

    import random
    items = list(problems)
    for p in items:
        p["_rand_key"] = random.random()

    unit_order = _build_unit_order_map()
    LEVEL = {"D": 0, "하": 0, "C": 1, "중": 1, "B": 2, "상": 2, "A": 3, "최상": 3}
    TYPE = {"객관식": 0, "단답형": 1, "서답형": 2, "주관식": 2, "서술형": 2}

    for kt, rev in reversed(criteria):
        if kt == "무작위":
            items.sort(key=lambda p: p["_rand_key"])
        elif kt == "단원순":
            items.sort(key=lambda p: unit_order.get(p.get("unit_code") or "", 999999), reverse=rev)
        elif kt == "수준순":
            items.sort(key=lambda p: LEVEL.get(p.get("difficulty"), 1), reverse=rev)
        elif kt == "형식순":
            items.sort(key=lambda p: TYPE.get(p.get("problem_type"), 3), reverse=rev)

    for p in items:
        p.pop("_rand_key", None)
    return items


def _ordered_units_for_subject(subject: str) -> list:
    """과목명으로 교육과정 순서대로 정렬된 중단원 리스트 반환.
    [{"code": ..., "name": ...}, ...] — 2022 → 2015 순서로 탐색.
    main_gui.py:924 _get_ordered_units_for_subject 포팅."""
    if not subject:
        return []
    try:
        units = _load_units()
    except Exception:
        return []
    for version in ("2022", "2015"):
        for subj_data in units.get(version, []):
            if subj_data.get("subject") == subject:
                out = []
                for large in subj_data.get("large_units", []):
                    for medium in large.get("medium_units", []):
                        out.append({"code": medium["code"], "name": medium["name"]})
                return out
    return []


@router.get("/partial/original/units_for_subject", response_class=HTMLResponse)
def partial_units_for_subject(
    request: Request,
    subject: str = "",
    user: SessionUser = Depends(require_user),
):
    """과목 선택 시 시험범위 unit_start/unit_end 드롭다운 옵션 갱신용."""
    units = _ordered_units_for_subject(subject)
    opts_html = '<option value=""></option>' + "".join(
        f'<option value="{u["name"]}">{u["name"]}</option>' for u in units
    )
    return HTMLResponse(opts_html)


def _diff_badge_for_score(score: int, th10: int, th30: int, th60: int) -> str:
    s = score or 0
    if s >= th10 and th10 > 0: return "최상"
    if s >= th30 and th30 > 0: return "상"
    if s >= th60 and th60 > 0: return "중"
    return "하"


def _apply_id_constraint(f: dict, engine, id_set):
    """f["id"] 에 IN/NOT IN 자동 선택 — SQLite IN 절 변수 한도(~32K) 초과 회피.
    id_set 이 매우 클 때 보완 집합(NOT IN) 으로 변환.
    id_set 빈 set 이면 caller 가 '__NONE__' 등으로 처리.
    """
    SQL_VAR_LIMIT = 900
    if not id_set:
        return False  # caller 가 직접 처리
    if len(id_set) <= SQL_VAR_LIMIT:
        f["id"] = {"in": list(id_set)}
        return True
    try:
        all_ids = set(engine.get_all_problem_ids())
    except Exception:
        all_ids = set()
    excluded = all_ids - id_set
    if not excluded:
        return True  # 사실상 전체 = 필터 안 검
    if len(excluded) <= SQL_VAR_LIMIT:
        f["id"] = {"not_in": list(excluded)}
        return True
    print(f"[id_constraint] 양쪽 다 큼 |in|={len(id_set)} |excl|={len(excluded)} → 필터 미적용")
    return True


def _get_diff_counts_for_files(engine, file_names):
    """주어진 file_name 리스트에 대해 file_name별 (a,b,c,d) 카운트.
    중등용 점수 = A×3 + B×2 + C×1 계산에 사용.
    FirestoreEngine 인 경우 cache_engine.db_path, LocalDBEngine 인 경우 engine.db_path.
    로컬(backend/) 코드는 건드리지 않고 서버 측에서만 캐시 SQLite 를 직접 조회.
    """
    if not file_names:
        return {}
    import sqlite3
    target = getattr(engine, "cache_engine", None) or engine
    db_path = getattr(target, "db_path", None)
    if not db_path:
        return {}
    placeholders = ",".join("?" * len(file_names))
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"""
            SELECT file_name,
                   SUM(CASE WHEN difficulty='A' THEN 1 ELSE 0 END) AS a,
                   SUM(CASE WHEN difficulty='B' THEN 1 ELSE 0 END) AS b,
                   SUM(CASE WHEN difficulty='C' THEN 1 ELSE 0 END) AS c,
                   SUM(CASE WHEN difficulty='D' THEN 1 ELSE 0 END) AS d
            FROM problems
            WHERE file_name IN ({placeholders})
            GROUP BY file_name
        """, file_names).fetchall()
    finally:
        conn.close()
    return {r[0]: (r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0) for r in rows}


@router.get("/partial/original/files", response_class=HTMLResponse)
def partial_original_files(
    request: Request,
    source: str,
    search: Optional[str] = None,
    year: Optional[str] = None,
    school: Optional[str] = None,
    grade: Optional[str] = None,
    semester: Optional[str] = None,
    exam_type: Optional[str] = None,
    curriculum: Optional[str] = None,
    subject: Optional[str] = None,
    unit_like: Optional[str] = None,
    diff_level: Optional[str] = None,
    unit_start: Optional[str] = None,
    unit_end: Optional[str] = None,
    user: SessionUser = Depends(require_user),
):
    """소스 + 필터로 시험지 파일 목록."""
    if source not in SOURCES:
        return HTMLResponse(
            '<div class="text-red-300 text-sm">유효하지 않은 소스</div>',
            status_code=200,
        )
    is_naesin = source in ("NAESIN_A", "NAESIN_N")

    f: dict = {"source": source}
    if search: f["file_name_like"] = search.strip()
    if year: f["year"] = year.strip()
    if school: f["school"] = school.strip()
    if is_naesin:
        if grade: f["grade"] = grade.strip()
        if semester: f["semester"] = semester.strip()
        if exam_type: f["exam_type"] = exam_type.strip()
        if curriculum: f["curriculum"] = curriculum.strip()
        if subject: f["subject"] = subject.strip()
        if unit_like: f["unit_like"] = unit_like.strip()

        # 시험범위 unit_start ~ unit_end → unit_range_codes
        us = (unit_start or "").strip()
        ue = (unit_end or "").strip()
        if us and ue and subject:
            order = _ordered_units_for_subject(subject.strip())
            name_to_idx = {u["name"]: i for i, u in enumerate(order)}
            si = name_to_idx.get(us)
            ei = name_to_idx.get(ue)
            if si is not None and ei is not None:
                lo, hi = min(si, ei), max(si, ei)
                f["unit_range_codes"] = [order[i]["code"] for i in range(lo, hi + 1)]

    engine = get_engine()
    rows = engine.search_exams_grouped(f)

    # 난이도 뱃지 — grade(중/고) 기준 분리 적용. NAESIN_N 에 고1·중2 혼재하므로 source 가 아닌 grade 로 분기.
    # 2026-05-16 고등(grade='고%') 484 시험지 전수조사:
    #   점수 = A×2 + B×1, th10=12 / th30=8 / th60=4
    # 2026-05-21 중등(grade='중%') 142 시험지 전수조사:
    #   고등 공식 적용 시 55.6% 가 0점 → 모두 "하" 로 떨어지는 문제
    #   새 공식 = A×3 + B×2 + C×1, th10=20 / th30=16 / th60=11
    # 중등 a/b/c 카운트는 서버에서 별도 조회 (로컬 db_engine 미변경).
    if is_naesin:
        TH_HIGH = (12, 8, 4)
        TH_MID = (20, 16, 11)
        mid_files = [r["file_name"] for r in rows
                     if (r.get("grade") or "").strip().startswith("중") and r.get("file_name")]
        mid_counts = _get_diff_counts_for_files(engine, mid_files) if mid_files else {}
        for r in rows:
            grade = (r.get("grade") or "").strip()
            if grade.startswith("중"):
                a, b, c, _d = mid_counts.get(r.get("file_name"), (0, 0, 0, 0))
                score = 3 * a + 2 * b + 1 * c
                r["adv_score"] = score
                th = TH_MID
            else:
                score = r.get("adv_score") or 0
                th = TH_HIGH
            r["diff_badge"] = _diff_badge_for_score(score, *th)
        if diff_level:
            rows = [r for r in rows if r.get("diff_badge") == diff_level.strip()]

    if is_naesin:
        groups: dict = {}
        for r in rows:
            key = r.get("school") or "미분류"
            groups.setdefault(key, []).append(r)
    else:
        groups = {}
        for r in rows:
            key = r.get("year") or "연도미상"
            groups.setdefault(key, []).append(r)

    return templates.TemplateResponse(
        request, "partials/original_files.html",
        {
            "groups": groups,
            "total": len(rows),
            "is_naesin": is_naesin,
            "source": source,
        },
    )


@router.get("/partial/original/problems", response_class=HTMLResponse)
def partial_original_problems(
    request: Request,
    file_name: str,
    user: SessionUser = Depends(require_user),
):
    """파일 선택 시 해당 파일의 문제 목록."""
    engine = get_engine()
    problems = engine.get_problems_by_files([file_name])
    has_naesin = any(
        (p.get("source") or "") in ("NAESIN_A", "NAESIN_N") for p in problems
    )
    # 단원 자동 채움 — 큰 단원 첫 3개 (로컬 main_gui.py:1276-1277 동등)
    _seen = []
    for p in problems:
        lu = (p.get("large_unit") or "").strip()
        if lu and lu not in _seen:
            _seen.append(lu)
        if len(_seen) >= 3:
            break
    unit_default = ", ".join(_seen)
    # 폴더 트리 옵션 — 로컬 main_gui.py:1375 _build_folder_options 동등
    folder_options = _build_folder_select_options(engine.get_folders(user.uid))
    return templates.TemplateResponse(
        request, "partials/original_problems.html",
        {
            "problems": problems, "file_name": file_name,
            "has_naesin": has_naesin, "unit_default": unit_default,
            "folder_options": folder_options,
        },
    )


def _build_folder_select_options(folders):
    """저장 폼 <select> 용 계층형 폴더 옵션.
    Returns [{value, label}, ...]
    로컬 main_gui.py:1375 _build_folder_options 동등.
    """
    opts = [{"value": "", "label": "/ (최상위)"}]

    def _add_children(parent_id, depth):
        children = [f for f in folders if f.get("parent_id") == parent_id]
        children.sort(key=lambda x: x.get("id", 0))
        for f in children:
            prefix = (" " * (depth * 4)) + ("└ " if depth > 0 else "")
            icon = "\U0001f512" if f.get("is_protected") else "\U0001f4c1"
            opts.append({"value": str(f["id"]), "label": f"{prefix}{icon} {f['name']}"})
            _add_children(f["id"], depth + 1)

    _add_children(None, 0)
    return opts


@router.get("/partial/folder_select_options", response_class=HTMLResponse)
def partial_folder_select_options(
    request: Request,
    user: SessionUser = Depends(require_user),
):
    """저장 폼 <select> 갱신용 — <option> 들만 반환."""
    engine = get_engine()
    folder_options = _build_folder_select_options(engine.get_folders(user.uid))
    html = "\n".join(
        f'<option value="{o["value"]}">{o["label"]}</option>'
        for o in folder_options
    )
    return HTMLResponse(html)


# ─────────── 시험지 관리 (Library) ───────────
def _build_folder_tree(folders):
    """평면 폴더 리스트 → parent_id 기반 계층 트리.
    각 노드: {id, name, is_protected, children: [...]}"""
    nodes = {f["id"]: {**f, "children": []} for f in folders}
    roots = []
    for f in folders:
        pid = f.get("parent_id")
        if pid and pid in nodes:
            nodes[pid]["children"].append(nodes[f["id"]])
        else:
            roots.append(nodes[f["id"]])
    # 생성 순서대로 (id asc)
    def sort_rec(lst):
        lst.sort(key=lambda n: n.get("id") or 0)
        for n in lst:
            sort_rec(n["children"])
    sort_rec(roots)
    return roots


@router.get("/library", response_class=HTMLResponse)
def library_page(request: Request, user: SessionUser = Depends(get_optional_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        request, "library.html",
        {"user": user},
    )


@router.get("/partial/library/folders", response_class=HTMLResponse)
def partial_library_folders(request: Request, user: SessionUser = Depends(require_user)):
    engine = get_engine()
    folders = engine.get_folders(user.uid)
    tree = _build_folder_tree(folders)
    return templates.TemplateResponse(
        request, "partials/library_folders.html",
        {"tree": tree},
    )


@router.get("/partial/library/tests", response_class=HTMLResponse)
def partial_library_tests(
    request: Request,
    folder_id: Optional[str] = None,
    sort: str = "created",
    q: Optional[str] = None,
    user: SessionUser = Depends(require_user),
):
    """folder_id 미지정 또는 'root' → 루트(directory_id=None). q=제목/단원요약 검색어."""
    engine = get_engine()
    fid: Optional[int]
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
        },
    )


@router.get("/partial/library/main", response_class=HTMLResponse)
def partial_library_main(request: Request, user: SessionUser = Depends(require_user)):
    """문항 보기 전체 화면 → ← 돌아가기 시 메인 그리드 복원."""
    return templates.TemplateResponse(request, "partials/library_main.html", {"user": user})


@router.get("/partial/library/test/{test_id}/full", response_class=HTMLResponse)
def partial_library_test_full(
    request: Request,
    test_id: int,
    user: SessionUser = Depends(require_user),
):
    """문항 보기 전체 화면 (로컬 main_gui.py:6315 _lib_show_problem_view 동등).
    좌(폴더)+중(목록)+우(상세) 그리드를 통째로 swap 해 전체 폭에서 7컬럼을 시원하게 표시."""
    engine = get_engine()
    detail = engine.get_test_detail(test_id, user.uid)
    if not detail:
        return HTMLResponse(
            '<div class="text-rose-300 text-sm">시험지를 찾을 수 없거나 권한이 없습니다.</div>',
            status_code=200,
        )
    folders = engine.get_folders(user.uid)
    unit_mappings = _load_unit_mappings()
    unit_options = [{"code": k, "name": v} for k, v in unit_mappings.items()]
    problem_ids = [p.get("id") for p in (detail.get("problems") or []) if p.get("id") is not None]
    try:
        pref_map = engine.get_preferences_bulk(user.uid, problem_ids) or {}
    except Exception:
        pref_map = {}
    return templates.TemplateResponse(
        request, "partials/library_test_full.html",
        {
            "test": detail,
            "folders": folders,
            "unit_options": unit_options,
            "pref_map": pref_map,
            "is_admin": (user.role == "admin"),
            "user_display": user.display_id or user.uid,
        },
    )


@router.get("/partial/library/test/{test_id}/preview", response_class=HTMLResponse)
def partial_library_test_preview(
    request: Request,
    test_id: int,
    user: SessionUser = Depends(require_user),
):
    """시험지 클릭 시 — 문제 목록(인라인 편집/선호도/삭제) + 출제 버튼.
    로컬 main_gui.py:6315 _lib_show_problem_view 동등.
    """
    engine = get_engine()
    detail = engine.get_test_detail(test_id, user.uid)
    if not detail:
        return HTMLResponse(
            '<div class="text-slate-500 text-sm">시험지를 찾을 수 없거나 권한이 없습니다.</div>',
            status_code=200,
        )
    folders = engine.get_folders(user.uid)

    # 단원 옵션 (curriculum_config.json) — 더블클릭 인라인 편집 드롭다운용
    unit_mappings = _load_unit_mappings()
    unit_options = [{"code": k, "name": v} for k, v in unit_mappings.items()]

    # 선호도 일괄 조회 (Good/Soso/Bad/None)
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


# ─────────── 문제 관리 (admin) ───────────
from server.auth_dep import require_admin


def _load_unit_mappings():
    path = config.BASE_DIR / "backend" / "curriculum_config.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f).get("unit_mappings", {})


@router.get("/manage", response_class=HTMLResponse)
def manage_page(request: Request, user: SessionUser = Depends(get_optional_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse("/", status_code=302)
    # 2026-05-23: 원본출제 검색 UI 동등 — curriculums / years 추가
    curriculums = _load_curriculum_subjects()
    engine = get_engine()
    try:
        all_years = engine.get_unique_years() or []
    except Exception:
        all_years = []
    return templates.TemplateResponse(
        request, "manage.html",
        {
            "user": user,
            "sources": [(s, SOURCE_LABELS[s]) for s in SOURCES],
            "curriculums": curriculums,
            "curriculum_names": list(curriculums.keys()),
            "all_years": all_years,
        },
    )


@router.get("/partial/manage/files", response_class=HTMLResponse)
def partial_manage_files(
    request: Request,
    source: str,
    search: Optional[str] = None,
    year: Optional[str] = None,
    school: Optional[str] = None,
    grade: Optional[str] = None,
    semester: Optional[str] = None,
    exam_type: Optional[str] = None,
    curriculum: Optional[str] = None,
    subject: Optional[str] = None,
    unit_like: Optional[str] = None,
    diff_level: Optional[str] = None,
    unit_start: Optional[str] = None,
    unit_end: Optional[str] = None,
    user: SessionUser = Depends(require_admin),
):
    """2026-05-23: 원본출제 검색 UI 동등 — 11개 필터 + 시험범위 + 난이도 뱃지.
    로직 흐름은 partial_original_files 와 동일하나 admin 권한, 응답 partial 만 다름.
    """
    if source not in SOURCES:
        return HTMLResponse('<div class="text-red-300 text-sm">유효하지 않은 소스</div>')
    is_naesin = source in ("NAESIN_A", "NAESIN_N")

    f: dict = {"source": source}
    if search: f["file_name_like"] = search.strip()
    if year: f["year"] = year.strip()
    if school: f["school"] = school.strip()
    if is_naesin:
        if grade: f["grade"] = grade.strip()
        if semester: f["semester"] = semester.strip()
        if exam_type: f["exam_type"] = exam_type.strip()
        if curriculum: f["curriculum"] = curriculum.strip()
        if subject: f["subject"] = subject.strip()
        if unit_like: f["unit_like"] = unit_like.strip()

        # 시험범위 unit_start ~ unit_end → unit_range_codes (partial_original_files 동등)
        us = (unit_start or "").strip()
        ue = (unit_end or "").strip()
        if us and ue and subject:
            order = _ordered_units_for_subject(subject.strip())
            name_to_idx = {u["name"]: i for i, u in enumerate(order)}
            si = name_to_idx.get(us)
            ei = name_to_idx.get(ue)
            if si is not None and ei is not None:
                lo, hi = min(si, ei), max(si, ei)
                f["unit_range_codes"] = [order[i]["code"] for i in range(lo, hi + 1)]

    engine = get_engine()
    rows = engine.search_exams_grouped(f)

    # 난이도 뱃지 (내신만) — partial_original_files 와 동일
    if is_naesin:
        TH_HIGH = (12, 8, 4)
        TH_MID = (20, 16, 11)
        mid_files = [r["file_name"] for r in rows
                     if (r.get("grade") or "").strip().startswith("중") and r.get("file_name")]
        mid_counts = _get_diff_counts_for_files(engine, mid_files) if mid_files else {}
        for r in rows:
            grade_v = (r.get("grade") or "").strip()
            if grade_v.startswith("중"):
                a, b, c, _d = mid_counts.get(r.get("file_name"), (0, 0, 0, 0))
                score = 3 * a + 2 * b + 1 * c
                r["adv_score"] = score
                th = TH_MID
            else:
                score = r.get("adv_score") or 0
                th = TH_HIGH
            r["diff_badge"] = _diff_badge_for_score(score, *th)
        if diff_level:
            rows = [r for r in rows if r.get("diff_badge") == diff_level.strip()]

    if is_naesin:
        groups = {}
        for r in rows:
            key = r.get("school") or "미분류"
            groups.setdefault(key, []).append(r)
    else:
        groups = {}
        for r in rows:
            key = r.get("year") or "연도미상"
            groups.setdefault(key, []).append(r)
    return templates.TemplateResponse(
        request, "partials/manage_files.html",
        {"groups": groups, "total": len(rows), "is_naesin": is_naesin, "source": source},
    )


def _flatten_unit_options() -> list:
    """단원 수정 드롭다운용 — 모든 medium unit (code, '과목 > 대단원 > 중단원') 평면 리스트.
    2022 → 2015 순서, 중복 code 제거."""
    out: list = []
    seen: set = set()
    try:
        units = _load_units()  # {2022: [...], 2015: [...]}
    except Exception:
        return out
    for ver in ("2022", "2015"):
        for subj in units.get(ver, []):
            sname = subj.get("subject") or ""
            for lu in subj.get("large_units", []):
                lname = lu.get("name") or ""
                for mu in lu.get("medium_units", []):
                    code = mu.get("code") or ""
                    name = mu.get("name") or ""
                    if not code or code in seen:
                        continue
                    seen.add(code)
                    label = f"[{code}] {sname} > {lname} > {name}"
                    out.append({"code": code, "name": name, "label": label})
    return out


@router.get("/partial/manage/unit_stats", response_class=HTMLResponse)
def partial_manage_unit_stats(
    request: Request,
    file_name: str,
    user: SessionUser = Depends(require_admin),
):
    """선택 파일의 단원별 분포 (large_unit > middle_unit, count)."""
    engine = get_engine()
    rows = engine.get_unit_stats([file_name])
    total = sum(r.get("count") or 0 for r in rows)
    return templates.TemplateResponse(
        request, "partials/manage_unit_stats.html",
        {"rows": rows, "total": total, "file_name": file_name},
    )


@router.get("/partial/manage/problems", response_class=HTMLResponse)
def partial_manage_problems(
    request: Request,
    file_name: str,
    view_mode: str = "all",  # all | excluded
    user: SessionUser = Depends(require_admin),
):
    engine = get_engine()
    problems = engine.get_problems_by_files([file_name])
    if view_mode == "excluded":
        problems = [p for p in problems if p.get("is_excluded")]
    pref_map = {}
    if problems:
        try:
            pref_map = engine.get_preferences_bulk(user.uid, [str(p["id"]) for p in problems]) or {}
        except Exception:
            pref_map = {}
    units = _load_unit_mappings()
    return templates.TemplateResponse(
        request, "partials/manage_problems.html",
        {
            "problems": problems,
            "file_name": file_name,
            "view_mode": view_mode,
            "pref_map": pref_map,
            "unit_mappings": units,
            "all_units": _flatten_unit_options(),
        },
    )
