# -*- coding: utf-8 -*-
"""
Phase 2-G: Firestore Security Rules 배포 스크립트

설계도: 로그인시스템설계도.md §3-2, §4 (이중 잠금)
입력: ./firestore.rules
출력: Firebase 프로젝트 'naegiwangbank' 의 cloud.firestore 릴리스 갱신

Firebase CLI (npm + 브라우저 OAuth) 없이, 이미 보유한 서비스 계정 키로
Firebase Rules REST API 를 직접 호출한다 → 완전 자동화 + 재현 가능.

API 흐름:
  1) POST /v1/projects/{pid}/rulesets         → 새 ruleset 생성 (이름 = projects/.../rulesets/UUID)
  2) PATCH /v1/projects/{pid}/releases/cloud.firestore → 그 ruleset 을 라이브 릴리스로 교체

사용법:
  python deploy_firestore_rules.py            # 배포
  python deploy_firestore_rules.py --dry-run  # 인증/룰 파싱만 확인 (rulesets 만 만들고 release 안함)
  python deploy_firestore_rules.py --status   # 현재 라이브 릴리스 확인
"""
import argparse
import json
import os
import sys

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

PROJECT_ID = "naegiwangbank"
RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firestore.rules")


def _resolve_service_account_path() -> str:
    """admin SDK 키 경로 — firebase_init 의 우선순위 탐색에 위임 (Phase 2)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from backend.firebase_init import find_key_path
    return find_key_path()


SERVICE_ACCOUNT = _resolve_service_account_path()

SCOPES = [
    "https://www.googleapis.com/auth/firebase",
    "https://www.googleapis.com/auth/cloud-platform",
]

API_BASE = "https://firebaserules.googleapis.com/v1"
RELEASE_NAME = f"projects/{PROJECT_ID}/releases/cloud.firestore"


def get_access_token():
    if not os.path.exists(SERVICE_ACCOUNT):
        sys.exit(f"[FAIL] 서비스 계정 키 없음: {SERVICE_ACCOUNT}")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT, scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token


def auth_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


def read_rules():
    if not os.path.exists(RULES_FILE):
        sys.exit(f"[FAIL] 규칙 파일 없음: {RULES_FILE}")
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return f.read()


def create_ruleset(token, source):
    url = f"{API_BASE}/projects/{PROJECT_ID}/rulesets"
    payload = {
        "source": {
            "files": [
                {"name": "firestore.rules", "content": source}
            ]
        }
    }
    resp = requests.post(url, headers=auth_headers(token), json=payload, timeout=30)
    if resp.status_code >= 300:
        sys.exit(f"[FAIL] ruleset 생성 실패 ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data["name"]  # e.g. projects/naegiwangbank/rulesets/UUID


def get_release(token):
    """현재 cloud.firestore 릴리스 정보."""
    url = f"{API_BASE}/{RELEASE_NAME}"
    resp = requests.get(url, headers=auth_headers(token), timeout=15)
    if resp.status_code == 404:
        return None
    if resp.status_code >= 300:
        sys.exit(f"[FAIL] release 조회 실패 ({resp.status_code}): {resp.text}")
    return resp.json()


def update_release(token, ruleset_name):
    """기존 릴리스가 있으면 PATCH, 없으면 POST."""
    existing = get_release(token)
    body = {
        "release": {
            "name": RELEASE_NAME,
            "rulesetName": ruleset_name,
        }
    }
    if existing is None:
        # create
        url = f"{API_BASE}/projects/{PROJECT_ID}/releases"
        resp = requests.post(
            url, headers=auth_headers(token),
            json=body["release"], timeout=15,
        )
    else:
        # 기존 릴리스 갱신: PATCH /v1/{release.name=projects/*/releases/**}
        # body 는 UpdateReleaseRequest = { "release": Release, "updateMask": ... }
        url = f"{API_BASE}/{RELEASE_NAME}"
        resp = requests.patch(
            url, headers=auth_headers(token),
            json={
                "release": {"name": RELEASE_NAME, "rulesetName": ruleset_name},
                "updateMask": "rulesetName",
            },
            timeout=15,
        )
    if resp.status_code >= 300:
        sys.exit(f"[FAIL] release 갱신 실패 ({resp.status_code}): {resp.text}")
    return resp.json()


def cmd_status():
    token = get_access_token()
    rel = get_release(token)
    if rel is None:
        print("현재 cloud.firestore 릴리스 없음 (배포 이력 없음)")
        return
    print(json.dumps(rel, indent=2, ensure_ascii=False))


def cmd_deploy(dry_run=False):
    source = read_rules()
    print(f"[1/3] rules 파일 읽음: {RULES_FILE} ({len(source)} chars)")

    token = get_access_token()
    print("[2/3] 서비스 계정 토큰 획득 OK")

    ruleset_name = create_ruleset(token, source)
    print(f"[3/3] ruleset 생성됨: {ruleset_name}")

    if dry_run:
        print("--dry-run: release 갱신 생략 (rules 파싱은 통과)")
        return

    rel = update_release(token, ruleset_name)
    print(f"[OK] cloud.firestore 릴리스 갱신: {rel.get('name')}")
    print(f"     -> rulesetName = {rel.get('rulesetName')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="ruleset 만 생성, release 안건드림")
    ap.add_argument("--status", action="store_true", help="현재 라이브 릴리스 조회")
    args = ap.parse_args()

    if args.status:
        cmd_status()
    else:
        cmd_deploy(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
