"""인증 API — Firebase REST 위임 + 세션 쿠키 발급."""
import time
import requests
from fastapi import APIRouter, Form, Response, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, PlainTextResponse

from server import config
from server.auth_dep import (
    SessionUser, issue_session_token, get_optional_user, require_user,
)

# 기존 backend/auth.py 의 상수/유틸 재사용
from backend.auth import (
    SIGN_IN_URL, _to_email, _from_email, _fetch_user_doc, AuthError,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(response: Response, display_id: str = Form(...), password: str = Form(...)):
    """display_id + password → 세션 쿠키 발급."""
    email = _to_email(display_id)
    try:
        rest = requests.post(
            SIGN_IN_URL,
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=10,
        )
    except requests.RequestException as e:
        return PlainTextResponse(f"네트워크 오류: {e}", status_code=200)

    if rest.status_code != 200:
        try:
            err_msg = rest.json().get("error", {}).get("message", "")
        except Exception:
            err_msg = rest.text
        friendly = {
            "EMAIL_NOT_FOUND": "존재하지 않는 ID입니다.",
            "INVALID_PASSWORD": "비밀번호가 틀렸습니다.",
            "INVALID_LOGIN_CREDENTIALS": "ID 또는 비밀번호가 틀렸습니다.",
            "USER_DISABLED": "비활성화된 계정입니다.",
            "TOO_MANY_ATTEMPTS_TRY_LATER": "시도 횟수 초과. 잠시 후 다시 시도하세요.",
        }.get(err_msg, f"로그인 실패: {err_msg}")
        return PlainTextResponse(friendly, status_code=200)

    rest_data = rest.json()
    uid = rest_data["localId"]

    try:
        user_doc = _fetch_user_doc(uid)
    except AuthError as e:
        return PlainTextResponse(str(e), status_code=200)

    user = SessionUser(
        uid=uid,
        display_id=user_doc.get("display_id") or _from_email(rest_data["email"]),
        display_name=user_doc.get("display_name") or "",
        role=user_doc["role"],
        email=rest_data["email"],
    )
    token = issue_session_token(user)
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        max_age=config.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,  # 외부 접속 시(HTTPS) True 로 환경변수로 토글 권장
    )
    response.headers["HX-Redirect"] = "/"
    return {"ok": True, "uid": uid, "role": user.role}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.SESSION_COOKIE_NAME)
    response.headers["HX-Redirect"] = "/login"
    return {"ok": True}


@router.get("/me")
def me(user: SessionUser = Depends(require_user)):
    return {
        "uid": user.uid,
        "display_id": user.display_id,
        "display_name": user.display_name,
        "role": user.role,
        "email": user.email,
    }
