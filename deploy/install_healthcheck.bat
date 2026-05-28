@echo off
setlocal

REM ============================================================
REM  Register ProblemBank2_HealthCheck scheduled task (5 min poll)
REM  Requires: Administrator privileges
REM ============================================================

set TASK_NAME=ProblemBank2_HealthCheck
set HEALTHCHECK_BAT=C:\sangsung\problem-bank-2\deploy\healthcheck.bat

REM Admin check
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run as Administrator.
    echo   Right-click this .bat and choose "Run as administrator".
    pause
    exit /b 1
)

if not exist "%HEALTHCHECK_BAT%" (
    echo [ERROR] healthcheck.bat not found at: %HEALTHCHECK_BAT%
    pause
    exit /b 1
)

REM Remove existing task if present (idempotent)
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Removing existing task: %TASK_NAME%
    schtasks /delete /tn "%TASK_NAME%" /f
)

REM Register: every 5 min, SYSTEM (needed for nssm restart), HIGHEST
echo [INFO] Registering scheduled task: %TASK_NAME%
schtasks /create /tn "%TASK_NAME%" /tr "cmd /c \"%HEALTHCHECK_BAT%\"" /sc minute /mo 5 /ru SYSTEM /rl HIGHEST /f
if errorlevel 1 (
    echo [ERROR] schtasks create failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Scheduled task registered
echo ============================================================
echo   Task name:    %TASK_NAME%
echo   Interval:     every 5 minutes
echo   Runs as:      SYSTEM (highest)
echo   Command:      %HEALTHCHECK_BAT%
echo   Log file:     C:\sangsung\problem-bank-2\logs\healthcheck.log
echo   Restart rule: after 2 consecutive failed /healthz checks
echo.
echo  Management commands:
echo    schtasks /query  /tn "%TASK_NAME%" /v /fo LIST   :: detailed status
echo    schtasks /run    /tn "%TASK_NAME%"               :: run once now
echo    schtasks /delete /tn "%TASK_NAME%" /f            :: remove
echo.
echo  Watch log live (in any cmd):
echo    powershell -Command "Get-Content C:\sangsung\problem-bank-2\logs\healthcheck.log -Wait -Tail 20"
echo.
echo  Run the first check immediately?
choice /c YN /n /m "Press Y to run now, N to wait 5 minutes: "
if errorlevel 2 goto :done
schtasks /run /tn "%TASK_NAME%"
timeout /t 3 /nobreak >nul
echo.
echo [INFO] Initial run triggered. Check log to verify.

:done
echo.
pause
endlocal
