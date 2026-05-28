@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

echo.
echo ============================================================
echo   포트 8000 정리 (충돌 시 사용)
echo ============================================================
echo.

REM === 포트 8000 확인 ===
echo [확인] 포트 8000 사용 중인 프로세스...
echo.

for /f "tokens=5" %%A in ('netstat -ano ^| findstr :8000') do (
    set PID=%%A
    echo   PID: !PID!

    REM === 프로세스 이름 조회 ===
    for /f "tokens=1" %%B in ('tasklist ^| findstr !PID!') do (
        echo   프로세스: %%B
    )

    REM === 종료 확인 ===
    echo.
    echo   이 프로세스를 종료하시겠습니까? (Y/N)
    set /p CONFIRM=

    if /i "!CONFIRM!"=="Y" (
        taskkill /PID !PID! /F
        if errorlevel 0 (
            echo   [OK] PID !PID! 종료됨
        ) else (
            echo   [ERROR] 종료 실패 (관리자 권한 필요할 수 있음)
        )
    ) else (
        echo   [스킵] 프로세스 유지
    )
)

echo.
echo ============================================================
echo   포트 정리 완료
echo   이제 "서버클라이언트시작.bat" 을 실행하세요.
echo ============================================================
echo.
pause
