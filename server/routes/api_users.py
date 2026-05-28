"""사용자 관리 API — admin 전용. 로컬 main_gui.py:6950-7264 동등.

엔드포인트:
  GET  /partial/users                       — 사용자 목록 partial
  POST /api/users/create                    — 신규 계정 발급 (모달 form)
  POST /api/users/{uid}/reset_password      — 비번 재설정
  POST /api/users/{uid}/toggle_active       — 활성/비활성 토글
  POST /api/users/{uid}/change_role         — admin ↔ user
  POST /api/users/{uid}/delete              — 계정 삭제 (Auth+Firestore)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server import config
from server.auth_dep import require_admin, SessionUser

router = APIRouter(tags=["users"])
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


def _list_users_safe():
    from backend import user_admin
    try:
        return user_admin.list_users(), None
    except Exception as e:
        return [], str(e)


@router.get("/partial/users", response_class=HTMLResponse)
def partial_users(request: Request, user: SessionUser = Depends(require_admin)):
    users, err = _list_users_safe()
    return templates.TemplateResponse(
        request, "partials/users_list.html",
        {"users": users, "current_uid": user.uid, "error": err},
    )


@router.post("/api/users/create", response_class=HTMLResponse)
async def api_users_create(
    request: Request,
    display_id: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    display_name: Optional[str] = Form(""),
    user: SessionUser = Depends(require_admin),
):
    from backend import user_admin
    if not display_id.strip():
        return HTMLResponse(
            '<div class="text-rose-300 text-xs">ID를 입력하세요.</div>',
        )
    if len(password) < 6:
        return HTMLResponse(
            '<div class="text-rose-300 text-xs">비밀번호는 6자 이상이어야 합니다.</div>',
        )
    if role not in ("admin", "user"):
        return HTMLResponse('<div class="text-rose-300 text-xs">잘못된 역할.</div>')
    try:
        user_admin.create_user(
            display_id.strip(), password, role=role,
            display_name=(display_name or "").strip(),
        )
    except Exception as e:
        return HTMLResponse(
            f'<div class="text-rose-300 text-xs">실패: {e}</div>',
        )
    # 성공: 목록 갱신 트리거 + 결과 메시지
    return HTMLResponse(
        f'<div class="text-emerald-300 text-xs" '
        f'hx-trigger="load delay:1500ms" hx-get="/partial/users" '
        f'hx-target="#users-root" hx-swap="innerHTML">'
        f'✓ 발급 완료 — ID: {display_id} / 비번: {password} / 역할: {role}</div>'
    )


def _self_guard(target_uid: str, user: SessionUser):
    if target_uid == user.uid:
        raise HTTPException(400, "본인 계정에는 적용할 수 없습니다.")


@router.post("/api/users/{uid}/reset_password", response_class=HTMLResponse)
async def api_users_reset_password(
    request: Request,
    uid: str,
    new_password: str = Form(...),
    user: SessionUser = Depends(require_admin),
):
    from backend import user_admin
    if len(new_password) < 6:
        return HTMLResponse(
            '<div class="text-rose-300 text-xs">비밀번호는 6자 이상이어야 합니다.</div>'
        )
    try:
        user_admin.reset_password(uid, new_password)
    except Exception as e:
        return HTMLResponse(f'<div class="text-rose-300 text-xs">실패: {e}</div>')
    return HTMLResponse(
        f'<div class="text-emerald-300 text-xs">✓ 비밀번호 재설정 — 새 비번: {new_password}</div>'
    )


@router.post("/api/users/{uid}/toggle_active", response_class=HTMLResponse)
async def api_users_toggle_active(
    request: Request,
    uid: str,
    active: int = Form(...),
    user: SessionUser = Depends(require_admin),
):
    from backend import user_admin
    _self_guard(uid, user) if not active else None
    try:
        user_admin.set_active(uid, bool(active))
    except Exception as e:
        return HTMLResponse(f'<div class="text-rose-300 text-xs">실패: {e}</div>')
    return partial_users(request, user)


@router.post("/api/users/{uid}/change_role", response_class=HTMLResponse)
async def api_users_change_role(
    request: Request,
    uid: str,
    new_role: str = Form(...),
    user: SessionUser = Depends(require_admin),
):
    from backend import user_admin
    _self_guard(uid, user)
    try:
        user_admin.update_role(uid, new_role)
    except Exception as e:
        return HTMLResponse(f'<div class="text-rose-300 text-xs">실패: {e}</div>')
    return partial_users(request, user)


@router.post("/api/users/{uid}/delete", response_class=HTMLResponse)
async def api_users_delete(
    request: Request,
    uid: str,
    user: SessionUser = Depends(require_admin),
):
    from backend import user_admin
    _self_guard(uid, user)
    try:
        user_admin.delete_user(uid)
    except Exception as e:
        return HTMLResponse(f'<div class="text-rose-300 text-xs">실패: {e}</div>')
    return partial_users(request, user)
