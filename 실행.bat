@echo off
title Sangsung Math - Problem Bank
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM === Check python ===
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found in PATH.
    echo Please install Python or add it to PATH.
    echo.
    pause
    exit /b 1
)

REM === Check main_gui.py ===
if not exist "backend\main_gui.py" (
    echo [ERROR] backend\main_gui.py not found in: %CD%
    echo.
    pause
    exit /b 1
)

echo [RUN] python backend\main_gui.py
echo.
chcp 65001 >nul
python backend\main_gui.py
set RC=%ERRORLEVEL%
echo.
echo ==========================================
echo  Exit code: %RC%
echo  Log: debug_console.log
echo ==========================================
pause
