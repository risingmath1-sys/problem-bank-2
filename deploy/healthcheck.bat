@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  Health-check watchdog: hits /healthz, restarts service after
REM  2 consecutive failures. Safe to run as scheduled task (SYSTEM).
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set SERVICE_NAME=ProblemBank2
set NSSM=C:\sangsung\problem-bank-2\deploy\nssm.exe
set HEALTH_URL=http://localhost:8000/healthz
set LOG_FILE=%CLONE_DIR%\logs\healthcheck.log
set FAIL_COUNT_FILE=%CLONE_DIR%\logs\.fail_count
set MAX_LOG_BYTES=1048576
set MAX_FAIL=2

if not exist "%CLONE_DIR%\logs" mkdir "%CLONE_DIR%\logs"

REM Rotate log when over 1 MB (keep one .old backup)
if exist "%LOG_FILE%" (
    for %%I in ("%LOG_FILE%") do set LOG_SIZE=%%~zI
    if !LOG_SIZE! gtr %MAX_LOG_BYTES% (
        if exist "%LOG_FILE%.old" del "%LOG_FILE%.old"
        ren "%LOG_FILE%" healthcheck.log.old
    )
)

set TS=%date% %time:~0,8%

REM Read previous consecutive-fail counter (default 0)
set FAILS=0
if exist "%FAIL_COUNT_FILE%" (
    for /f "usebackq" %%I in ("%FAIL_COUNT_FILE%") do set FAILS=%%I
)

REM Probe /healthz: -f fails on HTTP >=400, -s silent, -m 5 = 5 sec timeout
curl -sf -m 5 -o NUL "%HEALTH_URL%"
if errorlevel 1 (
    set /a FAILS=!FAILS! + 1
    echo !FAILS!> "%FAIL_COUNT_FILE%"
    echo [!TS!] healthcheck FAIL ^(consecutive=!FAILS!^) >> "%LOG_FILE%"

    if !FAILS! geq %MAX_FAIL% (
        echo [!TS!] reached %MAX_FAIL% consecutive failures - restarting %SERVICE_NAME% >> "%LOG_FILE%"
        "%NSSM%" restart %SERVICE_NAME% >>"%LOG_FILE%" 2>&1
        echo 0> "%FAIL_COUNT_FILE%"
        timeout /t 3 /nobreak >nul
        echo [!TS!] post-restart status: >> "%LOG_FILE%"
        "%NSSM%" status %SERVICE_NAME% >>"%LOG_FILE%" 2>&1
    )
) else (
    if !FAILS! gtr 0 (
        echo [!TS!] healthcheck OK ^(recovered from !FAILS! fails^) >> "%LOG_FILE%"
        echo 0> "%FAIL_COUNT_FILE%"
    ) else (
        echo [!TS!] healthcheck OK >> "%LOG_FILE%"
    )
)

endlocal
exit /b 0
