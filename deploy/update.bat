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

REM Capture HEAD before pull (for requirements diff + restart decision).
REM NOTE: do NOT gate on rev-parse SHA comparison. Under the SYSTEM scheduled
REM task, the old "rev-parse HEAD vs @{u}" returned empty -> ""=="" -> the script
REM always logged "no change" and NEVER pulled (mini PC stuck on old code).
REM Instead we run the pull and read its own output to decide.
set BEFORE_SHA=
for /f "delims=" %%I in ('git %GIT_OPTS% rev-parse HEAD 2^>nul') do set BEFORE_SHA=%%I

set PULL_OUT=%CLONE_DIR%\logs\_pull_out.txt
git %GIT_OPTS% pull --ff-only > "%PULL_OUT%" 2>&1
set PULL_RC=!errorlevel!
type "%PULL_OUT%" >> "%LOG_FILE%"
if not "!PULL_RC!"=="0" (
    echo [!TS!] [ERROR] git pull failed ^(rc=!PULL_RC!^) >> "%LOG_FILE%"
    del "%PULL_OUT%" >nul 2>&1
    exit /b 1
)

REM "Already up to date" (any case) => nothing changed, done.
findstr /i /c:"up to date" "%PULL_OUT%" >nul
if not errorlevel 1 (
    echo [!TS!] no change ^(HEAD=!BEFORE_SHA:~0,7!^) >> "%LOG_FILE%"
    del "%PULL_OUT%" >nul 2>&1
    exit /b 0
)
del "%PULL_OUT%" >nul 2>&1

set AFTER_SHA=
for /f "delims=" %%I in ('git %GIT_OPTS% rev-parse HEAD 2^>nul') do set AFTER_SHA=%%I
echo. >> "%LOG_FILE%"
echo [!TS!] === updated: !BEFORE_SHA:~0,7! -^> !AFTER_SHA:~0,7! === >> "%LOG_FILE%"

REM Check whether requirements.txt changed (only if both SHAs known).
set REQ_CHANGED=1
if not "!BEFORE_SHA!"=="" if not "!AFTER_SHA!"=="" (
    git %GIT_OPTS% diff --name-only !BEFORE_SHA! !AFTER_SHA! | findstr /b /c:"requirements.txt" >nul
    set REQ_CHANGED=!errorlevel!
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
