@echo off
setlocal

REM ============================================================
REM  Problem Bank 2 - Mini PC One-Time Setup
REM  Run this on the mini PC via RDP cmd
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe
set REPO_URL=https://github.com/risingmath1-sys/problem-bank-2.git

echo.
echo ============================================================
echo  [1/5] Prerequisite check
echo ============================================================

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git is not installed.
    echo   Install from: https://git-scm.com/download/win
    pause
    exit /b 1
)
echo [OK] git found

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at: %PYTHON_EXE%
    pause
    exit /b 1
)
echo [OK] Python found

if not exist "C:\sangsung" mkdir "C:\sangsung"

echo.
echo ============================================================
echo  [2/5] Repository clone / pull
echo ============================================================

if exist "%CLONE_DIR%\.git" (
    echo [INFO] Already cloned. Running git pull.
    cd /d "%CLONE_DIR%"
    git pull
) else (
    echo [INFO] Cloning repository...
    cd /d C:\sangsung
    git clone %REPO_URL% problem-bank-2
    if errorlevel 1 (
        echo [ERROR] git clone failed
        pause
        exit /b 1
    )
)

cd /d "%CLONE_DIR%"

echo.
echo ============================================================
echo  [3/5] Install Python packages
echo ============================================================

"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)
echo [OK] Packages installed

echo.
echo ============================================================
echo  [4/5] Create logs folder
echo ============================================================
if not exist "%CLONE_DIR%\logs" mkdir "%CLONE_DIR%\logs"
echo [OK] logs folder ready

echo.
echo ============================================================
echo  [5/5] Next steps
echo ============================================================
echo.
echo  Manual copy required for sensitive files:
echo.
echo    Copy these files from your PC to %CLONE_DIR% :
echo      - firebase-key.json
echo      - problem_bank.db
echo.
echo    Use network share, USB, or RDP clipboard.
echo.
echo  After copying, run nssm_install.bat to register the service.
echo.
echo ============================================================
pause
endlocal
