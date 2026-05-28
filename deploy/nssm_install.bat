@echo off
setlocal

REM ============================================================
REM  Register Problem Bank 2 SC server as a Windows service via NSSM
REM  Requires: Administrator privileges
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe
set SERVICE_NAME=ProblemBank2
set PORT=8000

REM Admin check
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run as Administrator.
    echo   Right-click this .bat file and select "Run as administrator".
    pause
    exit /b 1
)

REM NSSM check
where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] NSSM is not installed.
    echo.
    echo  How to install:
    echo   1. Download: https://nssm.cc/release/nssm-2.24.zip
    echo   2. Unzip and copy win64\nssm.exe to C:\Windows\System32
    echo   3. Or place nssm.exe in the same folder as this .bat and rerun
    pause
    exit /b 1
)
echo [OK] NSSM found

REM SESSION_SECRET (generate once, then reuse)
set SECRET_FILE=%CLONE_DIR%\.session_secret
if not exist "%SECRET_FILE%" (
    echo [INFO] Generating new SESSION_SECRET
    powershell -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')" > "%SECRET_FILE%"
)
set /p SESSION_SECRET=<"%SECRET_FILE%"
echo [OK] SESSION_SECRET ready

REM Remove existing service (if any)
echo.
echo [INFO] Cleaning up existing service (if present)
nssm stop %SERVICE_NAME% 2>nul
nssm remove %SERVICE_NAME% confirm 2>nul

REM Register service
echo.
echo [INFO] Registering service
nssm install %SERVICE_NAME% "%PYTHON_EXE%" "-m uvicorn server.main:app --host 0.0.0.0 --port %PORT% --workers 1"
nssm set %SERVICE_NAME% AppDirectory "%CLONE_DIR%"
nssm set %SERVICE_NAME% DisplayName "Problem Bank 2 (SC Server)"
nssm set %SERVICE_NAME% Description "FastAPI server for problem-bank-2 (port %PORT%)"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% AppStdout "%CLONE_DIR%\logs\stdout.log"
nssm set %SERVICE_NAME% AppStderr "%CLONE_DIR%\logs\stderr.log"
nssm set %SERVICE_NAME% AppRotateFiles 1
nssm set %SERVICE_NAME% AppRotateBytes 10485760
nssm set %SERVICE_NAME% AppEnvironmentExtra "NAEGIWANGBANK_SESSION_SECRET=%SESSION_SECRET%" "DATA_ENGINE=sqlite"
nssm set %SERVICE_NAME% AppExit Default Restart
nssm set %SERVICE_NAME% AppRestartDelay 5000

echo.
echo [INFO] Starting service
nssm start %SERVICE_NAME%
timeout /t 3 /nobreak >nul

echo.
echo ============================================================
echo  Service registration complete
echo ============================================================
nssm status %SERVICE_NAME%
echo.
echo  Service:    %SERVICE_NAME%
echo  Port:       %PORT%
echo  URL:        http://192.168.0.139:%PORT%
echo  Logs:       %CLONE_DIR%\logs\
echo.
echo  Management commands:
echo    nssm status   %SERVICE_NAME%
echo    nssm restart  %SERVICE_NAME%
echo    nssm stop     %SERVICE_NAME%
echo    nssm start    %SERVICE_NAME%
echo    nssm edit     %SERVICE_NAME%
echo.
echo ============================================================
pause
endlocal
