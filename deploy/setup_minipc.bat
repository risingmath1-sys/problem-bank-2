@echo off
chcp 65001 > nul
setlocal

REM ============================================================
REM  문제은행2 미니PC 1회 셋업 스크립트
REM  실행 위치: 미니PC RDP 접속 후 cmd에서 실행
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe
set REPO_URL=https://github.com/risingmath1-sys/problem-bank-2.git

echo.
echo ============================================================
echo  [1/5] 사전 체크
echo ============================================================

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git이 설치되어 있지 않습니다.
    echo   https://git-scm.com/download/win 에서 설치하세요.
    pause
    exit /b 1
)
echo [OK] git 확인

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python을 찾을 수 없습니다: %PYTHON_EXE%
    pause
    exit /b 1
)
echo [OK] Python 확인

if not exist "C:\sangsung" mkdir "C:\sangsung"

echo.
echo ============================================================
echo  [2/5] 저장소 clone / pull
echo ============================================================

if exist "%CLONE_DIR%\.git" (
    echo [INFO] 이미 clone되어 있음. git pull 실행
    cd /d "%CLONE_DIR%"
    git pull
) else (
    echo [INFO] git clone 시작
    cd /d C:\sangsung
    git clone %REPO_URL% problem-bank-2
    if errorlevel 1 (
        echo [ERROR] git clone 실패
        pause
        exit /b 1
    )
)

cd /d "%CLONE_DIR%"

echo.
echo ============================================================
echo  [3/5] Python 패키지 설치
echo ============================================================

"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install 실패
    pause
    exit /b 1
)
echo [OK] 패키지 설치 완료

echo.
echo ============================================================
echo  [4/5] logs 폴더 생성
echo ============================================================
if not exist "%CLONE_DIR%\logs" mkdir "%CLONE_DIR%\logs"
echo [OK] logs 폴더 준비

echo.
echo ============================================================
echo  [5/5] 다음 단계 안내
echo ============================================================
echo.
echo  ★ 민감 파일 수동 복사가 필요합니다:
echo.
echo    아래 파일들을 사용자 PC에서 %CLONE_DIR% 폴더로 복사:
echo      - firebase-key.json
echo      - problem_bank.db
echo.
echo    네트워크 공유, USB, 또는 RDP 클립보드 활용
echo.
echo  복사 후 nssm_install.bat 실행하여 서비스 등록
echo.
echo ============================================================
pause
endlocal
