"""
ebs_subject_map.py — EBS/모의고사 파일명 과목 표기 → DB subject명 변환 공통 매핑.

수능특강, 수능완성, 모의고사 등 모든 외부 소스 인덱서가 공유한다.
DB에 저장되는 subject는 unit_hierarchy.json의 2022 subject명을 기준으로 한다.

파일명 표기 예시:
  EBS수능특강수학Ⅰ[2025]_01_지수와로그.hwp   → 과목 파싱: "수학Ⅰ" → DB: "대수"
  EBS수능완성수학Ⅱ[2025]_01_함수의극한.hwp   → 과목 파싱: "수학Ⅱ" → DB: "미적분I"
  [2025 수능] 수학 영역.hwp                   → 모의고사 공통 수학 (별도 처리)
"""

# EBS 파일명 과목 표기 → 2022 교육과정 DB subject명
# unit_hierarchy.json ["2022"] 기준
EBS_SUBJECT_MAP: dict[str, str] = {
    # 수학Ⅰ → 대수 (지수로그, 삼각함수, 수열)
    "수학Ⅰ":      "대수",
    "수학I":       "대수",
    "수학1":       "대수",

    # 수학Ⅱ → 미적분I (함수의극한·연속, 다항함수 미분·적분)
    "수학Ⅱ":      "미적분I",
    "수학II":      "미적분I",
    "수학2":       "미적분I",

    # 미적분 → 미적분II (수열의극한, 지수로그·삼각 미분법, 적분법)
    "미적분":      "미적분II",

    # 확률과통계
    "확률과통계":  "확률과통계",
    "확통":        "확률과통계",

    # 기하
    "기하":        "기하",
}


def resolve_ebs_subject(raw_subject: str) -> str | None:
    """
    파일명에서 파싱한 과목 문자열을 받아 DB subject명을 반환.
    매핑에 없으면 None 반환 → 호출측에서 수동 입력 요청.

    Args:
        raw_subject: 파일명에서 추출한 과목 문자열 (예: "수학Ⅰ", "미적분")

    Returns:
        DB subject명 (예: "대수", "미적분II") 또는 None
    """
    return EBS_SUBJECT_MAP.get(raw_subject.strip())
