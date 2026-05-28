@echo off
REM Cloudflare Tunnel 설정 스크립트 (Windows)
REM 실행 방법: cmd에서 이 파일 실행

echo.
echo ===================================
echo  Cloudflare Tunnel 설정 (solutio)
echo ===================================
echo.

REM Step 1: Cloudflare CLI 버전 확인
echo [1/5] Cloudflare CLI 확인...
cloudflared --version
if errorlevel 1 (
    echo ❌ cloudflared가 설치되지 않았습니다.
    echo 다운로드: https://developers.cloudflare.com/cloudflare-one/connections/connect-applications/install-and-setup/installation/
    echo.
    pause
    exit /b 1
)

REM Step 2: Tunnel 인증 (Cloudflare 로그인)
echo.
echo [2/5] Cloudflare 인증 (브라우저 자동 실행)...
cloudflared tunnel login
if errorlevel 1 (
    echo ❌ 인증 실패
    pause
    exit /b 1
)
echo ✅ 인증 완료

REM Step 3: Tunnel 생성
echo.
echo [3/5] Tunnel 생성 (solutio)...
cloudflared tunnel create solutio
if errorlevel 1 (
    echo ⚠️  Tunnel이 이미 존재할 수 있습니다. (무시 가능)
)
echo ✅ Tunnel 준비 완료

REM Step 4: DNS 레코드 추가
echo.
echo [4/5] DNS 레코드 등록 (solutio.risingmath.kr)...
cloudflared tunnel route dns solutio solutio.risingmath.kr
if errorlevel 1 (
    echo ⚠️  DNS 레코드 추가 실패 (수동 추가 필요)
    echo.
    echo [수동 추가 방법]
    echo - Cloudflare 대시보드 접속
    echo - risingmath.kr 도메인 선택
    echo - DNS 레코드 → CNAME 추가
    echo   - 이름: solutio
    echo   - 대상: [Tunnel ID].cfargotunnel.com
) else (
    echo ✅ DNS 레코드 등록 완료
)

REM Step 5: 설정 파일 확인
echo.
echo [5/5] 설정 파일 확인...
if exist "%USERPROFILE%\.wintun\tunnel_config.yml" (
    echo ⚠️  기존 설정 파일 발견
    echo 경로: %USERPROFILE%\.wintun\tunnel_config.yml
) else (
    echo 📍 설정 파일 위치: %CD%\tunnel_config.yml
)

echo.
echo ===================================
echo  ✅ Tunnel 설정 완료!
echo ===================================
echo.
echo [다음 단계]
echo 1. FastAPI 서버 시작: python backend/main.py
echo 2. Tunnel 시작: cloudflared tunnel run solutio
echo 3. 브라우저 접속: https://solutio.risingmath.kr
echo.
pause
