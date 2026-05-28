#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2015 → 2022 변환 매핑 규칙 (단일 진실 소스).

원칙:
  - subject 옛 표기는 그대로 유지 (수학(상), 수학(하), 수학1, 수학2, 확률과 통계, 미적분, 기하)
  - unit_code 만 옛 → 새 코드로 변환
  - curriculum 은 "2015개정교육과정" 으로 통일
  - middle_unit/large_unit 은 새 unit_hierarchy 기준 재계산
  - 예외: '수(하)' 변종 → '수학(하)' 정규화 + 매핑
  - 예외: 옛 코드인데 subject='대수' → subject='수학1' 정정 + 매핑

매핑 표는 curriculum_config.json.bak_2026-05-23 의 2015_to_2022 79개에 기반.
누락 보완: P3, Q5, K5 등.
"""

# 옛 과목별 (옛코드 → 새코드) 매핑
OLD_SUBJECT_UNIT_MAP = {
    "수학(상)": {
        # 다항식 (그대로)
        "A1": "A1", "A2": "A2", "A3": "A3",
        # 방정식·부등식
        "B1": "B1", "B2": "B2", "B3": "B3",
        "B4": "B4", "B5": "B4", "B6": "B5",
        # 도형의 방정식 → 공통수학2
        "C1": "E1", "C2": "E2", "C3": "E3", "C4": "E4",
    },
    "수학(하)": {
        # 집합과 명제 → 공통수학2
        "D1": "F1", "D2": "F2", "D3": "F3",
        # 함수 → 공통수학2
        "E1": "G1", "E2": "G2", "E3": "G3",
        # 경우의 수 → 공통수학1
        "F1": "C1", "F2": "C2", "F3": "C3",
    },
    "수학1": {
        # 지수·로그 → 대수
        "J1": "H1", "J2": "H2", "J3": "H3", "J4": "H4", "J5": "H3",
        # 삼각함수 → 대수
        "K1": "I1", "K2": "I2", "K3": "I2", "K4": "I3", "K5": "I3",  # K5 추가 (혹시)
        # 수열 → 대수
        "L1": "J1", "L2": "J1", "L3": "J2", "L4": "J3", "L5": "J3",
    },
    "수학2": {
        # 함수의 극한과 연속 → 미적분I
        "M1": "K1", "M2": "K2",
        # 미분법 → 미적분I
        "N1": "L1", "N2": "L2", "N3": "L3", "N4": "L3", "N5": "L4", "N6": "L5",
        # 적분법 → 미적분I
        "O1": "M1", "O2": "M2", "O3": "M3", "O4": "M3",
    },
    "확률과 통계": {
        # 순열과 조합 → 확률과통계
        "G1": "N1", "G2": "N1", "G3": "N1", "G4": "N1",
        "G5": "N2", "G6": "N2", "G7": "N3",
        # 확률 → 확률과통계
        "H1": "O1", "H2": "O2", "H3": "O2",
        # 통계 → 확률과통계
        "I1": "P1", "I2": "P1", "I3": "P2", "I4": "P3",
    },
    "미적분": {
        # 수열의 극한 → 미적분II
        "P1": "Q1", "P2": "Q2", "P3": "Q2",  # P3(등비급수도형활용) → Q2(급수) 추가
        # 미분법 → 미적분II
        "Q1": "R1", "Q2": "R2", "Q3": "R3", "Q4": "R4", "Q5": "R5",
        # 적분법 → 미적분II
        "R1": "S1", "R2": "S3",
    },
    "기하": {
        # 이차곡선 → 기하
        "S1": "T1", "S2": "T2", "S3": "T3", "S4": "T4",
        # 평면벡터 → 기하 (V 코드)
        "T1": "V1", "T2": "V2", "T3": "V2",
        # 공간도형/공간좌표 → 그대로
        "U1": "U1", "U2": "U2",
    },
}

# subject 변종 정규화 (변환 전에 적용)
SUBJECT_NORMALIZE = {
    "수(하)":   "수학(하)",
    "수학하":   "수학(하)",
    "수학상":   "수학(상)",
    "수(상)":   "수학(상)",
    "수학 (상)": "수학(상)",
    "수학 (하)": "수학(하)",
    "수힉하":   "수학(하)",   # 오타
    "수1":      "수학1",
    "수2":      "수학2",
    "확통":     "확률과 통계",
    "확률과통계": "확률과 통계",   # (옛 표기 정규화. 새 표기는 그대로 '확률과통계')
    "미적":     "미적분",
    # '대수' + 옛 코드는 별도 처리 (아래 함수에서)
}

# 새 unit_code → (새 subject, 대단원, 중단원) — unit_hierarchy.json 에서 로드 가능
# 여기서는 일단 빈 dict, 런타임에 로드


def normalize_subject(subject: str) -> str:
    """변종 표기 → 표준 표기."""
    return SUBJECT_NORMALIZE.get(subject, subject)


def map_unit_code(subject: str, old_code: str) -> tuple:
    """
    (subject, old_unit_code) → (new_subject, new_unit_code).

    반환:
      (new_subject, new_unit_code) — 매핑 성공
      (None, None) — 매핑 실패 (변환 불가)
    """
    if not subject or not old_code:
        return (None, None)

    s = normalize_subject(subject)

    # 예외: '대수' + 옛 수학1 코드(J,K,L) → subject 를 '수학1' 으로 정정
    if s == "대수" and old_code and old_code[0] in "JKL":
        s = "수학1"

    table = OLD_SUBJECT_UNIT_MAP.get(s)
    if not table:
        return (None, None)

    new_code = table.get(old_code)
    if new_code is None:
        return (None, None)

    return (s, new_code)


if __name__ == "__main__":
    # 매핑 표 카운트
    total = 0
    for s, m in OLD_SUBJECT_UNIT_MAP.items():
        print(f"  {s}: {len(m)}개")
        total += len(m)
    print(f"총 {total}개 매핑")
