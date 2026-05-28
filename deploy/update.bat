@echo off
chcp 65001 > nul
setlocal

REM ============================================================
REM  git pull + 서비스 재시작 (배포 업데이트)
REM  사용자 PC에서 git push 후, 미니PC에서 이 파일 실행
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set SERVICE_NAME=ProblemBank2

cd /d "%CLONE_DIR%"
if errorlevel 1 (
    echo [ERROR] 폴더 이동 실패: %CLONE_DIR%
    pause
    exit /b 1
)

echo [INFO] 현재 커밋:
git log -1 --oneline

echo.
echo [INFO] git pull 실행
git pull
if errorlevel 1 (
    echo [ERROR] git pull 실패
    pause
    exit /b 1
)

echo.
echo [INFO] 패키지 업데이트 (변경 시)
set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe
"%PYTHON_EXE%" -m pip install -r requirements.txt --quiet

echo.
echo [INFO] 서비스 재시작: %SERVICE_NAME%
nssm restart %SERVICE_NAME%
timeout /t 3 /nobreak >nul

echo.
echo [INFO] 서비스 상태:
nssm status %SERVICE_NAME%

echo.
echo [OK] 업데이트 완료
echo  URL: http://192.168.0.139:8000
echo.
endlocal
