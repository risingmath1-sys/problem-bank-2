@echo off
chcp 65001 > nul
cd /d "G:\문제은행\문제은행2"

echo.
echo 상승 Solution 서버 시작 (포트 8000)
echo.

set NAEGIWANGBANK_SESSION_SECRET=dev-secret-CHANGE-IN-PRODUCTION
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo 서버 종료됨
pause
