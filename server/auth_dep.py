"""세션 쿠키 검증 의존성 + JWT 발급."""
import time
from typing import Optional
from dataclasses import dataclass

import jwt
from fastapi import Request, HTTPException, status, Depends

from server import config


@dataclass
class SessionUser:
    uid: str
    display_id: str
    display_name: str
    role: str
    email: str


def issue_session_token(user: SessionUser) -> str:
    """SessionUser → JWT 문자열."""
    now = int(time.time())
    payload = {
        "uid": user.uid,
        "did": user.display_id,
        "dn": user.display_name,
        "role": user.role,
        "email": user.email,
        "iat": now,
        "exp": now + config.SESSION_TTL_SECONDS,
    }
    return jwt.encode(payload, config.SESSION_SECRET, algorithm="HS256")


def decode_session_token(token: str) -> Optional[SessionUser]:
    try:
        payload = jwt.decode(token, config.SESSION_SECRET, algorithms=["HS256"])
        return SessionUser(
            uid=payload["uid"],
            display_id=payload["did"],
            display_name=payload.get("dn", ""),
            role=payload["role"],
            email=payload["email"],
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError):
        return None


def get_optional_user(request: Request) -> Optional[SessionUser]:
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        # 개발자 자동 로그인 백도어 — 환경변수 NAEGIWANGBANK_DEV_BYPASS=admin|user 설정 시.
        # 운영 환경에서는 절대 이 환경변수를 두지 말 것.
        import os
        bypass = os.environ.get("NAEGIWANGBANK_DEV_BYPASS")
        if bypass in ("admin", "user"):
            return SessionUser(
                uid=f"dev-{bypass}",
                display_id=f"dev-{bypass}",
                display_name=f"DEV {bypass.upper()}",
                role=bypass,
                email=f"dev-{bypass}@local",
            )
        return None
    return decode_session_token(token)


def require_user(request: Request) -> SessionUser:
    user = get_optional_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
            headers={"HX-Redirect": "/login"},
        )
    return user


def require_admin(user: SessionUser = Depends(require_user)) -> SessionUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user
