"""
SuneungWansungIndexer — 수능완성 소스 인덱서.

수능완성 HWP 파일 특징:
  - 태그 없음 (has_tags=False)
  - 파일명에서 과목 + 챕터 자동 파싱 → 단원코드 자동 결정
  - @ 마커 없음 (수특과 달리 섹션 마커 없음)
  - 중단원: 각 대단원의 첫 번째 unit_code 고정
  - 난이도: 각 유형 섹션의 마지막 문제 = 상급, 나머지 = 중급
  - 소스: SUNEUNG_WANSUNG
  - 교육과정: 2015이지만 2022 코드로 저장 (수특과 동일)

파일명 패턴:
  EBS수능완성수학1[2025]_01_지수함수와로그함수.hwp
  EBS수능완성수학2[2025]_04_함수의극한과연속.hwp
  EBS수능완성확률과통계[2025]_07_경우의수.hwp
  EBS수능완성미적분[2025]_07_수열의극한.hwp
"""

import os
import re

try:
    from backend.indexer_base import BaseIndexer
    from backend.indexers.ebs_subject_map import resolve_ebs_subject
    from backend.indexers.suneung_unit_map import parse_ebs_filename, get_wansung_unit_code
except ImportError:
    from indexer_base import BaseIndexer
    from indexers.ebs_subject_map import resolve_ebs_subject
    from indexers.suneung_unit_map import parse_ebs_filename, get_wansung_unit_code

from typing import List


class SuneungWansungIndexer(BaseIndexer):
    """
    수능완성 소스 인덱서.

    파일명 파싱으로 과목/단원코드를 자동 결정하며,
    유형 섹션 경계를 이용해 마지막 문제를 상급 난이도로 분류한다.
    """

    def get_schema(self) -> dict:
        return {
            "label": "수능완성",
            "fields": [
                {
                    "key":      "시행 연도",
                    "type":     "entry",
                    "default":  "2025",
                    "db_key":   "year",
                    "required": True,
                },
                # 과목·단원코드는 파일명에서 자동 추출 (여러 과목 폴더 일괄 처리 가능)
            ],
        }

    def get_required_db_key(self) -> str:
        """수능완성은 과목 자동 추출 → 연도만 필수 체크."""
        return "year"

    def has_tags(self) -> bool:
        """수능완성은 태그 없음."""
        return False

    def extract_metadata(self, file_path: str, form_values: dict) -> dict:
        """
        파일명에서 과목, 연도, 단원코드를 자동 추출.

        중단원은 각 대단원의 첫 번째 unit_code로 고정.
        """
        result = dict(form_values)
        filename = os.path.basename(file_path)

        parsed = parse_ebs_filename(filename)
        if parsed is None:
            return result

        subject_raw = parsed["subject_raw"]
        chapter_name = parsed["chapter_name"]
        year = parsed["year"]

        # 과목명 → 2022 DB subject
        subject = resolve_ebs_subject(subject_raw)
        if subject:
            result["subject"] = subject

        # 챕터명 → 대단원 첫 번째 unit_code
        unit_code = get_wansung_unit_code(subject_raw, chapter_name)
        if unit_code:
            result["unit_code"] = unit_code

        result["year"] = str(year)
        result["source"] = "SUNEUNG_COMPLETE"
        result["curriculum"] = "2022개정교육과정"

        return result

    @staticmethod
    def compute_high_difficulty_indices(full_text: str) -> set:
        """
        GetTextFile 전체 텍스트에서 상급 문제 인덱스(1-based) 집합 반환.

        각 유형 섹션의 마지막 문제 = 상급.
        ('N N.N. 답' 패턴으로 문제 카운팅, '유형' 텍스트로 섹션 경계 감지)

        Returns:
            set of int: 상급 문제의 1-based 인덱스 집합
        """
        lines = [l.rstrip('\r\n') for l in full_text.split('\n')]
        # "N N.N." (공백 구분) 또는 "N.N." (마침표 구분) 두 형식 모두 지원
        prob_pattern = re.compile(r'^\d+[\s.]\d+\.')

        # 유형 헤더 라인 인덱스 수집
        type_line_indices = []
        for i, line in enumerate(lines):
            if line.strip() == '유형':
                non_blank = []
                j = i - 1
                while j >= 0 and len(non_blank) < 2:
                    if lines[j].strip():
                        non_blank.append(lines[j].strip())
                    j -= 1
                # 두 번째 비어있지 않은 줄이 2자리 숫자면 유형 헤더로 확정
                if len(non_blank) >= 2 and re.match(r'^\d{2}$', non_blank[1]):
                    type_line_indices.append(i)

        if not type_line_indices:
            return set()

        # 유형별 문제 수 계산 → 마지막 문제 인덱스 수집
        high_set = set()
        total = 0
        for idx, type_line in enumerate(type_line_indices):
            end = type_line_indices[idx + 1] if idx + 1 < len(type_line_indices) else len(lines)
            cnt = sum(1 for l in lines[type_line:end] if prob_pattern.match(l.strip()))
            total += cnt
            if cnt > 0:
                high_set.add(total)  # 해당 유형의 마지막 문제 인덱스

        return high_set
