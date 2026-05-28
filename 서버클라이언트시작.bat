@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

echo.
echo ============================================================
echo   상승 Solution - 서버/클라이언트 통합 시작
echo   (2026-05-13 업데이트)
echo ============================================================
echo.

cd /d "G:\문제은행\문제은행2"

REM === 1. Python 확인 ===
echo [1/5] Python 설치 확인...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python을 찾을 수 없습니다.
    echo.
    echo 해결방법:
    echo  1. Python 3.9+ 설치: https://www.python.org/downloads/
    echo  2. 설치 시 "Add Python to PATH" 체크
    echo  3. 컴퓨터 재시작 후 다시 실행
    echo.
    pause
    exit /b 1
)
python --version
echo [OK] Python 설치됨
echo.

REM === 2. 의존성 확인 및 설치 ===
echo [2/5] 의존성 확인 및 설치...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [설치] requirements.txt 에서 패키지 설치 중...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] 의존성 설치 실패
        echo.
        echo 해결방법:
        echo  - 관리자 권한으로 명령 프롬프트 재실행
        echo  - 또는 수동 설치: pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
) else (
    echo [OK] 의존성 이미 설치됨
)
echo.

REM === 3. Firebase 키 확인 ===
echo [3/5] Firebase 키 파일 확인...
if not exist "backend\firebase_init.py" (
    echo [WARNING] backend\firebase_init.py 를 찾을 수 없습니다.
    echo 로그인 기능이 작동하지 않을 수 있습니다.
    echo.
)
echo.

REM === 4. server.main 모듈 확인 ===
echo [4/5] 서버 모듈 확인...
if not exist "server\main.py" (
    echo [ERROR] server\main.py 를 찾을 수 없습니다.
    echo 현재 디렉토리: %CD%
    echo.
    pause
    exit /b 1
)
echo [OK] 서버 모듈 정상
echo.

REM === 5. 서버 시작 ===
echo [5/5] 서버 시작 (포트 8000)...
echo.

set NAEGIWANGBANK_SESSION_SECRET=dev-secret-CHANGE-IN-PRODUCTION

start "상승 Solution 서버 (포트 8000)" cmd /k ^
    python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

echo [대기] 서버 부팅 중... (5초)
timeout /t 5 /nobreak

REM === 브라우저 실행 ===
echo.
echo [브라우저] http://localhost:8000 열기...
start http://localhost:8000

echo.
echo ============================================================
echo  ✓ 서버 시작 완료!
echo.
echo  - 브라우저: http://localhost:8000
echo  - 서버 종료: 검은색 서버 창에서 Ctrl+C
echo.
echo  문제 발생 시:
echo    1. 포트 8000 충돌 → 8000 포트 사용 중인 프로세스 확인/종료
echo    2. 에러 창 → 검은색 서버 창의 에러 메시지 확인
echo    3. 브라우저 접속 안 됨 → "진단.bat" 실행
echo ============================================================
echo.
pause
