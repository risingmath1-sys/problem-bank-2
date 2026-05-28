@echo off
chcp 65001 > nul

echo.
echo 상승 Solution 클라이언트
echo (서버가 이미 실행 중이어야 합니다)
echo.

start http://localhost:8000

echo 브라우저를 열었습니다.
echo.
pause
