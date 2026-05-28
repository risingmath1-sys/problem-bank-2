# -*- coding: utf-8 -*-
"""
Phase 2-H: 사용자 관리 (admin 전용)

설계도: 로그인시스템설계도.md §8-1

기능:
  - list_users()                                    : Firestore users/ 컬렉션 조회
  - create_user(display_id, password, role, name)   : Firebase Auth + Firestore 동시 생성
  - reset_password(uid, new_password)               : Firebase Auth 비번 재설정
  - set_active(uid, active)                         : Firestore users/{uid}.active 토글
  - delete_user(uid)                                : Auth + Firestore 양쪽 삭제 (위험)

전제:
  firebase_admin._apps 가 이미 초기화돼 있어야 함 (main_gui.py 진입점에서 처리).
  이 모듈의 함수들은 Firebase Admin SDK (서비스 계정) 권한으로 동작 → admin 만 호출해야 함.
  GUI 단에서 self.current_user_role == "admin" 가드로 호출 차단.
"""
import datetime
from typing import Optional

from firebase_admin import auth as fb_auth
from firebase_admin import firestore


EMAIL_DOMAIN = "@sangsung.local"


class UserAdminError(Exception):
    pass


def _to_email(display_id: str) -> str:
    display_id = (display_id or "").strip()
    if not display_id:
        raise UserAdminError("ID가 비어있습니다.")
    if "@" in display_id:
        return display_id
    return display_id + EMAIL_DOMAIN


def _from_email(email: str) -> str:
    if email and email.endswith(EMAIL_DOMAIN):
        return email[: -len(EMAIL_DOMAIN)]
    return email or ""


def _db():
    return firestore.client()


def list_users() -> list:
    """Firestore users/ 전체 조회. 정렬 = display_id."""
    snaps = _db().collection("users").stream()
    out = []
    for s in snaps:
        d = s.to_dict() or {}
        d["uid"] = s.id
        d.setdefault("display_id", _from_email(d.get("email", "")))
        d.setdefault("display_name", "")
        d.setdefault("role", "user")
        d.setdefault("active", True)
        out.append(d)
    out.sort(key=lambda x: (x.get("role") != "admin", x.get("display_id", "")))
    return out


def _other_active_admin_exists(exclude_uid: str) -> bool:
    """exclude_uid를 제외하고 다른 active admin이 1명 이상 있으면 True.
    마지막 admin 보호용 헬퍼.
    """
    for u in list_users():
        if u.get("uid") == exclude_uid:
            continue
        if u.get("role") == "admin" and u.get("active", True):
            return True
    return False


def create_user(display_id: str, password: str, role: str = "user",
                display_name: str = "") -> dict:
    """신규 계정 발급. Firebase Auth + Firestore users/{uid} 동시 생성.

    role: "admin" | "user"
    이미 존재하면 UserAdminError.
    """
    if role not in ("admin", "user"):
        raise UserAdminError("role은 admin 또는 user 여야 합니다.")
    if not password or len(password) < 6:
        raise UserAdminError("비밀번호는 6자 이상이어야 합니다.")

    email = _to_email(display_id)

    # 이미 있는지 확인
    try:
        existing = fb_auth.get_user_by_email(email)
        raise UserAdminError(f"이미 존재하는 ID 입니다: {display_id}")
    except fb_auth.UserNotFoundError:
        pass

    user = fb_auth.create_user(
        email=email,
        password=password,
        display_name=display_name or display_id,
        email_verified=True,
    )

    now = datetime.datetime.utcnow()
    doc = {
        "display_id": _from_email(email),
        "email": email,
        "display_name": display_name or "",
        "role": role,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    db = _db()
    db.collection("users").document(user.uid).set(doc)

    # 신규 사용자에게 '오답' 보호 폴더 자동 발급 (채점 다이얼로그 default 폴더)
    try:
        from backend.firestore_engine import ensure_protected_folder
        ensure_protected_folder(db, user.uid, "오답")
    except Exception as e:
        # 보호 폴더 생성 실패해도 사용자 발급 자체는 성공으로 처리.
        # 채점 다이얼로그가 lazy fallback 으로 안전히 처리되도록.
        print(f"[user_admin] 오답 폴더 발급 실패 (uid={user.uid}): {e}")

    doc["uid"] = user.uid
    return doc


def reset_password(uid: str, new_password: str):
    """Firebase Auth 비번 재설정."""
    if not new_password or len(new_password) < 6:
        raise UserAdminError("비밀번호는 6자 이상이어야 합니다.")
    fb_auth.update_user(uid, password=new_password)
    _db().collection("users").document(uid).update({
        "updated_at": datetime.datetime.utcnow(),
    })


def set_active(uid: str, active: bool):
    """Firestore users/{uid}.active 토글 + Firebase Auth disabled 동기화.
    마지막 active admin 비활성화는 차단.
    """
    if not active:
        target = _db().collection("users").document(uid).get().to_dict() or {}
        if target.get("role") == "admin" and target.get("active", True):
            if not _other_active_admin_exists(uid):
                raise UserAdminError(
                    "마지막 admin 계정은 비활성화할 수 없습니다.\n"
                    "다른 계정을 admin으로 지정한 뒤 다시 시도하세요."
                )
    fb_auth.update_user(uid, disabled=(not active))
    _db().collection("users").document(uid).update({
        "active": bool(active),
        "updated_at": datetime.datetime.utcnow(),
    })


def delete_user(uid: str):
    """Auth + Firestore 양쪽 삭제. 본인 계정 삭제 차단은 호출자 책임.
    마지막 active admin 삭제는 차단.
    """
    target = _db().collection("users").document(uid).get().to_dict() or {}
    if target.get("role") == "admin" and target.get("active", True):
        if not _other_active_admin_exists(uid):
            raise UserAdminError(
                "마지막 admin 계정은 삭제할 수 없습니다.\n"
                "다른 계정을 admin으로 지정한 뒤 다시 시도하세요."
            )
    try:
        fb_auth.delete_user(uid)
    except fb_auth.UserNotFoundError:
        pass
    try:
        _db().collection("users").document(uid).delete()
    except Exception:
        pass


def update_role(uid: str, role: str):
    """role 변경: admin <-> user.
    마지막 active admin을 user로 강등하는 것은 차단.
    """
    if role not in ("admin", "user"):
        raise UserAdminError("role은 admin 또는 user 여야 합니다.")
    if role == "user":
        target = _db().collection("users").document(uid).get().to_dict() or {}
        if target.get("role") == "admin" and target.get("active", True):
            if not _other_active_admin_exists(uid):
                raise UserAdminError(
                    "마지막 admin 계정은 user로 강등할 수 없습니다.\n"
                    "다른 계정을 admin으로 지정한 뒤 다시 시도하세요."
                )
    _db().collection("users").document(uid).update({
        "role": role,
        "updated_at": datetime.datetime.utcnow(),
    })
