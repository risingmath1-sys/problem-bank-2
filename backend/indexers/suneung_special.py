"""
SuneungSpecialIndexer — 수능특강 소스 인덱서.

수능특강 HWP 파일 특징:
  - 태그 없음 (has_tags=False)
  - 파일명에서 과목 + 챕터 자동 파싱 → 단원코드 자동 결정
  - @ 마커(투명 텍스트)로 문제 유형 섹션 구분 (파일당 @ 4개 고정):
      @ 0개 앞 → 예제/유제 (EXAM) 난이도: 하
      @ 1개 앞 → 레벨1 (L1)       난이도: 중
      @ 2개 앞 → 레벨2 (L2)       난이도: 상
      @ 3개 앞 → 레벨3 (L3)       난이도: 최상
      @ 4번째 마커 = L3 마지막 끝점 (그 뒤에 문제 없어야 함)
  - 등록 시 사용자 입력: 연도 (파일명에서 자동 추출되지만 확인용)
  - 과목/단원: 파일명 자동 파싱 (수동 불필요)
"""

import os

try:
    from backend.indexer_base import BaseIndexer
    from backend.indexers.ebs_subject_map import resolve_ebs_subject
    from backend.indexers.suneung_unit_map import parse_ebs_filename, get_unit_code
except ImportError:
    from indexer_base import BaseIndexer
    from indexers.ebs_subject_map import resolve_ebs_subject
    from indexers.suneung_unit_map import parse_ebs_filename, get_unit_code

from typing import List, Optional


# @ 마커 인덱스 → 문제 유형 코드
# @4번째는 L3 마지막 문제의 끝점 마커 → 그 뒤에 문제 없어야 함
_SECTION_TYPE_MAP = {
    0: "EXAM",   # 예제/유제 (첫 @ 앞)  난이도: 하
    1: "L1",     # 레벨1                난이도: 중
    2: "L2",     # 레벨2                난이도: 상
    3: "L3",     # 레벨3                난이도: 최상
}


class SuneungSpecialIndexer(BaseIndexer):
    """
    수능특강 소스 인덱서.

    파일명 파싱으로 단원코드를 자동 결정하며,
    @ 마커 개수로 문제 유형(예제/L1/L2/L3/대표기출)을 분류한다.
    """

    # ── 필수 오버라이드 ────────────────────────────────────────────────────

    def get_schema(self) -> dict:
        """
        수능특강 등록 폼 스키마.

        연도는 파일명에서 자동 추출되지만 사용자가 확인/수정 가능하도록 entry로 표시.
        과목/단원은 파일명 파싱으로 자동 결정 → extract_metadata()에서 채움.
        """
        return {
            "label": "수능특강",
            "fields": [
                {
                    "key":      "시행 연도",
                    "type":     "entry",
                    "default":  "2025",
                    "db_key":   "year",
                    "required": True,
                },
                {
                    "key":      "과목",
                    "type":     "combo",
                    "values":   ["대수", "미적분I", "확률과통계", "미적분II", "기하"],
                    "default":  "대수",
                    "db_key":   "subject",
                    "required": True,
                },
            ],
        }

    # ── 선택적 오버라이드 ──────────────────────────────────────────────────

    def has_tags(self) -> bool:
        """수능특강은 태그 없음."""
        return False

    def extract_metadata(self, file_path: str, form_values: dict) -> dict:
        """
        파일명에서 과목, 연도, 단원코드를 자동 추출하여 form_values에 병합.

        파싱 성공 시 subject, unit_code, year를 자동으로 채운다.
        파싱 실패 시 form_values 원본을 그대로 반환 (수동 입력값 유지).

        Args:
            file_path:   HWP 파일 전체 경로
            form_values: 등록 폼에서 수집된 값 딕셔너리

        Returns:
            메타데이터 딕셔너리 (DB 저장용)
        """
        result = dict(form_values)
        filename = os.path.basename(file_path)

        parsed = parse_ebs_filename(filename)
        if parsed is None:
            # 파일명 패턴 불일치 → 수동 입력값 그대로 사용
            return result

        subject_raw = parsed["subject_raw"]
        chapter_name = parsed["chapter_name"]
        year = parsed["year"]

        # 과목명 → 2022 DB subject
        subject = resolve_ebs_subject(subject_raw)
        if subject:
            result["subject"] = subject

        # 챕터명 → 중단원 코드
        unit_code = get_unit_code(subject_raw, chapter_name)
        if unit_code:
            result["unit_code"] = unit_code

        # 연도 (파일명 우선, 폼 입력값으로 덮어쓰지 않음)
        result["year"] = str(year)

        # 수능특강 고정 메타
        result["source"] = "SUNEUNG_SPECIAL"
        result["curriculum"] = "2022개정교육과정"

        return result

    @staticmethod
    def difficulty_from_section_type(section_type: str) -> str:
        """
        수능특강 섹션 유형 → 난이도 변환 (DB 저장용).

        규칙 (DB 코드):
          EXAM → "D" (하)
          L1   → "C" (중)
          L2   → "B" (상)
          L3   → "A" (최상)

        Args:
            section_type: "EXAM" / "L1" / "L2" / "L3"

        Returns:
            "A" / "B" / "C" / "D"  ← GUI 필터 코드와 일치
        """
        return {"EXAM": "D", "L1": "C", "L2": "B", "L3": "A"}.get(section_type, "C")

    def get_exam_options(self) -> List[dict]:
        """
        출제 화면에서 수능특강 전용 옵션: 섹션 유형 필터.
        """
        return [
            {
                "key":    "section_types",
                "label":  "문제 유형",
                "type":   "multicheck",
                "values": [
                    {"value": "EXAM", "label": "예제/유제 (하)"},
                    {"value": "L1",   "label": "레벨1 (중)"},
                    {"value": "L2",   "label": "레벨2 (상)"},
                    {"value": "L3",   "label": "레벨3 (최상)"},
                ],
                "default": ["L1", "L2", "L3"],
            },
        ]

    # ── 공개 유틸리티 ──────────────────────────────────────────────────────

    @staticmethod
    def resolve_section_type(at_marker_count: int) -> str:
        """
        파일 내 @ 마커 누적 개수 → 문제 유형 코드.

        @4번째는 L3 마지막 끝점 마커이므로 그 뒤에 문제가 있으면 파일 오류.
        이 경우 "L3"로 fallback하고 호출부에서 WARNING 출력.

        Args:
            at_marker_count: 해당 문제 위치까지 나온 @ 마커 총 개수

        Returns:
            "EXAM" / "L1" / "L2" / "L3"
        """
        return _SECTION_TYPE_MAP.get(at_marker_count, "L3")
