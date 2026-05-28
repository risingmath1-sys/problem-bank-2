"""
문제은행 FastAPI 웹 서버 (2026-05-02)
solutio.risingmath.kr에서 실행
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 프로젝트 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.firebase_init import init_firebase
from backend.auth import verify_token
from backend.firestore_engine import FirestoreEngine
from backend.hwp_generator import HWPQuestionGenerator
from backend.hwp_core import HWPCoreAutomation

# Firebase 초기화
init_firebase()
firestore = FirestoreEngine()

# FastAPI 앱 생성
app = FastAPI(title="문제은행 웹 서버", version="1.0.0")

# CORS 설정 (나중에 solutio.risingmath.kr 도메인만 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 중: 모두 허용, 프로덕션에서 변경
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 경로 설정 (나중에 CSS, JS 추가)
static_dir = PROJECT_ROOT / "frontend" / "static"
if not static_dir.exists():
    static_dir.mkdir(parents=True, exist_ok=True)

try:
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
except Exception as e:
    print(f"⚠️ 정적 파일 마운트 오류 (무시해도 됨): {e}")

# ============================================================
# 1. 인증 & 홈 페이지
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home():
    """홈 페이지"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>문제은행 - 로그인</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                   max-width: 600px; margin: 100px auto; padding: 20px; }
            .login-box { border: 1px solid #ddd; padding: 30px; border-radius: 8px; }
            button { background: #007bff; color: white; padding: 10px 20px; border: none;
                     border-radius: 4px; cursor: pointer; font-size: 16px; }
            button:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>내기왕 문제은행 (웹)</h1>
            <p>Firebase 인증으로 로그인하세요.</p>
            <button onclick="signIn()">Google로 로그인</button>
        </div>
        <script src="/__/firebase/init.js"></script>
        <script>
            function signIn() {
                alert('Firebase 인증 준비 중입니다.');
                // TODO: Firebase Auth UI 연결
            }
        </script>
    </body>
    </html>
    """

@app.get("/api/auth/status")
async def auth_status(request: Request):
    """인증 상태 확인"""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="미인증")

    try:
        token = auth_header.split(" ")[1]
        user_id = verify_token(token)
        return {"authenticated": True, "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# ============================================================
# 2. 문제 검색 & 조회 API
# ============================================================

@app.get("/api/problems")
async def get_problems(
    source: str = None,
    subject: str = None,
    year: int = None,
    limit: int = 50,
    offset: int = 0,
    request: Request = None
):
    """문제 목록 조회 (필터 포함)"""
    try:
        # TODO: Firebase Firestore에서 필터된 문제 조회
        problems = firestore.get_problems(
            source=source,
            subject=subject,
            year=year,
            limit=limit,
            offset=offset
        )
        return {"problems": problems, "total": len(problems)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/problems/{problem_id}")
async def get_problem(problem_id: str):
    """단일 문제 조회"""
    try:
        problem = firestore.get_problem(problem_id)
        if not problem:
            raise HTTPException(status_code=404, detail="문제를 찾을 수 없습니다")
        return problem
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# 3. 출제 API (HWP 생성)
# ============================================================

@app.post("/api/generate/random")
async def generate_random_test(request: Request):
    """랜덤 출제 (JSON 요청)"""
    try:
        payload = await request.json()
        num_problems = payload.get("num_problems", 10)
        filters = payload.get("filters", {})

        # HWP 생성 로직 호출
        result = await generate_hwp_file(
            num_problems=num_problems,
            filters=filters,
            test_name="랜덤출제"
        )

        return {"success": True, "download_url": result["file_url"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate/original")
async def generate_original_test(request: Request):
    """원본출제 (소스 파일에서)"""
    try:
        payload = await request.json()
        source = payload.get("source")
        problem_ids = payload.get("problem_ids", [])

        result = await generate_hwp_file(
            problem_ids=problem_ids,
            test_name="원본출제"
        )

        return {"success": True, "download_url": result["file_url"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# 4. 출제 결과 다운로드
# ============================================================

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """HWP 파일 다운로드"""
    try:
        # TODO: 보안: filename 검증 (경로 조작 방지)
        file_path = PROJECT_ROOT / "output" / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/octet-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# 5. 헬스 체크
# ============================================================

@app.get("/api/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }

# ============================================================
# 헬퍼 함수
# ============================================================

async def generate_hwp_file(num_problems=None, problem_ids=None, filters=None, test_name="출제"):
    """HWP 파일 생성 공통 로직"""
    try:
        # TODO: hwp_generator.py와 통합
        output_dir = PROJECT_ROOT / "output"
        output_dir.mkdir(exist_ok=True)

        filename = f"{test_name}_{__import__('time').time()}.hwp"
        file_path = output_dir / filename

        # 현재는 스텁. 실제 구현은 hwp_generator와 통합
        return {
            "file_url": f"/api/download/{filename}",
            "file_path": str(file_path)
        }
    except Exception as e:
        raise Exception(f"HWP 생성 실패: {e}")

# ============================================================
# 메인 실행
# ============================================================

if __name__ == "__main__":
    print("🚀 문제은행 웹 서버 시작...")
    print("📍 로컬: http://localhost:8000")
    print("🌐 웹: https://solutio.risingmath.kr (DNS 적용 후)")

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,  # 개발 중: 자동 재시작
        log_level="info"
    )
