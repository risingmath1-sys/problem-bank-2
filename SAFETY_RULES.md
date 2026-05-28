# 🚨 HWP 자동화 안전 규칙

## AI 실행 금지 정책

> [!CAUTION]
> **HWP 자동화 스크립트는 AI가 자동으로 실행하지 않습니다.**
> 
> 무한루프 위험이 있으므로, 모든 HWP 관련 테스트는 **사용자가 직접 터미널에서 실행**해야 합니다.

## 금지 대상 스크립트

다음 파일들은 AI가 `run_command`로 실행하지 않습니다:

- `backend/verify_hwp_open.py`
- `backend/test_hwp_automation.py`
- `backend/hwp_parser_safe.py`
- `backend/hwp_metadata_parser_v2.py`
- `backend/test_exam_gen_simple.py`
- `test_metadata_extraction.py`
- `test_hwp_*.py` (모든 HWP 테스트 파일)

## 사용자 실행 가이드

### 워크플로우 참조
```
/.agent/workflows/safe-hwp-test.md
```

### 빠른 실행 명령어

**HWP 열기 테스트:**
```powershell
cd g:\문제은행\문제은행2\backend
python verify_hwp_open.py
```

**메타데이터 추출:**
```powershell
cd g:\문제은행\문제은행2
python test_metadata_extraction.py
```

## 긴급 중단 방법

1. **Ctrl+C** - 스크립트 중단
2. **작업 관리자** - Hwp.exe 강제 종료
3. **PowerShell 명령:**
   ```powershell
   taskkill /F /IM Hwp.exe
   ```

## AI 행동 규칙

1. ✅ **허용**: 코드 작성, 수정, 리뷰
2. ✅ **허용**: 실행 명령어 제공
3. ❌ **금지**: HWP 스크립트 자동 실행
4. ❌ **금지**: `SafeToAutoRun=true` 설정 (HWP 관련)

---

**작성일**: 2026-01-23  
**목적**: 무한루프 방지 및 시스템 안정성 확보
