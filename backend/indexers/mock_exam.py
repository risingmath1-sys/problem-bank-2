"""
MockExamIndexer — 모의고사 소스 인덱서.

모의고사 HWP 파일 특징:
  - 태그 없음 (has_tags=False)
  - 파일명에서 연도 자동 파싱 → 46형/38형(~2026) / 30형(2027~) 결정
  - 객/주 구분: 문제 번호 기반 정적 매핑
  - 난이도: 문제 번호 기반 정적 매핑
  - 단원코드: 동일 파일명 + _units.csv 사이드카에서 로드
  - 소스: MOCK_EXAM

파일명 패턴:
  HIDDENKICE모의고사[2025][시즌2]_05회.hwp
  한석원모의고사[2025][시즌2]_01회.hwp
  25031801_2025년03월18일대성수학.hwp       ← [XXXX] 없는 패턴

사이드카 CSV (같은 폴더, 같은 파일명 베이스):
  HIDDENKICE모의고사[2025][시즌2]_05회_units.csv

  CSV 형식:
    문제번호,unit_code
    1,K1
    2,K1
    ...
    46,I3

  사이드카 CSV가 없으면 unit_code는 빈 문자열로 저장됨.
  (단원분류 미완료 파일은 인덱싱하지 않는 것을 권장)

  기하 미분류 시: 1~38번까지만 CSV에 포함 (39~46번 행 생략)
  → CSV 최대 문제번호로 38형/46형 자동 판단

46형 구조 (공통+확통+미적분+기하, ~2026):
  1-22:   대수·미적분1 (공통)
  23-30:  확률과통계 (선택)
  31-38:  미적분 (선택)
  39-46:  기하 (선택)

  객관식: 1-15, 23-28, 31-36, 39-44  (총 33문)
  주관식: 16-22, 29-30, 37-38, 45-46  (총 13문)

  난이도:
    하  : 1-2, 23, 31, 39
    중  : 3-8, 16-19, 24-27, 32-35, 40-43
    상  : 9-13, 20, 29, 37, 45
    최상: 14-15, 21-22, 28, 30, 36, 38, 44, 46

38형 구조 (공통+확통+미적분, 기하 없음, ~2026):
  1-22:   대수·미적분1 (공통)
  23-30:  확률과통계 (선택)
  31-38:  미적분 (선택)

  객관식: 1-15, 23-28, 31-36  (총 27문)
  주관식: 16-22, 29-30, 37-38 (총 11문)

  난이도:
    하  : 1-2, 23, 31
    중  : 3-8, 16-19, 24-27, 32-35
    상  : 9-13, 20, 29, 37
    최상: 14-15, 21-22, 28, 30, 36, 38

30형 구조 (2027년~, 대수·미적분1·확통 혼합):
  객관식: 1-21  (총 21문)
  주관식: 22-30 (총 9문)

  난이도:
    하  : 1-3
    중  : 4-13, 22-25
    상  : 14-18, 26-27
    최상: 19-21, 28-30

_exam_form 자동 판단 순서:
  1. year >= 2027 → 30형 (확정)
  2. CSV 최대 문제번호 max_num 기준:
       max_num >= 39 → 46형
       0 < max_num <= 38 → 38형
       max_num == 0 (CSV 없음/비어있음) → 46형 (기본값)
"""

import os
import re
import csv
from typing import Optional

try:
    from backend.indexer_base import BaseIndexer
except ImportError:
    from indexer_base import BaseIndexer


class MockExamIndexer(BaseIndexer):
    """모의고사 인덱서 — 번호 기반 객/주/난이도 정적 매핑."""

    # ── 46형 정적 매핑 ───────────────────────────────────────────

    _D46: dict = {
        **{n: "D" for n in [1, 2, 23, 31, 39]},                          # 하
        **{n: "C" for n in list(range(3, 9)) + list(range(16, 20))
                             + list(range(24, 28)) + list(range(32, 36))
                             + list(range(40, 44))},                       # 중
        **{n: "B" for n in list(range(9, 14)) + [20, 29, 37, 45]},       # 상
        **{n: "A" for n in [14, 15, 21, 22, 28, 30, 36, 38, 44, 46]},   # 최상
    }

    _T46: dict = {
        **{n: "객관식" for n in list(range(1, 16))
                               + list(range(23, 29)) + list(range(31, 37))
                               + list(range(39, 45))},
        **{n: "주관식" for n in list(range(16, 23)) + [29, 30, 37, 38, 45, 46]},
    }

    # ── 38형 정적 매핑 (공통+확통+미적분, 기하 없음) ─────────────

    _D38: dict = {
        **{n: "D" for n in [1, 2, 23, 31]},                               # 하
        **{n: "C" for n in list(range(3, 9)) + list(range(16, 20))
                             + list(range(24, 28)) + list(range(32, 36))}, # 중
        **{n: "B" for n in list(range(9, 14)) + [20, 29, 37]},            # 상
        **{n: "A" for n in [14, 15, 21, 22, 28, 30, 36, 38]},             # 최상
    }

    _T38: dict = {
        **{n: "객관식" for n in list(range(1, 16))
                               + list(range(23, 29)) + list(range(31, 37))},
        **{n: "주관식" for n in list(range(16, 23)) + [29, 30, 37, 38]},
    }

    # ── 30형 정적 매핑 ───────────────────────────────────────────

    _D30: dict = {
        **{n: "D" for n in range(1, 4)},                                  # 하
        **{n: "C" for n in list(range(4, 14)) + list(range(22, 26))},    # 중
        **{n: "B" for n in list(range(14, 19)) + [26, 27]},              # 상
        **{n: "A" for n in list(range(19, 22)) + list(range(28, 31))},   # 최상
    }

    _T30: dict = {
        **{n: "객관식" for n in range(1, 22)},
        **{n: "주관식" for n in range(22, 31)},
    }

    def __init__(self):
        self._exam_form: int = 46         # 46 / 38 / 30
        self._unit_map: dict = {}         # {problem_num(int): unit_code(str)}
        self._tag_map: dict = {}          # {problem_num(int): tag(str)}  예: {12: "원순열"}

    # ── BaseIndexer 인터페이스 ────────────────────────────────────

    def get_schema(self) -> dict:
        return {
            "label": "모의고사",
            "fields": [],   # 모든 메타데이터를 파일명 + 사이드카 CSV에서 자동 추출
        }

    def get_required_db_key(self) -> str:
        """파일명 파싱으로 year를 채우므로 빈 폼에서도 통과하도록 source 사용."""
        return "source"

    def has_tags(self) -> bool:
        return False

    def can_index(self, file_path: str) -> bool:
        """사이드카 _units.csv가 있는 파일만 인덱싱 허용."""
        base = os.path.splitext(file_path)[0]
        return os.path.exists(base + "_units.csv")

    def extract_metadata(self, file_path: str, form_values: dict) -> dict:
        """
        파일명에서 연도를 파싱하고, 사이드카 CSV에서 단원코드를 로드한다.

        연도 파싱 우선순위:
          1. [XXXX] 패턴 (예: HIDDENKICE모의고사[2025]...)
          2. YYYY년 패턴 fallback (예: 25031801_2025년03월18일대성수학)

        _exam_form 판단:
          - year >= 2027 → 30형
          - CSV 최대 문제번호 >= 39 → 46형
          - CSV 최대 문제번호 <= 38 → 38형
          - CSV 없음 → 46형 (기본값)
        """
        result = dict(form_values)
        filename = os.path.basename(file_path)

        # 연도 파싱: [XXXX] 우선, 실패 시 YYYY년 fallback
        m = re.search(r'\[(\d{4})\]', filename)
        if not m:
            m = re.search(r'(\d{4})년', filename)

        year = None
        if m:
            year = int(m.group(1))
            result["year"] = str(year)

        # 30형 판단: 연도 2027 이상 → 30형 확정
        if year is not None and year >= 2027:
            self._exam_form = 30
        else:
            self._exam_form = 46  # 임시, CSV 로드 후 재판단

        # 공통 메타
        result["subject"]    = "수학"
        result["curriculum"] = "2022개정교육과정"
        result["source"]     = "MOCK_EXAM"

        # 사이드카 CSV 로드
        base = os.path.splitext(file_path)[0]
        csv_path = base + "_units.csv"
        self._unit_map = {}
        self._tag_map = {}
        if os.path.exists(csv_path):
            try:
                with open(csv_path, newline='', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        num  = int(row.get("문제번호", row.get("num", 0)))
                        code = row.get("unit_code", row.get("code", "")).strip()
                        tag  = row.get("tag", "").strip()
                        if num and code:
                            self._unit_map[num] = code
                        if num and tag:
                            self._tag_map[num] = tag
            except Exception:
                pass

        # 38형 vs 46형 최종 판단 (30형은 위에서 이미 확정됨)
        if self._exam_form != 30:
            max_num = max(self._unit_map.keys(), default=0)
            if 0 < max_num <= 38:
                self._exam_form = 38
            else:
                self._exam_form = 46  # max_num==0(CSV없음) 또는 >=39

        result["exam_type"] = f"{self._exam_form}형"

        return result

    # ── 번호 기반 조회 메서드 (파서에서 호출) ─────────────────────

    def set_actual_problem_count(self, count: int) -> None:
        """파서에서 실제 미주 개수 확인 후 호출.
        unit_code용 _exam_form은 유지하고, difficulty/type용 _type_form을 보정."""
        if count >= 45:
            self._type_form = 46
        elif count >= 29:
            self._type_form = 38
        else:
            self._type_form = 30

    def difficulty_by_number(self, num: int) -> str:
        """문제 번호 → 난이도. 실제 문항 수(_type_form) 기준."""
        form = getattr(self, '_type_form', self._exam_form)
        if form == 46:
            return self._D46.get(num, "")
        elif form == 38:
            return self._D38.get(num, "")
        else:  # 30형
            return self._D30.get(num, "")

    def problem_type_by_number(self, num: int) -> str:
        """문제 번호 → 객관식/주관식. 실제 문항 수(_type_form) 기준."""
        form = getattr(self, '_type_form', self._exam_form)
        if form == 46:
            return self._T46.get(num, "객관식")
        elif form == 38:
            return self._T38.get(num, "객관식")
        else:  # 30형
            return self._T30.get(num, "객관식")

    def unit_code_by_number(self, num: int) -> str:
        """문제 번호 → 단원코드 (사이드카 CSV에서 로드, 없으면 빈 문자열)."""
        return self._unit_map.get(num, "")

    def tag_by_number(self, num: int) -> str:
        """문제 번호 → 태그 (사이드카 CSV tag 컬럼, 없으면 빈 문자열).
        예: N1원 문제는 tag='원순열' 반환."""
        return self._tag_map.get(num, "")
