# HWP Metadata Extraction Design (Revised)

> **Purpose**: Extract metadata tags from HWP files to build problem database  
> **Scope**: Metadata only (no height measurement, no full content extraction)  
> **Last Updated**: 2026-01-20

---

## 1. Goal

Extract metadata from HWP files to populate Firebase database with problem information, enabling search and filtering capabilities.

## 2. Metadata Input Priority

> [!IMPORTANT]
> **User Input (UI) Priority**: UI에서 사용자가 선택한 공통 메타데이터(연도, 학기, 과목 등)를 HWP 내의 태그 정보보다 우선하여 적용합니다. 파일 내 태그는 UI 값이 없을 때나 보조적인 용도로만 참조합니다.

## 3. Curriculum & Subject Mapping

- **Flexible Configuration**: 교육과정(2015/2022) 및 과목 리스트는 코드 내에 하드코딩하지 않고 외부 설정 파일(`curriculum_config.json`)을 통해 관리합니다.
- **Future Proofing**: 새로운 교육과정이 도입되더라도 JSON 파일만 업데이트하면 시스템이 즉시 대응할 수 있도록 설계합니다.

## 4. Implementation Strategy

### Safe Operations
- ✅ Open HWP file (using `RobustHwpController`)
- ✅ Get text content for tag parsing
- ✅ Regex-based metadata extraction
- ❌ No cursor movement for extraction (to prevent infinite loops)

### Bulk Registration & Resume Logic
- **`registration_log.json`**: 폴더 스캔 시 가공 완료된 파일명을 로그 파일에 저장합니다.
- **Automatic Resume**: 프로그램 재시작 시 로그 파일을 대조하여 이미 완료된 파일은 자동으로 건너뜁니다.
- **Atomic Operations**: 한 파일의 모든 문제 데이터가 Firestore에 성공적으로 업로드된 경우에만 작업 완료로 기록합니다.

## 5. Metadata Structure

```json
{
  "problem_id": "hwp_휘문고2024기말_1",
  "meta": {
    "school": "UI 입력값 우선",
    "year": "UI 입력값 우선",
    "grade": "UI 입력값 우선",
    "semester": "UI 입력값 우선",
    "exam_type": "UI 입력값 우선",
    "subject": "UI 입력값 우선",
    "unit_code": "HWP 태그에서 추출",
    "difficulty": "HWP 태그에서 추출",
    "problem_type": "자동 판별 (객관식/주관식)"
  }
}
```

## 6. Error Handling & Safety

- **Timeout**: 파일당 10초 제한.
- **Validation**: 필수 필드 (학교, 과목, 단원) 누락 시 에러 로그 생성 후 다음 파일 진행.
- **Process Isolation**: 각 파일 처리는 독립적인 프로세스 환경에서 수행하여 메인 UI 앱의 중단을 방지합니다.

## 7. Problem Boundary Detection Strategy

> [!IMPORTANT]
> **Rectangle Marker Abolishment**: The previous approach of using rectangle shapes to mark problem boundaries has been abolished. The new approach uses endnote-based positioning for more reliable problem extraction.

### Problem Range Detection Rules

#### Upper Problem (상단 문제)
- **Start Point**: Endnote number position
- **End Point**: 3 lines above the next problem's tag (tag = endnote line - 1)
- **Exception**: If this is the last problem in the column, extend to column end

#### Lower Problem (하단 문제)
- **Start Point**: Problem tag position (endnote line - 1)
- **End Point**: Column end (before column break / page break)

### Rationale
- **Generous Margins**: The 3-line margin for upper problems ensures images and equations are not cut off
- **Full Column Capture**: Lower problems capture all trailing whitespace for later normalization
- **Endnote Reliability**: Endnote numbers are already reliably detected in the current system

### Auto-Spacing Normalization (Future Work)
- **Issue**: Copied content may include excessive trailing newlines
- **Solution**: Automatic normalization of whitespace after paste operation
- **Approach**: To be designed in implementation phase
  - Option A: Post-paste cleanup (simple)
  - Option B: Pre-copy preprocessing (precise)
  - Option C: Hybrid approach

---

## 8. Implementation Plan

### Phase 1: Core Engine (No UI)
1. `curriculum_config.json` 정의
2. `hwp_metadata_parser.py` 구현 (설정 파일 기반)
3. 로컬 테스트 및 결과 검증

### Phase 2: Firebase & Integration
1. Firestore 업로드 로직 통합
2. `registration_log.json` 기반 재개 로직 구현

### Phase 3: Admin UI
1. Tkinter/Vite 등 관리자 도구 화면 구성
2. 진행률 표시 및 로그 뷰어

### Phase 4: Problem Extraction Engine
1. Implement endnote-based boundary detection
2. Column end detection logic
3. Auto-spacing normalization

---

**Status**: 사용자 피드백 반영 완료, 최종 승인 대기 중  
**Risk Level**: Low  
**Dependencies**: pywin32, firebase-admin, curriculum_config.json
