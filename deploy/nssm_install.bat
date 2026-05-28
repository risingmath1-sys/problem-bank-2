@echo off
chcp 65001 > nul
setlocal

REM ============================================================
REM  NSSM으로 문제은행2 SC 서버 등록 (관리자 권한 필요)
REM ============================================================

set CLONE_DIR=C:\sangsung\problem-bank-2
set PYTHON_EXE=C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe
set SERVICE_NAME=ProblemBank2
set PORT=8000

REM 관리자 권한 체크
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 관리자 권한으로 실행해주세요.
    echo   이 .bat 파일을 우클릭 -^> "관리자 권한으로 실행"
    pause
    exit /b 1
)

REM NSSM 체크
where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] NSSM이 설치되어 있지 않습니다.
    echo.
    echo  설치 방법:
    echo   1. https://nssm.cc/release/nssm-2.24.zip 다운로드
    echo   2. 압축 해제 후 win64\nssm.exe 를 C:\Windows\System32 에 복사
    echo   3. 또는 nssm.exe 와 같은 폴더에 이 .bat 두고 다시 실행
    pause
    exit /b 1
)
echo [OK] NSSM 확인

REM SESSION_SECRET 생성 (기존 값이 있으면 유지)
set SECRET_FILE=%CLONE_DIR%\.session_secret
if not exist "%SECRET_FILE%" (
    echo [INFO] SESSION_SECRET 새로 생성
    powershell -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')" > "%SECRET_FILE%"
)
set /p SESSION_SECRET=<"%SECRET_FILE%"
echo [OK] SESSION_SECRET 준비

REM 기존 서비스 제거
echo.
echo [INFO] 기존 서비스 정리 (있을 경우)
nssm stop %SERVICE_NAME% 2>nul
nssm remove %SERVICE_NAME% confirm 2>nul

REM 서비스 등록
echo.
echo [INFO] 서비스 등록
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
echo [INFO] 서비스 시작
nssm start %SERVICE_NAME%
timeout /t 3 /nobreak >nul

echo.
echo ============================================================
echo  서비스 등록 완료
echo ============================================================
nssm status %SERVICE_NAME%
echo.
echo  서비스명:   %SERVICE_NAME%
echo  포트:       %PORT%
echo  URL:        http://192.168.0.139:%PORT%
echo  로그:       %CLONE_DIR%\logs\
echo.
echo  관리 명령:
echo    nssm status   %SERVICE_NAME%
echo    nssm restart  %SERVICE_NAME%
echo    nssm stop     %SERVICE_NAME%
echo    nssm start    %SERVICE_NAME%
echo    nssm edit     %SERVICE_NAME%   (GUI)
echo.
echo ============================================================
pause
endlocal
