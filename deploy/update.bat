@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  Auto-pull poller: git fetch -> if upstream ahead -> pull + restart
REM  Safe to run as scheduled task (no pause, no stdout).
REM  Manual run: run from cmd; see logs\autopull.log for output.
REM
REM  RESTART MODEL (important):
REM   The real server runs via start_server.bat in the Q user's interactive
REM   desktop (HWP COM needs a real WindowStation; a Windows Service breaks it).
REM   So we do NOT restart any service. Instead we KILL the uvicorn process
REM   listening on SERVER_PORT; start_server.bat's loop then auto-relaunches it
REM   with the freshly pulled code (== same effect as a manual Ctrl+C).
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set SERVER_PORT=8000
set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe
set LOG_FILE=%CLONE_DIR%\logs\autopull.log
set MAX_LOG_BYTES=1048576

REM -c safe.directory=... bypasses "dubious ownership" when running as SYSTEM.
set GIT_OPTS=-c safe.directory=C:/sangsung/problem-bank-2

cd /d "%CLONE_DIR%" || exit /b 1

if not exist "%CLONE_DIR%\logs" mkdir "%CLONE_DIR%\logs"

REM Rotate log when over 1 MB (keep one .old backup)
if exist "%LOG_FILE%" (
    for %%I in ("%LOG_FILE%") do set LOG_SIZE=%%~zI
    if !LOG_SIZE! gtr %MAX_LOG_BYTES% (
        if exist "%LOG_FILE%.old" del "%LOG_FILE%.old"
        ren "%LOG_FILE%" autopull.log.old
    )
)

REM Timestamp (locale-dependent; good enough for log lines)
set TS=%date% %time:~0,8%

REM Fetch upstream silently
git %GIT_OPTS% fetch --quiet 2>>"%LOG_FILE%"
if errorlevel 1 (
    echo [!TS!] [ERROR] git fetch failed >> "%LOG_FILE%"
    exit /b 1
)

for /f %%I in ('git %GIT_OPTS% rev-parse HEAD') do set LOCAL_SHA=%%I
for /f %%I in ('git %GIT_OPTS% rev-parse @{u}') do set REMOTE_SHA=%%I

if "!LOCAL_SHA!"=="!REMOTE_SHA!" (
    echo [!TS!] no change ^(HEAD=!LOCAL_SHA:~0,7!^) >> "%LOG_FILE%"
    exit /b 0
)

echo. >> "%LOG_FILE%"
echo [!TS!] === changes detected: !LOCAL_SHA:~0,7! -^> !REMOTE_SHA:~0,7! === >> "%LOG_FILE%"

REM Check whether requirements.txt is among changed files
git %GIT_OPTS% diff --name-only !LOCAL_SHA! !REMOTE_SHA! | findstr /b /c:"requirements.txt" >nul
set REQ_CHANGED=!errorlevel!

git %GIT_OPTS% pull --quiet >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [!TS!] [ERROR] git pull failed >> "%LOG_FILE%"
    exit /b 1
)

if !REQ_CHANGED! equ 0 (
    echo [!TS!] requirements.txt changed - running pip install >> "%LOG_FILE%"
    "%PYTHON_EXE%" -m pip install -r requirements.txt --quiet >>"%LOG_FILE%" 2>&1
)

REM Restart the interactive console server: kill uvicorn on SERVER_PORT.
REM start_server.bat's :restart loop relaunches it with the new code in ~5s.
set KILLED=0
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:":%SERVER_PORT% " ^| findstr /c:"LISTENING"') do (
    echo [!TS!] killing uvicorn pid %%P ^(port %SERVER_PORT%^) >> "%LOG_FILE%"
    taskkill /f /pid %%P >>"%LOG_FILE%" 2>&1
    set KILLED=1
)
if "!KILLED!"=="0" (
    echo [!TS!] [WARN] no LISTENING process on port %SERVER_PORT% - is start_server.bat running? >> "%LOG_FILE%"
)

timeout /t 6 /nobreak >nul
echo [!TS!] post-restart check (expect a LISTENING line): >> "%LOG_FILE%"
netstat -ano | findstr /c:":%SERVER_PORT% " | findstr /c:"LISTENING" >>"%LOG_FILE%" 2>&1

endlocal
exit /b 0
