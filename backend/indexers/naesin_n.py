"""
NaesinNIndexer - 내신기출B (N사) 소스 인덱서.

파일명 형식: [고/중][YYYY][G-S-T][지역][학교][과목][출판사?][단원범위?].hwp
예시: [고][2025][1-1-a][서울강남구][경기고][공수1][다항식의연산-이차함수].hwp
     [고][2025][1-1-a][서울강남구][휘문고][전재통][다항식의연산-이차함수].hwp  ← 과목 없이 출판사

특징:
- 폼 입력 없음 — 연도/학년/학기/시험구분/과목/학교 전부 파일명 자동 파싱
- 교육과정 자동 판단: year - grade >= 2024 → 2022개정, 그 외 → 2015교육과정
- 태그 있음 (has_tags=True) — 본문 평문 태그: [중단원] 한글명 / [난이도] 킬|상|중|하
- 난이도 매핑: 킬→A, 상→B, 중→C, 하→D
- unit_code: [중단원] 텍스트 → naesin_n_unit_map.json 룩업
- 문제 경계: 미주(endnote) 번호 = 문제 번호 (NAESIN_A와 동일)
- 문제 범위: endnote[N] ~ [중단원] 바로 위 줄
"""

import json
import os
import re

try:
    from backend.indexer_base import BaseIndexer
except ImportError:
    from indexer_base import BaseIndexer


# ── 난이도 매핑 ───────────────────────────────────────────────────────────────
_DIFFICULTY_MAP = {
    "킬": "A",
    "상": "B",
    "중": "C",
    "하": "D",
}

# ── 과목명 정규화 매핑 ────────────────────────────────────────────────────────
# 파일명에 나오는 다양한 표기 → DB 표준 과목명
_SUBJ_2015 = {
    "수학상":       "수학(상)",
    "수상":         "수학(상)",
    "수(상)":       "수학(상)",
    "수학(상)":     "수학(상)",
    "수학하":       "수학(하)",
    "수하":         "수학(하)",
    "수(하)":       "수학(하)",
    "수학(하)":     "수학(하)",
    "수힉하":       "수학(하)",   # 오타
    "수1":          "수학1",
    "수학1":        "수학1",
    "수학ⅰ":       "수학1",
    "수학i":        "수학1",
    "수2":          "수학2",
    "수학2":        "수학2",
    "수학ⅱ":       "수학2",
    "수학ii":       "수학2",
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

# 인식 가능한 과목명 집합 (소문자 기준) — 파일명에서 과목/출판사 구분용
_KNOWN_SUBJECTS_2015 = {k.lower() for k in _SUBJ_2015}
_KNOWN_SUBJECTS_2022 = {k.lower() for k in _SUBJ_2022}
_KNOWN_SUBJECTS_ALL  = _KNOWN_SUBJECTS_2015 | _KNOWN_SUBJECTS_2022


def _detect_curriculum(year: int, grade: int) -> str:
    """
    연도 + 학년으로 교육과정 자동 판단.

    2022개정교육과정은 2025년 고1부터 최초 적용.
    고1이었던 연도 = year - grade + 1 >= 2025
    → year - grade >= 2024 → 2022개정
    """
    if year - grade >= 2024:
        return "2022개정교육과정"
    return "2015개정교육과정"  # 2026-05-26: NAESIN_A 와 표기 통일


def _normalize_subject(raw: str, curriculum: str) -> str:
    """파일명 과목명 원본 → DB 표준 과목명. 매핑 실패 시 원본 반환."""
    table = _SUBJ_2022 if "2022" in curriculum else _SUBJ_2015
    key = raw.strip()
    for k, v in table.items():
        if k.lower() == key.lower():
            return v
    return raw


def _parse_naesin_n_filename(file_path: str) -> dict:
    """
    파일명에서 내신기출B 메타데이터 파싱.

    패턴: [고/중][YYYY][G-S-T][지역][학교][과목][출판사?][단원범위?].hwp
    - 학교명 다음 대괄호부터 순서대로 확인
    - 인식 가능한 과목명에 매칭되는 첫 번째 항목 → 과목
    - 과목 이후 항목 전부 무시 (떨거지)

    반환: 파싱된 키만 포함된 dict
    """
    fname_noext = os.path.splitext(os.path.basename(file_path))[0]
    result = {}

    # ① 고/중 구분
    if fname_noext.startswith("[고]"):
        result["school_level"] = "고등"
    elif fname_noext.startswith("[중]"):
        result["school_level"] = "중학"

    # 모든 대괄호 항목 순서대로 추출
    brackets = re.findall(r"\[([^\]]+)\]", fname_noext)
    if not brackets:
        return result

    idx = 0

    # 첫 항목은 고/중 → skip
    if brackets[idx] in ("고", "중"):
        idx += 1

    # ② 연도: [YYYY]
    if idx < len(brackets) and re.match(r"^\d{4}$", brackets[idx]):
        result["year"] = brackets[idx]
        idx += 1

    # ③ 학년-학기-시험구분: [G-S-T]  T: a=중간, b=기말
    if idx < len(brackets):
        m = re.match(r"^(\d)-(\d)-([ab])$", brackets[idx], re.IGNORECASE)
        if m:
            level_prefix = "중" if result.get("school_level") == "중학" else "고"
            result["grade"]     = f"{level_prefix}{m.group(1)}"
            result["semester"]  = f"{m.group(2)}학기"
            result["exam_type"] = "중간고사" if m.group(3).lower() == "a" else "기말고사"
            idx += 1

    # ④ 지역: 다음 항목 (숫자 아닌 항목)
    if idx < len(brackets) and not re.match(r"^\d+$", brackets[idx]):
        result["region"] = brackets[idx]
        idx += 1

    # ⑤ 학교명: 다음 항목
    if idx < len(brackets) and not re.match(r"^\d+$", brackets[idx]):
        result["school"] = brackets[idx]
        idx += 1

    # ⑥ 과목명: 학교명 이후 — 인식 가능한 과목명에 매칭될 때까지 순차 탐색
    #    매칭 안 되면 출판사명으로 간주하고 건너뜀
    #    과목 이후 항목은 전부 무시
    while idx < len(brackets):
        candidate = brackets[idx].strip()
        if candidate.lower() in _KNOWN_SUBJECTS_ALL:
            result["subject_raw"] = candidate
            break
        # 인식 불가 항목(출판사 등) → skip
        idx += 1

    return result


# ── unit_map 로드 (모듈 임포트 시 1회) ───────────────────────────────────────
_MAP_PATH = os.path.join(os.path.dirname(__file__), "naesin_n_unit_map.json")
try:
    with open(_MAP_PATH, encoding="utf-8") as _f:
        _UNIT_MAP_RAW = json.load(_f)
except Exception:
    _UNIT_MAP_RAW = {}

# 공백 제거 정규화된 룩업 테이블 (고등 / 중학 분리)
def _build_lookup(section: dict) -> dict:
    """공백 제거 후 소문자 키로 정규화된 룩업 테이블 생성."""
    tbl = {}
    for k, v in section.items():
        if k.startswith("_"):
            continue
        norm = k.replace(" ", "")
        tbl[norm] = v
    return tbl

_HS_LOOKUP = _build_lookup(_UNIT_MAP_RAW.get("high_school", {}))
_MS_LOOKUP = _build_lookup(_UNIT_MAP_RAW.get("middle_school", {}))


def lookup_unit_code(unit_text: str, school_level: str = "고등") -> str:
    """
    [중단원] 텍스트 → unit_code 변환.

    Args:
        unit_text:    태그에서 추출한 단원명 (예: "삼각함수의 그래프")
        school_level: "고등" 또는 "중학"

    Returns:
        unit_code 문자열 (예: "I2") 또는 "" (매핑 없으면)
    """
    norm = unit_text.strip().replace(" ", "")
    tbl = _MS_LOOKUP if school_level == "중학" else _HS_LOOKUP
    return tbl.get(norm, "")


def parse_naesin_n_tags(full_text: str) -> tuple[str, str]:
    """
    HWP 전체 텍스트에서 [중단원] / [난이도] 태그 추출.

    Returns:
        (unit_text, difficulty_code)  — 없으면 ("", "")
    """
    unit_text = ""
    difficulty_code = ""

    m_unit = re.search(r"\[중단원\]\s*(.+)", full_text)
    if m_unit:
        unit_text = m_unit.group(1).strip()

    m_diff = re.search(r"\[난이도\]\s*(.+)", full_text)
    if m_diff:
        raw_diff = m_diff.group(1).strip()
        difficulty_code = _DIFFICULTY_MAP.get(raw_diff, "")

    return unit_text, difficulty_code


class NaesinNIndexer(BaseIndexer):
    """내신기출B (N사) 소스 — 파일명 자동 파싱, 교육과정 자동 판단."""

    def get_schema(self) -> dict:
        return {
            "label": "내신기출B (N사)",
            "fields": [],   # 폼 입력 없음 — 전부 파일명 자동 파싱
        }

    def get_required_db_key(self) -> str:
        """필수 체크 항목 없음 (파일명에서 모두 자동 파싱)."""
        return ""

    def extract_metadata(self, file_path: str, form_values: dict) -> dict:
        """
        파일명에서 연도/학년/학기/시험구분/과목/학교/교육과정 자동 파싱.
        """
        result = dict(form_values)

        parsed = _parse_naesin_n_filename(file_path)

        result["year"]         = parsed.get("year",     result.get("year", ""))
        result["grade"]        = parsed.get("grade",    result.get("grade", ""))
        result["semester"]     = parsed.get("semester", result.get("semester", ""))
        result["exam_type"]    = parsed.get("exam_type",result.get("exam_type", ""))
        result["school"]       = parsed.get("school",   result.get("school", ""))
        result["school_level"] = parsed.get("school_level", "고등")

        # 교육과정 자동 판단
        try:
            year  = int(result["year"])
            grade = int(result["grade"].replace("고", "").replace("중", ""))
            result["curriculum"] = _detect_curriculum(year, grade)
        except (ValueError, KeyError):
            result["curriculum"] = ""

        # 과목명 정규화
        if "subject_raw" in parsed:
            result["subject"] = _normalize_subject(
                parsed["subject_raw"], result.get("curriculum", "")
            )

        return result

    # has_tags() → True  (BaseIndexer 기본값 — 미주 기반 문제 경계)
    # detect_difficulty() → None  (파서가 [난이도] 태그 직접 처리)
