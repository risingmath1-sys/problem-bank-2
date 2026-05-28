@echo off
setlocal

REM ============================================================
REM  Dev PC: start FastAPI server + open browser
REM  ASCII-only. Uses %~dp0 so the Korean path does not break cmd.
REM ============================================================

cd /d "%~dp0"

if not exist "server\main.py" (
    echo [ERROR] server\main.py not found in %CD%
    pause
    exit /b 1
)

set NAEGIWANGBANK_SESSION_SECRET=dev-secret-CHANGE-IN-PRODUCTION

REM Open browser 5 seconds later (parallel)
start "" /min cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:8000"

echo.
echo ============================================================
echo  Starting server on http://localhost:8000
echo  (Ctrl+C in this window to stop)
echo ============================================================
echo.

python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo Server stopped.
pause
endlocal
