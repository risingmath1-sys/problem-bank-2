"""서버 설정 — 환경변수 + 경로."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DATA_DIR = BASE_DIR / "server_data"
EXAM_RESULTS_DIR = SERVER_DATA_DIR / "exam_results"
LOGS_DIR = SERVER_DATA_DIR / "logs"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

EXAM_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("NAEGIWANGBANK_HOST", "0.0.0.0")
PORT = int(os.environ.get("NAEGIWANGBANK_PORT", "8000"))

# 세션 JWT 비밀키. 환경변수 미설정 시 임시 생성 (재시작 시 모든 세션 무효 — 운영에선 반드시 환경변수 설정).
SESSION_SECRET = os.environ.get("NAEGIWANGBANK_SESSION_SECRET")
if not SESSION_SECRET:
    SESSION_SECRET = secrets.token_urlsafe(48)
    print("[config] WARNING: NAEGIWANGBANK_SESSION_SECRET 미설정 - 임시 키 생성. 재시작 시 모든 세션 무효.")

SESSION_COOKIE_NAME = "ngwb_session"
SESSION_TTL_SECONDS = 24 * 60 * 60  # 24시간
EXAM_RESULT_TTL_SECONDS = 24 * 60 * 60  # 출제 결과 24시간 보관

# HWP 원본 파일 루트 (settings.json source_hwp_dir 와 동일 역할).
# 우선순위: 환경변수 → settings.json → BASE_DIR/exercise
def _resolve_source_root() -> Path:
    env = os.environ.get("NAEGIWANGBANK_HWP_SOURCE_DIR")
    if env:
        return Path(env)
    settings = BASE_DIR / "settings.json"
    if settings.exists():
        try:
            import json
            with open(settings, "r", encoding="utf-8") as f:
                data = json.load(f)
            v = data.get("source_hwp_dir")
            if v:
                return Path(v)
        except Exception:
            pass
    return BASE_DIR / "exercise"

HWP_SOURCE_ROOT = _resolve_source_root()
