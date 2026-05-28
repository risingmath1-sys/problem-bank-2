@echo off
REM ========================================================
REM   naegiwangbank .exe build - one-button automation
REM     1. version.txt PATCH +1
REM     2. PyInstaller
REM     3. rename to dist\naegiwangbank_v{ver}.exe
REM     4. copy firebase-key.json + package zip
REM     5. save build log
REM ========================================================
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo.
echo ============================================================
echo   naegiwangbank .exe build START
echo ============================================================
echo.

REM === 1. Check PyInstaller ===
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller not installed.
    echo         Install: pip install pyinstaller
    if "%CI%"=="" pause
    exit /b 1
)

REM === 2. Bump version ===
echo [1/5] Bumping version...
for /f "delims=" %%v in ('python _bump_version.py') do set VER=%%v
if not defined VER (
    echo [ERROR] _bump_version.py failed
    if "%CI%"=="" pause
    exit /b 1
)
echo        new version: v%VER%
echo.

REM === 3. PyInstaller ===
echo [2/5] PyInstaller (1-3 minutes)...
if not exist build_logs mkdir build_logs
set BUILD_LOG=build_logs\build_v%VER%.log

python -m PyInstaller --noconfirm --clean naegiwangbank.spec > "%BUILD_LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller failed. Log: %BUILD_LOG%
    echo.
    echo === last 30 lines ===
    powershell -Command "Get-Content '%BUILD_LOG%' -Tail 30"
    if "%CI%"=="" pause
    exit /b 1
)
echo        build done. Log: %BUILD_LOG%
echo.

REM === 4. Rename output ===
echo [3/5] Renaming output...
if not exist "dist\naegiwangbank.exe" (
    echo [ERROR] dist\naegiwangbank.exe was not created.
    if "%CI%"=="" pause
    exit /b 1
)

set OUTNAME=naegiwangbank_v%VER%.exe
if exist "dist\%OUTNAME%" del "dist\%OUTNAME%"

REM PyInstaller 직후 AV 스캔/락 가능 — 재시도
set RETRY=0
:RENAME_TRY
move "dist\naegiwangbank.exe" "dist\%OUTNAME%" >nul 2>&1
if not exist "dist\%OUTNAME%" (
    set /a RETRY+=1
    if !RETRY! lss 5 (
        timeout /t 2 /nobreak >nul 2>&1
        goto RENAME_TRY
    )
    echo [ERROR] rename 실패 ^(5회 재시도 후도^)
    if "%CI%"=="" pause
    exit /b 1
)
echo        -^> dist\%OUTNAME%
echo.

REM === 5. Copy key + package zip ===
echo [4/5] Packaging zip (.exe + firebase-key.json)...
python -c "from backend.firebase_init import find_key_path; import shutil; p=find_key_path(); shutil.copy(p, 'dist/firebase-key.json'); print('       key copied from:', p)"
if errorlevel 1 (
    echo [ERROR] firebase-key.json copy failed - cannot build deploy zip
    echo         ^(.exe is OK at dist\%OUTNAME%, but you must add key manually^)
    if "%CI%"=="" pause
    exit /b 1
)

set ZIPNAME=naegiwangbank_v%VER%.zip
if exist "dist\%ZIPNAME%" del "dist\%ZIPNAME%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist/%OUTNAME%','dist/firebase-key.json' -DestinationPath 'dist/%ZIPNAME%' -Force"
if errorlevel 1 (
    echo [ERROR] zip packaging failed
    if "%CI%"=="" pause
    exit /b 1
)
echo        -^> dist\%ZIPNAME%
echo.

REM === 6. Done ===
echo [5/5] Done
echo.
echo ============================================================
echo   OK exe:        dist\%OUTNAME%
echo   OK deploy zip: dist\%ZIPNAME%   ^<-- this is what you ship
echo   OK build log:  %BUILD_LOG%
echo   next build will auto-bump PATCH again
echo ============================================================
echo.
if "%CI%"=="" pause
