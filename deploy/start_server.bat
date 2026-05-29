@echo off
chcp 65001 > nul
title ProblemBank2 Server (User Desktop)

REM ============================================================
REM  Run uvicorn in the Q account's interactive desktop so that
REM  HWP COM automation (Hangul/Pyhwpx) can attach to a real
REM  WindowStation. NSSM-as-Service mode breaks HWP because of
REM  Service Window Station isolation.
REM  Place this .bat in the Startup folder for auto-launch.
REM ============================================================

cd /d C:\sangsung\problem-bank-2

set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe

REM ---- Stable session secret -------------------------------------------------
REM  Without a fixed secret, config.py generates a random one each start, which
REM  logs every user out on restart (incl. auto-pull restarts). Store it in a
REM  gitignored local file (.session_secret); auto-generate on first run so it
REM  stays constant across restarts.
set SECRET_FILE=C:\sangsung\problem-bank-2\.session_secret
if not exist "%SECRET_FILE%" (
    echo [%date% %time%] Generating session secret -^> %SECRET_FILE%
    "%PYTHON_EXE%" -c "import secrets;open(r'%SECRET_FILE%','w').write(secrets.token_urlsafe(48))"
)
set /p NAEGIWANGBANK_SESSION_SECRET=<"%SECRET_FILE%"

:restart
echo.
echo [%date% %time%] Starting ProblemBank2 server on port 8000...
echo.
"%PYTHON_EXE%" -m uvicorn server.main:app --host 0.0.0.0 --port 8000
echo.
echo [%date% %time%] Server stopped or crashed. Restarting in 5 seconds...
echo  (Press Ctrl+C now to abort the restart loop.)
timeout /t 5 /nobreak >nul
goto restart
