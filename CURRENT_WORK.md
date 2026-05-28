# 현재 작업 상태 (마지막 업데이트: 2026-02-28)

## 작업 중인 프로젝트
`G:\문제은행\문제은행2` — 상승수학 문항 관리 시스템 (AnG 엔진)

---

## 오늘 한 작업 (2026-02-28)

### 수정 완료: 2015 내신기출 단원코드 매핑 버그 3종

#### 버그 1 (핵심): 파서에 config_path 미전달 → 매핑 로직 완전 무력화
- **원인**: `main_gui.py` 56번 줄에서 `HWPMetadataParserV2(output_dir=...)` 생성 시
  `config_path` 인자를 안 넘겨서 파서의 `self.curr_map = {}` (빈 딕셔너리)
  → `if is_legacy and self.curr_map:` 조건이 **False** → 매핑 블록 통째로 건너뜀
  → 2015 코드가 그대로 DB 저장됨
- **수정**: `backend/main_gui.py` 56줄
  ```python
  # 수정 전
  self.parser = HWPMetadataParserV2(output_dir=self.output_dir)
  # 수정 후
  _cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "curriculum_config.json")
  self.parser = HWPMetadataParserV2(output_dir=self.output_dir, config_path=_cfg_path)
  ```

#### 버그 2: 대단원 출제 쿼리 시 2015→2022 변환 누락
- **원인**: `_query_count_for_row`의 대단원(large) 분기에서
  `_get_medium_codes_for_large`로 얻은 2015 중단원 코드를 변환 없이 그대로 쿼리
- **수정**: `backend/main_gui.py` ~2118줄 (large 분기에 mapping 적용 추가)

#### 버그 3: 실제 출제 쿼리에서도 동일 문제
- **원인**: ~2451줄 중단원 출제 분기도 2015 코드 그대로 사용
- **수정**: `backend/main_gui.py` ~2451줄 (large+medium 양쪽 모두 mapping 적용)

#### DB 마이그레이션
- **현상**: 기존 등록된 935건 2015 내신기출이 2015 코드로 저장돼 있었음
- **수정**: `migrate_unit_codes.py` 작성/실행 → 752건 변환, 183건 스킵
- **결과**: 935건 중 926건(99%) 유효 2022 코드로 정상 변환
  - 9건 문제 잔존: unit_code 빈 값 8건(태그 파싱 실패), K5 1건(유효치 않은 코드)
- **마이그레이션 스크립트**: `migrate_unit_codes.py` (루트에 위치, 재실행 가능)

---

## 핵심 파일 위치
- 메인 GUI: `backend/main_gui.py`
- DB 엔진: `backend/db_engine.py`
- HWP 파서: `backend/hwp_metadata_parser_v2.py`
- 교육과정 설정: `backend/curriculum_config.json`
- 단원 계층: `backend/unit_hierarchy.json`
- 내기왕 인덱서: `backend/indexers/naesin_ang.py`
- 아키텍처 문서: `system_architecture.md`
- DB 마이그레이션 스크립트: `migrate_unit_codes.py`

---

## 오늘 한 작업 (2026-03-13)

### ✅ DB 정비 3종 완료

#### 1. 한국어 난이도 코드 232건 → 영문 변환
- 원인: 수능특강 및 구버전 인덱서가 한국어('상','중','하','최상')로 저장
- 처리: `최상→A(25건), 상→B(62건), 중→C(51건), 하→D(94건)` 일괄 변환
- 잔존: 0건 ✅

#### 2. source 빈 값 538건 처리
- 원인: 구버전 인덱서가 source 컬럼을 저장 안 함
- 처리: 파일명 패턴으로 분류 → NAESIN_ANG(508건), SUNEUNG_SPECIAL(30건) 업데이트
- 잔존: 0건 ✅

#### 3. 수능완성 기하 unit_code 빈 값 522건 수정
- 원인: 기하 파일 인덱싱(2026-03-02) 당시 `WANSUNG_CHAPTER_MAP`에 '기하' 키 미존재
  → `get_wansung_unit_code("기하", ...)` 반환 None → unit_code 미저장
  → 이후 기하 항목 추가됐으나 재인덱싱 누락
- 처리: 파일명 챕터명 기준 직접 업데이트
  - `_07_이차곡선` → T1 (163건)
  - `_08_평면벡터` → V1 (183건)
  - `_09_공간도형과공간좌표` → U1 (176건)
- 잔존: 0건 ✅
- 참고: 수능완성 전체 problem_number=NULL은 **설계상 정상** (수완 인덱서는 problem_number 미사용)

### ✅ 정답 페이지 홀수 시작 기능 추가
- 파일: `backend/hwp_generator.py` — `_insert_answer_list()`
- BreakPage 후 `get_layout_state()`로 현재 페이지 확인 → 짝수이면 BreakPage 추가
- 항상 홀수 페이지에서 정답 시작 보장

---

## ⚠️ 의도적 미처리 사항 (건드리지 말 것)

### MOCK_EXAM unit_code 빈 값 984건 — 의도적 미분류
- 대상: 2023~2025년 모의고사 파일
- 이유: 사이드카 CSV(_units.csv)를 아직 작성하지 않은 파일
  → 단원 분류 작업 진행 중이며, CSV 작성 후 재인덱싱 예정
- **절대 자동으로 채우거나 삭제하지 말 것**

---

## 다음에 할 작업

### ① DB 잔존 문제 9건 처리 (낮은 우선순위)
- unit_code 비어있는 8건: HWP 파일에서 단원코드 태그가 없거나 파싱 실패
  → 해당 HWP 파일 재등록 (force_update) 하면 해결
- K5 1건: 유효하지 않은 코드 → 수동 확인 후 수정

### ② 수능특강 HWP 파일 구조 분석 (이전 미완료 작업)
- 섹션 헤더(예제/유제/Level1 등)가 이미지인지 텍스트인지 확인
- 분석 대상: `G:\문제은행\문제들\수능특강\` 폴더

### ③ source_type 컬럼 추가 (DB 스키마)
- `backend/db_engine.py`의 problems 테이블에 `source_type TEXT` 추가
- 마이그레이션 코드 작성

---

## 내기왕 단원코드 체계 정리 (중요 참고사항)

내기왕은 2022개정교과 기준 단일 코드 체계 사용 (A~V):
- 공통수학1: A(다항식), B(방정식), C(경우의수), D(행렬)
- 공통수학2: E(도형), F(집합명제), G(함수)
- 수학I: H(지수로그), I(삼각함수), J(수열)
- 미적분I: K(극한), L(미분), M(적분)
- 확률과통계: N(경우의수), O(확률), P(통계)
- 미적분II: Q(극한), R(미분), S(적분)
- 기하: T(이차곡선), U(평면좌표), V(벡터)

2015 내신기출 파일에서 사용하는 2015 전용 코드가 있을 때만 2015_to_2022 매핑 필요.
매핑 테이블: `backend/curriculum_config.json` > `curriculum_mappings` > `2015_to_2022`

---

## 중요 결정사항
- 6개 소스를 **하나의 프로그램**에서 처리 (분리 X)
- 인덱서는 플러그인 패턴 (`BaseIndexer` 추상 클래스)
- 수능특강/완성/모의고사/문제집은 **대단원** 기준
- 내신기출 2종은 **중단원** 기준
- DB unit_code는 **항상 2022 코드** (primary 조회 키)
- mapped_unit_code는 원본 2015 코드 보관용 (비어있으면 원래부터 2022)
