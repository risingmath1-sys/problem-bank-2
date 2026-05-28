# -*- coding: utf-8 -*-
"""
Phase 2-C: 인증 모듈

설계도: 로그인시스템설계도.md §8-1, §8-2

기능:
  - login(display_id, password) -> dict   (성공 시) | raises AuthError (실패 시)
  - logout()
  - load_cached_session() -> dict | None   (자동 로그인용)
  - get_current_user() -> dict | None
  - refresh_id_token() -> bool

내부:
  - Firebase Auth REST API (signInWithPassword) 로 비번 검증
  - Firestore users/{uid} 에서 role / active 조회
  - 토큰 캐시: %APPDATA%\\naegiwangbank\\auth_token.json
"""
import json
import os
import time
import datetime
from typing import Optional

import requests

# 이 키는 frontend/src/firebase.js 에 이미 공개되어 있다 (Web API Key 는 비밀이 아님)
WEB_API_KEY = "AIzaSyAyn73R7Kj4yFMZPJhCp1FjZMS9Q8NgsNE"

EMAIL_DOMAIN = "@sangsung.local"

SIGN_IN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}"
REFRESH_URL = f"https://securetoken.googleapis.com/v1/token?key={WEB_API_KEY}"

CACHE_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "naegiwangbank")
CACHE_PATH = os.path.join(CACHE_DIR, "auth_token.json")

_current_session: Optional[dict] = None  # 인메모리 세션


class AuthError(Exception):
    pass


def _to_email(display_id: str) -> str:
    """짧은 ID → 내부 email. '@' 가 이미 있으면 그대로."""
    display_id = (display_id or "").strip()
    if not display_id:
        raise AuthError("ID가 비어있습니다.")
    return display_id if "@" in display_id else display_id + EMAIL_DOMAIN


def _from_email(email: str) -> str:
    """email → 표시용 ID."""
    if email and email.endswith(EMAIL_DOMAIN):
        return email[: -len(EMAIL_DOMAIN)]
    return email


def _get_firestore():
    """firebase_admin 이 이미 초기화돼 있다고 가정 (main_gui.py 에서 초기화됨)."""
    from firebase_admin import firestore
    return firestore.client()


def _save_cache(session: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)


def _load_cache() -> Optional[dict]:
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _delete_cache():
    if os.path.exists(CACHE_PATH):
        try:
            os.remove(CACHE_PATH)
        except Exception:
            pass


def _fetch_user_doc(uid: str) -> dict:
    """Firestore users/{uid} 에서 role, active, display_name 등 조회."""
    db = _get_firestore()
    snap = db.collection("users").document(uid).get()
    if not snap.exists:
        raise AuthError("사용자 정보가 등록되어 있지 않습니다. 관리자에게 문의하세요.")
    data = snap.to_dict() or {}
    if not data.get("active", False):
        raise AuthError("비활성화된 계정입니다. 관리자에게 문의하세요.")
    role = data.get("role")
    if role not in ("admin", "user"):
        raise AuthError("권한 정보가 올바르지 않습니다.")
    return data


def _build_session(rest_resp: dict, user_doc: dict) -> dict:
    """REST 응답 + Firestore user 문서 → 세션 dict."""
    expires_in = int(rest_resp.get("expiresIn", "3600"))
    expires_at = time.time() + expires_in
    return {
        "uid": rest_resp["localId"],
        "email": rest_resp["email"],
        "display_id": user_doc.get("display_id") or _from_email(rest_resp["email"]),
        "display_name": user_doc.get("display_name") or "",
        "role": user_doc["role"],
        "id_token": rest_resp["idToken"],
        "refresh_token": rest_resp["refreshToken"],
        "expires_at": expires_at,
        "saved_at": time.time(),
    }


def login(display_id: str, password: str) -> dict:
    """로그인. 성공 시 세션 dict 반환 + 캐시 저장. 실패 시 AuthError."""
    global _current_session
    email = _to_email(display_id)
    try:
        resp = requests.post(
            SIGN_IN_URL,
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=10,
        )
    except requests.RequestException as e:
        raise AuthError(f"네트워크 오류: {e}")

    if resp.status_code != 200:
        try:
            err_msg = resp.json().get("error", {}).get("message", "")
        except Exception:
            err_msg = resp.text
        # 친화적 메시지로 변환
        friendly = {
            "EMAIL_NOT_FOUND": "존재하지 않는 ID입니다.",
            "INVALID_PASSWORD": "비밀번호가 틀렸습니다.",
            "INVALID_LOGIN_CREDENTIALS": "ID 또는 비밀번호가 틀렸습니다.",
            "USER_DISABLED": "비활성화된 계정입니다.",
            "TOO_MANY_ATTEMPTS_TRY_LATER": "시도 횟수 초과. 잠시 후 다시 시도하세요.",
        }.get(err_msg, f"로그인 실패: {err_msg}")
        raise AuthError(friendly)

    rest_data = resp.json()
    user_doc = _fetch_user_doc(rest_data["localId"])  # active/role 검증

    # PC 인증 (계정 도용 방지) — admin 면제, user 만 검증/등록
    try:
        from backend.pc_identity import verify_or_register_device, DeviceError
        verify_or_register_device(rest_data["localId"], user_doc["role"])
    except DeviceError as e:
        raise AuthError(str(e))

    session = _build_session(rest_data, user_doc)
    _save_cache(session)
    _current_session = session
    return session


def logout():
    """로그아웃. 캐시 + 메모리 세션 삭제."""
    global _current_session
    _current_session = None
    _delete_cache()


def load_cached_session() -> Optional[dict]:
    """캐시에서 세션 복원. 토큰 만료 시 refresh 시도. 실패하면 None.
    PC 인증 실패 시 캐시 삭제 + None (다른 PC 에 cache 파일 복사 공격 차단)."""
    global _current_session
    cached = _load_cache()
    if not cached:
        return None
    # 만료 5분 전이면 refresh
    if cached.get("expires_at", 0) > time.time() + 300:
        _current_session = cached
    else:
        # refresh 시도
        if not _refresh_token(cached):
            _delete_cache()
            return None
        _current_session = cached
        _save_cache(cached)

    # PC 인증 검증 (admin 면제). 실패 시 캐시 폐기 + 로그인 다이얼로그로 강제
    try:
        from backend.pc_identity import verify_or_register_device, DeviceError
        verify_or_register_device(cached["uid"], cached.get("role", "user"))
    except DeviceError:
        _current_session = None
        _delete_cache()
        return None
    except Exception:
        # 네트워크/Firestore 일시 오류 → 캐시 유지 (오프라인 허용)
        pass

    return cached


def _refresh_token(session: dict) -> bool:
    """refresh_token 으로 새 idToken 발급. 성공 True, 실패 False."""
    rt = session.get("refresh_token")
    if not rt:
        return False
    try:
        resp = requests.post(
            REFRESH_URL,
            data={"grant_type": "refresh_token", "refresh_token": rt},
            timeout=10,
        )
    except requests.RequestException:
        return False
    if resp.status_code != 200:
        return False
    data = resp.json()
    session["id_token"] = data["id_token"]
    session["refresh_token"] = data["refresh_token"]
    session["expires_at"] = time.time() + int(data["expires_in"])
    session["saved_at"] = time.time()
    return True


def get_current_user() -> Optional[dict]:
    """현재 로그인된 사용자. 없으면 None."""
    return _current_session


def is_admin() -> bool:
    return bool(_current_session and _current_session.get("role") == "admin")
