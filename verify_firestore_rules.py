# -*- coding: utf-8 -*-
"""
Phase 2-G 검증: Firestore Security Rules 가 의도대로 작동하는지 확인.

테스트 항목:
  1) Admin SDK (서비스 계정) 로 problems/ 읽기 → 통과 (룰 우회)
  2) 무인증 REST 호출 → 401/403 (거부)
  3) admin 사용자 (admin@sangsung.local) 로 idToken 받아 problems/ 읽기 → 200 (허용)
  4) admin 사용자로 problems/ write → 200 (허용 — admin)
  5) admin 사용자로 자기 users/{uid} 읽기 → 200 (허용)
  6) admin 사용자로 다른 컬렉션 (가상 unknown_col) 읽기 → 403 (default deny)

사용법:
  python verify_firestore_rules.py
"""
import json
import os
import sys
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

PROJECT_ID = "naegiwangbank"
SA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "backend", "naegiwangbank-firebase-adminsdk-fbsvc-5e5e798b33.json")
WEB_API_KEY = "AIzaSyAyn73R7Kj4yFMZPJhCp1FjZMS9Q8NgsNE"
ADMIN_ID = "admin@sangsung.local"
ADMIN_PW = "123456"

FS_BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"


def admin_sdk_test():
    """1) admin SDK 로 problems/ 읽기."""
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SA_PATH))
    db = firestore.client()
    snaps = list(db.collection("problems").limit(1).stream())
    return len(snaps), snaps[0].id if snaps else None


def get_user_id_token(email, password):
    """Firebase Auth REST 로 idToken 발급."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}"
    r = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True}, timeout=10)
    r.raise_for_status()
    return r.json()["idToken"]


def fs_get(path, id_token=None):
    """Firestore REST GET. id_token=None 이면 무인증."""
    url = f"{FS_BASE}/{path}"
    headers = {}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    r = requests.get(url, headers=headers, timeout=10)
    return r.status_code, r.text[:200]


def fs_list(collection, id_token=None, page_size=1):
    url = f"{FS_BASE}/{collection}?pageSize={page_size}"
    headers = {}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    r = requests.get(url, headers=headers, timeout=10)
    return r.status_code, r.text[:200]


def fs_write(collection, doc_id, fields, id_token=None):
    """PATCH = create/update. fields = {key: {valueType: value}}."""
    url = f"{FS_BASE}/{collection}/{doc_id}"
    headers = {"Content-Type": "application/json"}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    r = requests.patch(url, headers=headers, json={"fields": fields}, timeout=10)
    return r.status_code, r.text[:200]


def fs_delete(collection, doc_id, id_token=None):
    url = f"{FS_BASE}/{collection}/{doc_id}"
    headers = {}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    r = requests.delete(url, headers=headers, timeout=10)
    return r.status_code, r.text[:200]


def get_admin_uid():
    import firebase_admin
    from firebase_admin import auth as fb_auth
    return fb_auth.get_user_by_email(ADMIN_ID).uid


def main():
    results = []

    # 1) Admin SDK 우회 read
    try:
        n, doc_id = admin_sdk_test()
        results.append(("1. Admin SDK problems read", "PASS" if n >= 0 else "FAIL", f"{n}건, sample={doc_id}"))
    except Exception as e:
        results.append(("1. Admin SDK problems read", "FAIL", str(e)[:120]))

    # 2) 무인증 REST 호출
    code, body = fs_list("problems")
    ok = code in (401, 403)
    results.append(("2. 무인증 problems list", "PASS" if ok else "FAIL", f"http={code}"))

    # 3) admin idToken 발급
    try:
        admin_token = get_user_id_token(ADMIN_ID, ADMIN_PW)
        results.append(("3a. admin signIn", "PASS", "idToken OK"))
    except Exception as e:
        results.append(("3a. admin signIn", "FAIL", str(e)[:120]))
        admin_token = None

    if admin_token:
        # 3b) admin 으로 problems list
        code, body = fs_list("problems", id_token=admin_token)
        results.append(("3b. admin problems list", "PASS" if code == 200 else "FAIL",
                        f"http={code}"))

        # 4) admin 으로 problems write (테스트 doc → 검증 후 삭제)
        # Firestore 문서 ID 는 __xx__ 패턴 금지 → 일반 ID 사용
        test_doc = "rules_verify_admin_write_TMP"
        code, body = fs_write("problems", test_doc, {"verify_test": {"stringValue": "rules-verify"}}, id_token=admin_token)
        write_ok = code == 200
        results.append(("4. admin problems write", "PASS" if write_ok else "FAIL", f"http={code}"))
        if write_ok:
            d_code, _ = fs_delete("problems", test_doc, id_token=admin_token)
            results.append(("4-cleanup. admin delete test doc", "PASS" if d_code == 200 else "WARN",
                            f"http={d_code}"))

        # 5) admin 자기 users/{uid} 읽기
        try:
            admin_uid = get_admin_uid()
            code, body = fs_get(f"users/{admin_uid}", id_token=admin_token)
            results.append(("5. admin self users read", "PASS" if code == 200 else "FAIL",
                            f"http={code}"))
        except Exception as e:
            results.append(("5. admin self users read", "FAIL", str(e)[:120]))

        # 6) default-deny: 가상 unknown_col 접근
        code, body = fs_list("unknown_collection_xyz", id_token=admin_token)
        deny_ok = code == 403
        # 빈 컬렉션도 200 반환 가능 (existence-independent) → 200이면 룰이 허용한 것 = 문제
        results.append(("6. unknown_col read (default deny)",
                        "PASS" if deny_ok else "FAIL",
                        f"http={code}"))

    # 출력
    print()
    print("=" * 70)
    print("Firestore Security Rules 검증 결과")
    print("=" * 70)
    fail_count = 0
    for name, status, detail in results:
        marker = "[OK] " if status == "PASS" else ("[!!] " if status == "FAIL" else "[~~] ")
        if status == "FAIL":
            fail_count += 1
        print(f"{marker}{name:<40} {status:<5} | {detail}")
    print("=" * 70)
    print(f"총 {len(results)}건 / 실패 {fail_count}건")
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
