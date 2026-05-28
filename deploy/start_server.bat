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

:restart
echo.
echo [%date% %time%] Starting ProblemBank2 server on port 8000...
echo.
C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000
echo.
echo [%date% %time%] Server stopped or crashed. Restarting in 5 seconds...
echo  (Press Ctrl+C now to abort the restart loop.)
timeout /t 5 /nobreak >nul
goto restart
