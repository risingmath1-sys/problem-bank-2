"""
NaesinAngIndexer - 내신기출(내기왕) 소스 인덱서.

파일명 형식: [YYYY-G-S-T][과목][학교][단원코드...]...
예시: [2024-2-2-F][기하][단대부고][02015][02003].hwp

특징:
- 모든 필드(연도/학년/학기/시험구분/과목/학교/교육과정) 파일명 자동 파싱 — 폼 입력 불필요
- 교육과정 자동 판단: year - grade >= 2024 → 2022개정, 그 외 → 2015교육과정
- 태그 있음 (has_tags=True, BaseIndexer 기본값 사용)
- 난이도는 태그에서 파싱 (hwp_metadata_parser_v2가 직접 처리)
"""

import os
import re

try:
    from backend.indexer_base import BaseIndexer
except ImportError:
    from indexer_base import BaseIndexer


# ── 과목명 정규화 매핑 ────────────────────────────────────────────────────
# 파일명에 나오는 다양한 표기 → DB 표준 과목명
# 키 비교는 소문자로, 값은 curriculum_config.json 표준 그대로

_SUBJ_2015 = {
    "수학상":       "수학(상)",
    "수(상)":       "수학(상)",
    "수학하":       "수학(하)",
    "수하":         "수학(하)",
    "수학(하)":     "수학(하)",
    "수힉하":       "수학(하)",   # 오타
    "수1":          "수학1",
    "수학1":        "수학1",
    "수학ⅰ":       "수학1",
    "수학i":        "수학1",
    "수학2":        "수학2",
    "미적분":       "미적분",
    "미적":         "미적분",
    "확통":         "확률과 통계",
    "확률과통계":   "확률과 통계",
    "확률과 통계":  "확률과 통계",
    "기하":         "기하",
}

_SUBJ_2022 = {
    "공수1":        "공통수학1",
    "공통수1":      "공통수학1",
    "공통수학1":    "공통수학1",
    "공수2":        "공통수학2",
    "공통수2":      "공통수학2",
    "공통수학2":    "공통수학2",
    "대수":         "대수",
    "미적분":       "미적분I",
    "미적":         "미적분I",
    "미적분i":      "미적분I",
    "미적분ⅰ":     "미적분I",
    "미적분ii":     "미적분II",
    "미적분ⅱ":     "미적분II",
    "확통":         "확률과통계",
    "확률과통계":   "확률과통계",
    "확률과 통계":  "확률과통계",
    "기하":         "기하",
}


def _detect_curriculum(year: int, grade: int) -> str:
    """
    연도 + 학년으로 교육과정 자동 판단.

    2022개정교육과정은 2025년 고1부터 최초 적용.
    고1이었던 연도 = year - grade + 1 >= 2025
    → year - grade >= 2024 → 2022개정
    """
    if year - grade >= 2024:
        return "2022개정교육과정"
    return "2015개정교육과정"  # 2026-05-26: DB 표기 통일


def _normalize_subject(raw: str, curriculum: str) -> str:
    """파일명 과목명 원본 → DB 표준 과목명 변환. 매핑 실패 시 원본 반환."""
    table = _SUBJ_2022 if "2022" in curriculum else _SUBJ_2015
    key = raw.strip()
    for k, v in table.items():
        if k.lower() == key.lower():
            return v
    return raw


def _parse_naesin_filename(file_path: str) -> dict:
    """
    파일명에서 내신기출 메타데이터 파싱.

    패턴: ...[YYYY-G-S-T][과목][학교][코드...]...
    - [YYYY-G-S-T]는 파일명 어디에 있어도 OK (중간 매칭)
    - 그 뒤 첫 번째 비숫자 대괄호 → 과목명
    - 두 번째 비숫자 대괄호 → 학교명

    반환: 파싱된 키만 포함된 dict
    """
    fname_noext = os.path.splitext(os.path.basename(file_path))[0]
    result = {}

    # [YYYY-G-S-T] 패턴
    m = re.search(r"\[(\d{4})-(\d)-(\d)-([MF])\]", fname_noext)
    if not m:
        return result

    result["year"]      = m.group(1)
    result["grade"]     = f"고{m.group(2)}"
    result["semester"]  = f"{m.group(3)}학기"
    result["exam_type"] = "기말고사" if m.group(4) == "F" else "중간고사"

    # 날짜 패턴 이후의 대괄호 내용 순서대로 추출
    rest = fname_noext[m.end():]
    brackets = re.findall(r"\[([^\]]+)\]", rest)

    # 첫 번째 비숫자 항목 → 과목명
    if brackets and not re.match(r"^\d+$", brackets[0]):
        result["subject_raw"] = brackets[0]
        brackets = brackets[1:]

    # 두 번째 비숫자 항목 → 학교명
    if brackets and not re.match(r"^\d+$", brackets[0]):
        result["school"] = brackets[0]

    return result


class NaesinAngIndexer(BaseIndexer):
    """내신기출(내기왕) 소스 — 모든 필드 파일명 자동 파싱, 폼 입력 불필요."""

    def get_schema(self) -> dict:
        return {
            "label": "내신기출A (내기왕)",
            "fields": [],  # 모든 필드 자동 파싱 — 폼 입력 없음
        }

    def get_required_db_key(self) -> str:
        """필수 폼 입력 없음 (모든 필드 파일명 자동 파싱)."""
        return ""

    def extract_metadata(self, file_path: str, form_values: dict) -> dict:
        """파일명에서 연도/학년/학기/시험구분/과목/학교/교육과정 모두 자동 파싱."""
        result = dict(form_values)

        parsed = _parse_naesin_filename(file_path)

        result["year"]      = parsed.get("year",      result.get("year", ""))
        result["grade"]     = parsed.get("grade",     result.get("grade", ""))
        result["semester"]  = parsed.get("semester",  result.get("semester", ""))
        result["exam_type"] = parsed.get("exam_type", result.get("exam_type", ""))
        result["school"]    = parsed.get("school",    result.get("school", ""))

        # 교육과정 자동 판단
        try:
            yr = int(parsed["year"])
            gr = int(re.search(r"\d+", parsed["grade"]).group())
            result["curriculum"] = _detect_curriculum(yr, gr)
        except Exception:
            result["curriculum"] = "2022개정교육과정"  # fallback

        if "subject_raw" in parsed:
            result["subject"] = _normalize_subject(parsed["subject_raw"], result["curriculum"])

        return result

    # has_tags()          → True  (BaseIndexer 기본값 사용)
    # detect_difficulty() → None  (BaseIndexer 기본값 사용, 파서가 태그 파싱)
    # get_exam_options()  → []    (BaseIndexer 기본값 사용)
