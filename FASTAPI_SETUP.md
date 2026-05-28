# 📡 FastAPI 웹 서버 설정 가이드

**상태**: 🔧 진행 중 (2026-05-02 완성 중)

---

## 🚀 Quick Start (로컬 테스트)

### 1. Python 의존성 설치
```bash
cd G:\문제은행\문제은행2
pip install -r requirements.txt
```

### 2. FastAPI 서버 시작
```bash
python backend/main.py
```

**확인:**
- 터미널: `Uvicorn running on http://127.0.0.1:8000`
- 브라우저: http://localhost:8000 접속 (로그인 화면)
- API: http://localhost:8000/api/health

---

## 🌐 Cloudflare Tunnel 설정 (외부 접속)

### Step 1: Cloudflare CLI 설치
```bash
# 옵션 A: Windows (Chocolatey)
choco install cloudflared

# 옵션 B: 직접 다운로드
https://developers.cloudflare.com/cloudflare-one/connections/connect-applications/install-and-setup/installation/
```

### Step 2: 자동 설정 스크립트 실행
```bash
cd G:\문제은행\문제은행2
setup_tunnel.bat
```

**스크립트가 자동으로:**
1. ✅ Cloudflare 인증 (브라우저)
2. ✅ Tunnel 생성 (`solutio`)
3. ✅ DNS 레코드 등록 (`solutio.risingmath.kr`)

### Step 3: Tunnel 시작
```bash
cloudflared tunnel run solutio
```

**확인:**
- 터미널에 `Connected to Cloudflare!` 메시지
- https://solutio.risingmath.kr 접속 (DNS 적용 후)

---

## ⚙️ 설정 파일

### `tunnel_config.yml` (프로젝트 루트)
```yaml
tunnel: solutio
credentials-file: C:\Users\dongw\.cloudflare\solutio-tunnel-cert.json

ingress:
  - hostname: solutio.risingmath.kr
    service: http://localhost:8000
  - service: http_status:404
```

### `backend/main.py`
- FastAPI 메인 앱
- 라우트:
  - `GET /` - 홈/로그인
  - `GET /api/health` - 헬스 체크
  - `GET /api/problems` - 문제 조회
  - `POST /api/generate/random` - 랜덤 출제
  - `POST /api/generate/original` - 원본 출제
  - `GET /api/download/{filename}` - 다운로드

---

## 📋 체크리스트

### DNS 적용 대기 중 (현재)
- [ ] `risingmath.kr` 도메인 변경 완료
- [ ] DNS 적용 완료 (수 시간 걸림)
  - 확인: `nslookup risingmath.kr` 또는 `ping risingmath.kr`

### Cloudflare Tunnel 준비
- [ ] Cloudflare CLI 설치 완료
- [ ] `setup_tunnel.bat` 실행 완료
- [ ] `solutio` Tunnel 생성 완료
- [ ] DNS 레코드 `solutio.risingmath.kr` 등록 완료

### 로컬 테스트
- [ ] FastAPI 서버 시작 (`python backend/main.py`)
- [ ] 브라우저 접속 (`http://localhost:8000`) ✅
- [ ] API 테스트 (`http://localhost:8000/api/health`) ✅

### 외부 접속 테스트 (DNS 적용 후)
- [ ] Tunnel 시작 (`cloudflared tunnel run solutio`)
- [ ] 브라우저 접속 (`https://solutio.risingmath.kr`) ⏳ DNS 대기 중

### 추가 구현 (다음 단계)
- [ ] Firebase Auth UI 연결
- [ ] Firestore 쿼리 통합
- [ ] HWP 생성 라우트 구현
- [ ] HTMX 프론트엔드 (UI)
- [ ] 출제 결과 다운로드
- [ ] 권한 관리 (admin/user)

---

## 🔗 관련 링크

- **Cloudflare Tunnel 문서**: https://developers.cloudflare.com/cloudflare-one/connections/connect-applications/
- **FastAPI 문서**: https://fastapi.tiangolo.com/
- **Firestore 문서**: https://firebase.google.com/docs/firestore

---

## 💡 팁

### 로컬에서만 테스트
```bash
python backend/main.py
# http://localhost:8000 접속
```

### 호스트를 모든 인터페이스로 공개 (주의: 보안)
```python
# backend/main.py에서:
uvicorn.run(..., host="0.0.0.0", port=8000)
```

### Tunnel 상태 확인
```bash
cloudflared tunnel list
cloudflared tunnel info solutio
```

### Tunnel 삭제 (필요 시)
```bash
cloudflared tunnel delete solutio
```

---

**문제 발생 시:**
- [Cloudflare 로그](https://developers.cloudflare.com/cloudflare-one/connections/connect-applications/troubleshooting/debug-logging/)
- [FastAPI 에러](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- 터미널 스크롤업 ⬆️
