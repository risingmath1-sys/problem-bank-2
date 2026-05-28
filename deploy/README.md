# 미니PC 셋업 가이드

학원 미니PC (`192.168.0.139`)에서 문제은행2 SC 서버를 운영하기 위한 셋업 절차.

## 사전 준비물 (미니PC에 설치되어 있어야 함)

- [x] Python 3.11 (`C:\Users\Q\AppData\Local\Programs\Python\Python311\python.exe`)
- [ ] git (없으면 https://git-scm.com/download/win)
- [ ] NSSM (없으면 https://nssm.cc/release/nssm-2.24.zip → `nssm.exe`를 `C:\Windows\System32`에 복사)
- [ ] 한컴 오피스 (HWP COM 자동화용 — 출제 기능 사용 시)

## 1회 셋업 (RDP 접속 후 미니PC에서 실행)

```cmd
REM 1. RDP 접속
REM    Win+R → mstsc → 192.168.0.139

REM 2. cmd 열고 임시 폴더로 이동
cd %TEMP%

REM 3. 셋업 스크립트 다운로드 후 실행
curl -O https://raw.githubusercontent.com/risingmath1-sys/problem-bank-2/main/deploy/setup_minipc.bat
setup_minipc.bat
```

또는 미니PC에서 GitHub 페이지를 열어 `deploy/setup_minipc.bat`를 직접 다운로드해 실행해도 됩니다.

### 셋업 스크립트가 하는 일

1. git / Python 설치 여부 체크
2. `C:\sangsung\problem-bank-2`에 저장소 clone
3. `pip install -r requirements.txt`
4. `logs/` 폴더 생성

## 민감 파일 복사 (수동)

`.gitignore`에 의해 GitHub에 올라가지 않은 파일들을 미니PC로 복사:

| 파일 | 사용자 PC 경로 | 미니PC 경로 |
| --- | --- | --- |
| `firebase-key.json` | `G:\문제은행\문제은행2\firebase-key.json` | `C:\sangsung\problem-bank-2\firebase-key.json` |
| `problem_bank.db` | `G:\문제은행\문제은행2\problem_bank.db` | `C:\sangsung\problem-bank-2\problem_bank.db` |

복사 방법: RDP 클립보드 / 네트워크 공유 / USB

## 서비스 등록 (NSSM)

민감 파일 복사 후, 미니PC에서 **관리자 권한 cmd**로 실행:

```cmd
cd C:\sangsung\problem-bank-2\deploy
nssm_install.bat
```

### 등록되는 서비스

- **서비스명:** `ProblemBank2`
- **포트:** 8000
- **자동 시작:** 부팅 시 자동 (`SERVICE_AUTO_START`)
- **충돌 시 자동 재시작:** 5초 후 재시작
- **로그:** `C:\sangsung\problem-bank-2\logs\stdout.log` / `stderr.log` (10MB 로테이션)
- **환경변수:**
  - `NAEGIWANGBANK_SESSION_SECRET` — 자동 생성, `.session_secret` 파일에 저장
  - `DATA_ENGINE=sqlite`

### 접속 확인

브라우저에서 `http://192.168.0.139:8000` 접속.

## 배포 업데이트 (코드 변경 시)

### 사용자 PC에서

```cmd
cd G:\문제은행\문제은행2
git add .
git commit -m "변경 내용"
git push
```

### 미니PC에서 (RDP 접속 후)

```cmd
cd C:\sangsung\problem-bank-2\deploy
update.bat
```

`update.bat`이 git pull → pip install → 서비스 재시작까지 처리.

## 서비스 관리 명령

```cmd
nssm status   ProblemBank2     :: 현재 상태
nssm restart  ProblemBank2     :: 재시작
nssm stop     ProblemBank2     :: 중지
nssm start    ProblemBank2     :: 시작
nssm edit     ProblemBank2     :: GUI 편집
nssm remove   ProblemBank2 confirm  :: 서비스 제거
```

## 트러블슈팅

| 증상 | 확인 |
| --- | --- |
| 서비스 시작 실패 | `logs/stderr.log` 확인 |
| 포트 충돌 | `netstat -ano | findstr :8000` |
| DB 없음 에러 | `problem_bank.db` 복사 누락 확인 |
| Firestore 인증 실패 | `firebase-key.json` 복사 누락 / 손상 확인 |
| 외부 접속 안 됨 | Windows 방화벽 인바운드 규칙에서 포트 8000 허용 |
