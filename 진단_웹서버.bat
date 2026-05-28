@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

echo.
echo ============================================================
echo   상승 Solution - 웹 서버 진단
echo ============================================================
echo.

cd /d "G:\문제은행\문제은행2"

REM === 진단 로그 시작 ===
set LOGFILE=진단_웹서버.log
(
    echo [%date% %time%] 진단 시작
    echo.
) > %LOGFILE%

REM === 1. Python ===
echo [진단 1/7] Python 버전...
python --version >> %LOGFILE% 2>&1
for /f "tokens=*" %%A in ('python --version 2^>^&1') do echo   %%A
echo.

REM === 2. Python 경로 ===
echo [진단 2/7] Python 경로...
for /f "tokens=*" %%A in ('where python') do (
    echo   %%A
    echo   %%A >> %LOGFILE%
)
echo.

REM === 3. FastAPI 설치 확인 ===
echo [진단 3/7] FastAPI 설치 확인...
pip show fastapi >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo   [X] FastAPI 미설치
    echo   해결: pip install -r requirements.txt
) else (
    echo   [O] FastAPI 설치됨
)
echo.

REM === 4. Uvicorn 설치 확인 ===
echo [진단 4/7] Uvicorn 설치 확인...
pip show uvicorn >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo   [X] Uvicorn 미설치
    echo   해결: pip install uvicorn
) else (
    echo   [O] Uvicorn 설치됨
)
echo.

REM === 5. Firebase 설치 확인 ===
echo [진단 5/7] Firebase Admin SDK 설치 확인...
pip show firebase-admin >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo   [X] firebase-admin 미설치
    echo   해결: pip install firebase-admin
) else (
    echo   [O] firebase-admin 설치됨
)
echo.

REM === 6. 포트 8000 상태 ===
echo [진단 6/7] 포트 8000 상태...
netstat -ano | findstr :8000 >> %LOGFILE% 2>&1
if errorlevel 0 (
    for /f "tokens=*" %%A in ('netstat -ano ^| findstr :8000 2^>nul') do (
        echo   [!] 포트 8000 사용 중: %%A
    )
) else (
    echo   [O] 포트 8000 사용 가능
)
echo.

REM === 7. server.main 모듈 테스트 ===
echo [진단 7/7] server.main 모듈 import 테스트...
echo.
python -c "from server import main; print('  [O] server.main 정상')" >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo   [X] server.main 모듈 오류
    echo.
    echo   오류 상세:
    python -c "from server import main" 2>&1 | findstr /v "^$"
    echo. >> %LOGFILE%
    echo   [ERROR] server.main import 실패 >> %LOGFILE%
    python -c "from server import main" >> %LOGFILE% 2>&1
) else (
    echo   [O] server.main 정상
)
echo.

REM === 결과 요약 ===
echo ============================================================
echo.
echo 진단 로그: %LOGFILE%
echo (자세한 내용은 위 파일을 확인하세요)
echo.
echo 다음 단계:
echo  1. 위의 [X] 항목들을 해결하세요
echo  2. "서버클라이언트시작.bat" 실행
echo  3. 여전히 안 되면 아래 명령을 수동 실행:
echo.
echo    cd G:\문제은행\문제은행2
echo    python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
echo.
echo ============================================================
echo.
pause

REM === 로그 파일 표시 ===
echo.
echo === %LOGFILE% 내용 ===
type %LOGFILE%
