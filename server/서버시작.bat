@echo off
setlocal

REM ASCII-only; %~dp0 avoids the Korean path tripping up the cmd parser.
cd /d "%~dp0.."

echo.
echo Starting server on port 8000 (Ctrl+C to stop)
echo.

set NAEGIWANGBANK_SESSION_SECRET=dev-secret-CHANGE-IN-PRODUCTION
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo Server stopped.
pause
endlocal
