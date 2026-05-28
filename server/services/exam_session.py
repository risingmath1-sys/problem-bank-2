"""랜덤 출제 Step 3 용 사용자별 임시 출제 문항 저장.

로컬 main_gui.py 의 self.problem_batches / self._pre_sort_batches 를 서버 메모리로 포팅.

- 출제 문항이 batch 단위로 누적 (랜덤추가 → 새 batch)
- 정렬 직전 1회분 백업 → 정렬 취소 가능
- 한 사용자당 1개 draft. 새 출제 시작 시 reset.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ExamDraft:
    """한 사용자의 한 출제 세션 데이터."""
    batches: List[List[dict]] = field(default_factory=list)
    pre_sort_batches: Optional[List[List[dict]]] = None
    pre_skipped: List[dict] = field(default_factory=list)
    exam_title: str = ""
    exclude_tags: bool = False
    fast_answer_key: bool = False
    # 일회성 제외 (제외설정 다이얼로그) — 로컬 _oneshot_excluded_* 동등
    oneshot_excluded_test_ids: set = field(default_factory=set)
    oneshot_excluded_problem_ids: set = field(default_factory=set)
    # [랜덤추가] Step 2 → Step 3 전환 시점의 form 백업 — 로컬 _step2_filter_backup 동등.
    # FormData.multi_items() 결과를 그대로 보관 → 복원 시 FormData(items) 로 재구성.
    last_form_items: List[Tuple[str, str]] = field(default_factory=list)
    # [순서정렬] 직전 정렬 옵션 — 다이얼로그 재오픈 시 select/checkbox 미리 채움.
    # 키: sort_p1/p2/p3 (값: "(없음)" | "단원순" | "수준순" | "형식순" | "무작위"),
    #     sort_p1_rev/p2_rev/p3_rev (값: "1" | "")
    last_sort_options: Dict[str, str] = field(default_factory=dict)

    @property
    def all_problems(self) -> List[dict]:
        out = []
        for b in self.batches:
            out.extend(b)
        return out

    @property
    def total(self) -> int:
        return sum(len(b) for b in self.batches)

    def append_batch(self, problems: List[dict]) -> None:
        if problems:
            self.batches.append(list(problems))
        # 정렬 백업은 새 batch 추가 시 무효 (다른 작업 흐름)
        self.pre_sort_batches = None

    def remove_problem(self, problem_id: str) -> bool:
        """id 일치 문제 1건 제거. 빈 batch 자동 정리."""
        target = str(problem_id)
        for batch in self.batches:
            for p in batch:
                if str(p.get("id")) == target:
                    batch.remove(p)
                    self.batches = [b for b in self.batches if b]
                    self.pre_sort_batches = None
                    return True
        return False

    def apply_sort(self, sorted_flat: List[dict]) -> None:
        """정렬 결과(flat list)를 단일 batch 로 통합. 직전 batches 백업."""
        # 백업 (이미 백업 있으면 유지 — 직전 1회만 복원 가능)
        if self.pre_sort_batches is None:
            self.pre_sort_batches = [list(b) for b in self.batches]
        self.batches = [list(sorted_flat)] if sorted_flat else []

    def undo_sort(self) -> bool:
        if self.pre_sort_batches is None:
            return False
        self.batches = [list(b) for b in self.pre_sort_batches]
        self.pre_sort_batches = None
        return True

    def can_undo_sort(self) -> bool:
        return self.pre_sort_batches is not None

    def pop_last_batch(self) -> Optional[List[dict]]:
        """[이전] 버튼: 마지막 batch 제거 (랜덤추가 취소)."""
        if not self.batches:
            return None
        popped = self.batches.pop()
        self.pre_sort_batches = None
        return popped

    def reset(self) -> None:
        self.batches = []
        self.pre_sort_batches = None
        self.pre_skipped = []
        self.exam_title = ""
        self.exclude_tags = False
        self.fast_answer_key = False
        self.last_form_items = []
        self.last_sort_options = {}


_drafts: Dict[str, ExamDraft] = {}
_lock = threading.Lock()


def get_draft(user_id: str) -> ExamDraft:
    with _lock:
        d = _drafts.get(user_id)
        if d is None:
            d = ExamDraft()
            _drafts[user_id] = d
        return d


def reset_draft(user_id: str) -> None:
    """draft 전체 정리. 단, 정렬 옵션(last_sort_options)은 사용자 취향이라
    새 사이클로 이월 — 매번 새 랜덤출제 진입 시에도 다이얼로그가 직전 옵션을 기억."""
    with _lock:
        d = _drafts.pop(user_id, None)
        if d and d.last_sort_options:
            _drafts[user_id] = ExamDraft(last_sort_options=dict(d.last_sort_options))


def has_draft(user_id: str) -> bool:
    with _lock:
        d = _drafts.get(user_id)
        return d is not None and d.total > 0
