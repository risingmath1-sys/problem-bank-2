# -*- coding: utf-8 -*-
"""Firebase Admin SDK 키 파일 탐색 + 초기화.

Phase 2: 키를 .exe 번들에 포함시키지 않기 위해 외부 경로에서 탐색.

탐색 우선순위:
  1. 환경변수 NAEGIWANGBANK_FIREBASE_KEY 가 가리키는 파일
  2. .exe 와 같은 폴더 (sys.executable 기준 — frozen 모드)
     dev 모드에서는 프로젝트 루트
  3. %APPDATA%\\naegiwangbank\\firebase-key.json (사용자별 위치)
  4. backend/<adminsdk>.json (구버전 호환 — dev 모드 / 마이그레이션 전)

키가 발견되지 않으면 KeyNotFoundError 발생 → 호출자가 사용자에게 명확한 안내 표시.

배포 시나리오:
  - 일반 사용자: .exe 옆에 키 파일을 둔 zip 으로 배포 (관리자가 1회 전달)
  - 관리자(개발자): %APPDATA%\\naegiwangbank\\firebase-key.json 으로 1회 이전 후 dev/exe 모두 자동 탐색

향후 Phase 6 (REST 전환) 시 이 모듈은 admin SDK 가 정말 필요한 경우(user_admin.py)
한정으로만 호출되고, 일반 사용자 흐름은 REST 클라이언트로 대체된다.
"""
import os
import sys
import glob

KEY_FILENAME_PATTERN = "naegiwangbank-firebase-adminsdk-*.json"
ENV_VAR = "NAEGIWANGBANK_FIREBASE_KEY"
DEFAULT_USER_KEY = "firebase-key.json"


class KeyNotFoundError(Exception):
    """Admin SDK 키 파일을 찾지 못함. 사용자에게 표시할 메시지를 담음."""
    pass


def _candidate_dirs() -> list:
    """키 파일을 탐색할 후보 디렉토리 목록 (우선순위 순)."""
    dirs = []
    # 1. .exe 옆 (frozen) / 프로젝트 루트 (dev)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
    else:
        # main_gui.py 의 base_dir 와 동일 (프로젝트 루트)
        dirs.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 2. %APPDATA%\naegiwangbank\
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    dirs.append(os.path.join(appdata, "naegiwangbank"))

    # 3. backend/ (구버전 호환)
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    return dirs


def find_key_path() -> str:
    """우선순위에 따라 키 파일 경로를 결정. 없으면 KeyNotFoundError."""
    # 0. 환경변수 우선
    env_path = os.environ.get(ENV_VAR)
    if env_path:
        if os.path.exists(env_path):
            return env_path
        raise KeyNotFoundError(
            f"환경변수 {ENV_VAR} 가 가리키는 파일이 없습니다:\n  {env_path}"
        )

    tried = []
    for d in _candidate_dirs():
        # (a) 정해진 이름 firebase-key.json
        cand = os.path.join(d, DEFAULT_USER_KEY)
        tried.append(cand)
        if os.path.exists(cand):
            return cand
        # (b) adminsdk 패턴
        for match in glob.glob(os.path.join(d, KEY_FILENAME_PATTERN)):
            return match
        tried.append(os.path.join(d, KEY_FILENAME_PATTERN))

    raise KeyNotFoundError(
        "Firebase 인증 키 파일을 찾을 수 없습니다.\n\n"
        "다음 위치 중 한 곳에 키 파일을 두세요:\n"
        + "\n".join(f"  · {p}" for p in tried[:6])
        + "\n\n관리자에게 키 파일을 요청하세요."
    )


def init_admin_sdk():
    """firebase_admin 초기화. 이미 초기화돼 있으면 no-op.

    반환: 키 파일 경로 (디버그/로그용)
    예외: KeyNotFoundError, 그 외 firebase_admin 자체 예외
    """
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        return None  # 이미 초기화됨

    key_path = find_key_path()
    firebase_admin.initialize_app(credentials.Certificate(key_path))
    return key_path
