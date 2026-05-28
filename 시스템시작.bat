@echo off
chcp 65001 > nul

echo.
echo ============================================================
echo   상승 Solution - 서버 시작
echo ============================================================
echo.

cd /d "G:\문제은행\문제은행2"

set NAEGIWANGBANK_SESSION_SECRET=dev-secret-CHANGE-IN-PRODUCTION

echo [시작] 포트 8000에 서버 시작...
start "상승 Solution 서버" python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

echo [대기] 5초 후 브라우저 실행...
timeout /t 5 /nobreak

echo [브라우저] http://localhost:8000 열기...
start http://localhost:8000

echo.
echo 완료! 이 창을 닫아도 서버는 계속 실행됩니다.
echo 서버 종료: 검은색 서버 창에서 Ctrl+C
echo.
pause
