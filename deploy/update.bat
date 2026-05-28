@echo off
setlocal

REM ============================================================
REM  git pull + restart service (deploy update)
REM  Run on mini PC after a git push from the dev PC
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set SERVICE_NAME=ProblemBank2
set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe

cd /d "%CLONE_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot change directory: %CLONE_DIR%
    pause
    exit /b 1
)

echo [INFO] Current commit:
git log -1 --oneline

echo.
echo [INFO] Running git pull
git pull
if errorlevel 1 (
    echo [ERROR] git pull failed
    pause
    exit /b 1
)

echo.
echo [INFO] Updating packages (if changed)
"%PYTHON_EXE%" -m pip install -r requirements.txt --quiet

echo.
echo [INFO] Restarting service: %SERVICE_NAME%
nssm restart %SERVICE_NAME%
timeout /t 3 /nobreak >nul

echo.
echo [INFO] Service status:
nssm status %SERVICE_NAME%

echo.
echo [OK] Update complete
echo  URL: http://192.168.0.139:8000
echo.
endlocal
