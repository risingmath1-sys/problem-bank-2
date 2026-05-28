"""HWP 출제 작업 큐 + 단일 워커 (직렬화).

설계:
- 서버 시작 시 _worker_loop 백그라운드 task 1개 시작.
- /api/exam/random 가 enqueue → Job state=queued
- 워커가 하나씩 꺼냄 → state=running → loop.run_in_executor 로 generate_exam 동기 실행 → state=done 또는 failed
- HWP COM 인스턴스는 generate_exam 내부에서 매 호출마다 새로 띄우고 정리 (controller=None 전달).
  추후 워커 lifecycle 에 source/target 인스턴스 1쌍 영구화 가능 (TODO).
"""
import asyncio
import time
import uuid
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from server import config

JOB_TTL_SECONDS = 60 * 60  # 1시간 후 자동 정리 (다운로드 받았으면 됐음)


@dataclass
class Job:
    id: str
    user_id: str
    problems: List[Dict]
    options: Dict[str, Any]
    kind: str = "exam"  # exam | indexing
    state: str = "queued"  # queued | running | done | failed
    progress_msg: str = "대기 중..."
    progress_pct: int = 0  # 진행률 %
    error: Optional[str] = None
    result_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    total: int = 0
    success: int = 0
    skipped: List[Dict] = field(default_factory=list)
    # indexing 전용 필드
    indexing_log: List[str] = field(default_factory=list)  # 진행 로그 (최근 N줄)
    indexing_stats: Dict[str, int] = field(default_factory=dict)  # files/problems/errors


class JobQueue:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.jobs: Dict[str, Job] = {}
        self._worker_task: Optional[asyncio.Task] = None

    def start(self, loop: asyncio.AbstractEventLoop):
        self._worker_task = loop.create_task(self._worker_loop())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass

    async def submit(self, job: Job) -> str:
        self.jobs[job.id] = job
        await self._queue.put(job)
        return job.id

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def cleanup_old(self):
        """TTL 지난 job 정리."""
        cutoff = time.time() - JOB_TTL_SECONDS
        stale = [jid for jid, j in self.jobs.items() if j.finished_at and j.finished_at < cutoff]
        for jid in stale:
            j = self.jobs.pop(jid, None)
            if j and j.result_path and Path(j.result_path).exists():
                try:
                    Path(j.result_path).unlink()
                except OSError:
                    pass

    async def _worker_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            job: Job = await self._queue.get()
            try:
                job.state = "running"
                job.started_at = time.time()
                if job.kind == "indexing":
                    job.progress_msg = "인덱싱 시동 중..."
                    await loop.run_in_executor(None, _run_indexing, job)
                else:
                    job.progress_msg = "HWP 시동 중..."
                    await loop.run_in_executor(None, _run_generate, job)
                if job.error:
                    job.state = "failed"
                else:
                    job.state = "done"
            except Exception as e:
                job.state = "failed"
                job.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            finally:
                job.finished_at = time.time()
                self._queue.task_done()
                self.cleanup_old()


def _run_generate(job: Job):
    """워커 스레드 본체 — hwp_generator.generate_exam 호출."""
    from backend.hwp_generator import HWPGenerator
    import re

    target_dir = config.EXAM_RESULTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # 로컬 main_gui.py:4554-4577 와 동등 — 파일명 생성
    # 기본 파일명 자동 생성: 시험지제목[단원].hwp
    _title = (job.options.get("exam_title") or "").strip()
    _unit  = (job.options.get("exam_unit", "") or "").strip()

    # 제목이 없으면 기본값 사용
    if not _title:
        from datetime import datetime
        _title = f"시험지_{datetime.now().strftime('%Y%m%d')}"

    # 파일명 생성: 제목[단원] 또는 제목만
    if _title and _unit:
        _default_name = f"{_title}[{_unit}]"
    elif _title:
        _default_name = _title
    else:
        _default_name = "시험지"

    # 파일명에 사용 불가 문자 제거 (로컬과 동일)
    _default_name = re.sub(r'[\\/:*?"<>|]', '_', _default_name)

    target_path = target_dir / f"{_default_name}.hwp"

    total = len(job.problems)
    job.total = total

    def on_progress(msg: str):
        # generate_exam 이 다양한 메시지를 보냄. 진행률 추정: "N/M" 패턴 찾기.
        job.progress_msg = msg
        # "1/10 진행" 같은 패턴이면 % 추산
        import re
        m = re.search(r"(\d+)\s*/\s*(\d+)", msg)
        if m:
            cur = int(m.group(1)); tot = int(m.group(2))
            if tot > 0:
                job.progress_pct = min(100, int(cur * 100 / tot))

    # ★ enqueue 단계에서 setter 된 pre_skipped (validate에서 걸러진 누락) 를 보존
    pre_skipped = list(job.skipped)

    generator = HWPGenerator()
    try:
        result = generator.generate_exam(
            str(target_path),
            job.problems,
            progress_callback=on_progress,
            exclude_tags=job.options.get("exclude_tags", False),
            stealth_mode=job.options.get("stealth_mode", True),
            fast_answer_key=False,
            db=None,
            exam_title=job.options.get("exam_title", ""),
            exam_unit=job.options.get("exam_unit", ""),
        )
    except Exception as e:
        job.error = f"generate_exam 호출 실패: {type(e).__name__}: {e}"
        return

    if not target_path.exists() or target_path.stat().st_size == 0:
        job.error = "출력 파일이 생성되지 않았습니다."
        return

    job.result_path = str(target_path)
    job.success = (result or {}).get("success", 0)

    # ★ pre_skipped(validate에서 걸러진 것) + gen_skipped(generate_exam 중 스킵된 것) 합산
    #   — 로컬 main_gui.py:4770 의 _all_skipped 와 동등
    gen_skipped = (result or {}).get("skipped_problems", []) or []
    job.skipped = pre_skipped + list(gen_skipped)

    job.progress_pct = 100

    # ★ 출제 불일치 메시지 — 로컬 main_gui.py:4782-4790 와 동등
    if job.total > 0 and job.success < job.total:
        nums = sorted(
            s.get("request_index") for s in job.skipped
            if s.get("request_index")
        )
        nums_str = ", ".join(str(n) for n in nums) or "(번호 추적 실패)"
        job.progress_msg = (
            f"완료 — 목표 {job.total}문제 → 실제 {job.success}문제 출제 "
            f"(누락 번호: {nums_str})"
        )
    else:
        job.progress_msg = f"완료 — {job.success}/{job.total} 출제됨"


def _run_indexing(job: Job):
    """워커 스레드 본체 — HWPMetadataParserV2.process 호출 (인덱싱).

    options:
      source       : 'NAESIN_A' / 'NAESIN_N' / 'SUNEUNG_SPECIAL' 등
      target_path  : 폴더 또는 파일 경로 (서버 기준 절대 경로)
      is_folder    : True 면 폴더 일괄, False 면 단일 파일
      force_reindex: 기존 데이터 덮어쓰기
      stealth_mode : 백그라운드 모드
      common_meta  : 인덱서별 공통 메타 (curriculum/subject/year 등)
    """
    import os
    from backend.hwp_metadata_parser_v2 import HWPMetadataParserV2
    from backend.indexer_registry import get_indexer
    from server.services.engine import get_engine

    source = job.options.get("source") or ""
    target_path = job.options.get("target_path") or ""
    is_folder = bool(job.options.get("is_folder", True))
    force_reindex = bool(job.options.get("force_reindex", False))
    stealth_mode = bool(job.options.get("stealth_mode", True))
    common_meta = job.options.get("common_meta") or {}

    if not source:
        job.error = "source 가 비어있습니다."
        return
    if not target_path or not os.path.exists(target_path):
        job.error = f"대상 경로를 찾을 수 없습니다: {target_path}"
        return

    indexer = get_indexer(source)
    if indexer is None:
        job.error = f"인덱서 미구현: {source}"
        return

    # 작업 디렉토리 — 서버 측 결과는 server_data/indexed_results/ 로
    output_dir = config.SERVER_DATA_DIR / "indexed_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = config.BASE_DIR / "backend" / "curriculum_config.json"
    engine = get_engine()
    parser = HWPMetadataParserV2(
        output_dir=str(output_dir),
        config_path=str(cfg_path),
        engine=engine,
    )

    # 진행 로그 콜백
    log_max = 100  # 최근 100줄만 유지

    def on_progress(msg: str):
        try:
            line = str(msg or "").strip()
            if not line:
                return
            job.progress_msg = line
            job.indexing_log.append(line)
            if len(job.indexing_log) > log_max:
                del job.indexing_log[:-log_max]
            # "1/10" 패턴이면 % 갱신
            import re
            m = re.search(r"(\d+)\s*/\s*(\d+)", line)
            if m:
                cur = int(m.group(1)); tot = int(m.group(2))
                if tot > 0:
                    job.progress_pct = min(99, int(cur * 100 / tot))
        except Exception:
            pass

    # 인덱싱 전 DB 카운트 — 인덱싱 후 증감으로 통계 추정
    try:
        before_count = engine.query_counts({"source": source}, include_excluded=True)
    except Exception:
        before_count = 0

    try:
        if is_folder:
            parser.scan_folder(
                target_path,
                common_meta,
                max_workers=1,
                visible=False,  # 서버는 보이지 않게
                force_reindex=force_reindex,
                progress_callback=on_progress,
                stealth_mode=stealth_mode,
                indexer=indexer,
            )
        else:
            parser.scan_file(
                target_path,
                common_meta,
                visible=False,
                progress_callback=on_progress,
                stealth_mode=stealth_mode,
                indexer=indexer,
            )
    except Exception as e:
        job.error = f"인덱싱 실패: {type(e).__name__}: {e}"
        job.indexing_log.append(f"❌ {job.error}")
        return

    # 인덱싱 후 카운트 — 추가된 문제 수 추정
    try:
        after_count = engine.query_counts({"source": source}, include_excluded=True)
    except Exception:
        after_count = before_count
    added = max(0, after_count - before_count)

    # 처리한 파일 수 추정
    files_n = 1 if not is_folder else _count_hwp_files(target_path)

    job.indexing_stats = {
        "files": files_n,
        "problems": added,
        "errors": 0,  # 정확한 에러 카운트는 parser 가 별도로 노출하지 않음
        "db_total": after_count,
    }
    job.success = added
    job.total = added
    job.progress_pct = 100
    job.progress_msg = f"완료 — {files_n}파일 / 신규 {added}문제 (소스 총 {after_count})"


def _count_hwp_files(folder: str) -> int:
    import os
    n = 0
    try:
        for f in os.listdir(folder):
            if f.lower().endswith(".hwp"):
                n += 1
    except Exception:
        pass
    return n


# ──── 모듈 싱글톤 ────
_queue: Optional[JobQueue] = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue()
    return _queue
