"""HWP 원본 파일 탐색 / 검증 — main_gui._find_source_hwp 포팅."""
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from server import config

_INDEX_CACHE: Optional[Dict[str, str]] = None


def _build_index() -> Dict[str, str]:
    """HWP_SOURCE_ROOT 하위 모든 .hwp 파일을 {basename: abspath} 로 인덱싱."""
    idx: Dict[str, str] = {}
    root = config.HWP_SOURCE_ROOT
    if not root.exists():
        return idx
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if not fname.lower().endswith(".hwp"):
                continue
            # 동일 basename 중복 시 첫 발견 우선 (main_gui 와 동일 동작)
            idx.setdefault(fname, os.path.join(dirpath, fname))
    return idx


def get_index(force_rebuild: bool = False) -> Dict[str, str]:
    global _INDEX_CACHE
    if _INDEX_CACHE is None or force_rebuild:
        _INDEX_CACHE = _build_index()
    return _INDEX_CACHE


def find(filename: str) -> Optional[str]:
    """파일명 → 절대경로. 없으면 None."""
    if not filename:
        return None
    idx = get_index()
    return idx.get(filename)


def validate_problems(problems: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """main_gui.py:4683-4726 의 검증 단계 포팅.

    각 문제의 file_path 가 유효한지 확인하고, 없으면 file_name 으로 재탐색.
    Returns: (validated, skipped)
        skipped: [{id, file_name, request_index, reason}] - 출제에서 제외된 문제 목록
            request_index: 원래 요청 리스트에서의 1-base 순번 (누락 번호 표시용)
    """
    validated: List[Dict] = []
    skipped: List[Dict] = []
    rebuilt = False
    for i, p in enumerate(problems):
        req_idx = i + 1  # 1-base — 로컬 main_gui.py:4714 와 동일
        fpath = p.get("file_path")
        fname = p.get("file_name")
        if fpath and os.path.exists(fpath):
            # request_index 를 살아남은 문제에도 부여 — generate_exam 의 skipped_problems
            # 가 이걸 그대로 들고 다닐 수 있도록.
            p = dict(p)
            p.setdefault("request_index", req_idx)
            validated.append(p)
            continue
        if not fname:
            skipped.append({
                "id": p.get("id") or "?",
                "file_name": None,
                "request_index": req_idx,
                "reason": "file_name 누락",
            })
            continue
        found = find(fname)
        if not found and not rebuilt:
            # 인덱스가 오래됐을 수 있음 - 1회 재빌드 후 재시도
            get_index(force_rebuild=True)
            rebuilt = True
            found = find(fname)
        if found:
            p = dict(p)  # 원본 mutate 방지
            p["file_path"] = found
            p.setdefault("request_index", req_idx)
            validated.append(p)
        else:
            skipped.append({
                "id": p.get("id") or "?",
                "file_name": fname,
                "request_index": req_idx,
                "reason": f"파일 없음: {fname}",
            })
    return validated, skipped
