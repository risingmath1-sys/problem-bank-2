"""
BaseIndexer - 모든 소스 인덱서의 공통 인터페이스.

공통 로직(문항번호 제거, 미주번호 처리, 좌표 추출, DB 저장)은 이 클래스에만 존재한다.
소스별 서브클래스는 get_schema()를 포함하여 차이나는 메서드만 오버라이드한다.

[설계 원칙]
- 공통 인터페이스(BaseIndexer 메서드)는 두 번째 소스 구현 시 필요에 따라 조정한다.
- 첫 번째 소스만 보고 미리 모든 차이를 예측하지 않는다 (over-engineering 금지).
"""

from typing import List, Dict, Optional


class BaseIndexer:
    """
    소스 인덱서 공통 베이스 클래스.

    서브클래스 구현 규칙:
    - get_schema()           : 필수 오버라이드
    - has_tags()             : 선택 (기본값 True)
    - extract_metadata()     : 선택 (기본값: 폼 입력 그대로)
    - detect_difficulty()    : 선택 (기본값: None)
    - get_exam_options()     : 선택 (기본값: 빈 리스트, 추후 구현)
    """

    # ── 소스별 오버라이드 필수 ──────────────────────────────────────

    def get_schema(self) -> dict:
        """
        등록 폼 필드 정의 반환. UI가 이 값으로 폼을 자동 렌더링한다.

        반환 형식:
        {
            "label": "소스 표시 이름",
            "fields": [
                {
                    "key":      "학교명",         # 폼 레이블 & self.entries 키
                    "type":     "entry",           # entry / combo / curr / subj
                    "default":  "",               # 초기값
                    "values":   [...],             # combo 전용
                    "db_key":   "school",          # common_meta 딕셔너리 키
                    "required": False,             # 필수 여부 (기본 False)
                },
                ...
            ],
        }

        type 종류:
          entry  - 일반 텍스트 입력
          combo  - 드롭다운 (values 필요)
          curr   - 교육과정 드롭다운 (과목명과 연동, curr_config 자동 사용)
          subj   - 과목명 드롭다운 (교육과정 선택에 따라 동적 변경)
        """
        raise NotImplementedError(f"{self.__class__.__name__}.get_schema() 미구현")

    # ── 소스별 선택적 오버라이드 ────────────────────────────────────

    def has_tags(self) -> bool:
        """
        태그([학교/년도/...]) 기반 문제 구분 여부.
        - True  : 내신기출 방식 (태그로 문제 범위 탐지)
        - False : 파일명/번호 기반 (수능특강, 모의고사 등)
        """
        return True

    def extract_metadata(self, file_path: str, form_values: dict) -> dict:
        """
        파일명/내용에서 메타데이터를 추가 추출.
        기본값: 폼 입력값 그대로 반환.

        수능특강 등에서 오버라이드:
          - 파일명 파싱 → 대단원/중단원 자동 추출
          - 파일 내 특수 인자 스캔
        """
        return form_values

    def detect_difficulty(self, problem_content: str) -> Optional[str]:
        """
        문제 내용에서 난이도 자동 감지.
        기본값: None (감지 안 함 — 태그 파싱은 파서가 직접 처리).
        수능특강 등에서 오버라이드: 파일 내 특수 인자 스캔.
        """
        return None

    def can_index(self, file_path: str) -> bool:
        """
        이 파일을 인덱싱할 수 있는지 사전 검사.
        기본값: True (항상 허용).
        모의고사 등 사이드카 파일이 필요한 소스에서 오버라이드.
        """
        return True

    def get_exam_options(self) -> List[dict]:
        """
        출제 화면에서 이 소스에만 표시할 특별 옵션 목록.
        기본값: 빈 리스트 (소스 구현 완료 후 채우는 방식).

        반환 형식:
        [
            {"key": "...", "label": "...", "type": "check/combo", ...}
        ]
        """
        return []

    # ── 공통 유틸리티 (서브클래스에서 재사용 가능) ──────────────────

    def collect_form_values(self, entries: dict) -> dict:
        """
        self.entries(위젯 딕셔너리)에서 값을 읽어 common_meta 딕셔너리 반환.
        schema의 db_key로 키 매핑한다.
        """
        meta = {}
        for field in self.get_schema()["fields"]:
            key = field["key"]
            db_key = field.get("db_key", key)
            if key in entries:
                meta[db_key] = entries[key].get()
        return meta

    def get_required_db_key(self) -> str:
        """
        start_scan에서 필수 입력 체크할 db_key 반환.
        기본값: "subject" (과목명은 항상 필수).
        """
        return "subject"
