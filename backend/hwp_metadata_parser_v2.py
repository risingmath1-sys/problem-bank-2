"""
HWP Metadata Parser V2 - Direct HWP Indexing Strategy
Purpose: Extract metadata and coordinates directly from HWP files for bulk registration.
"""

import os
import re
import json
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor
try:
    import msvcrt # For file locking on Windows
except ImportError:
    msvcrt = None
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import win32com.client as win32

try:
    from backend.hwp_core import RobustHwpController
except ImportError:
    from hwp_core import RobustHwpController

try:
    from backend.app.db.firebase import get_firestore_db
except ImportError:
    try:
        from app.db.firebase import get_firestore_db
    except ImportError:
        get_firestore_db = None


@dataclass
class ProblemRecord:
    problem_id: str
    file_name: str
    endnote_index: int
    school: str
    year: str
    grade: str
    semester: str
    exam_type: str
    subject: str
    curriculum: str
    unit_code: str
    mapped_unit_code: str  # [New] for 2015->2022 compatibility
    difficulty: str
    problem_type: str  # 객관식 / 주관식
    pos_start: List[int]
    pos_end: List[int]
    large_unit: str = ""
    middle_unit: str = ""
    source: str = ""       # 소스 타입: NAESIN_A, NAESIN_N, SUNEUNG_SPECIAL, etc.
    indexed_at: float = 0.0
    file_hash: str = ""
    search_text: str = ""
    tags: str = ""         # 쉼표 구분 태그 (예: "원순열")

class RegistrationLogManager:
    """Manages indexing progress to allow resuming."""
    def __init__(self, log_path: str = "registration_log.json"):
        self.log_path = log_path
        self.logs = self._load_logs()

    def _load_logs(self) -> Dict:
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                print(f"[RegistrationLog] 로그 파일 JSON 파싱 오류 ({self.log_path}): {e} → 빈 로그로 시작")
                return {}
            except Exception as e:
                print(f"[RegistrationLog] 로그 파일 읽기 실패 ({self.log_path}): {e} → 빈 로그로 시작")
                return {}
        return {}

    def is_processed(self, filename: str) -> bool:
        return filename in self.logs and self.logs[filename].get("status") == "done"

    def save_log(self, filename: str, status: str, count: int = 0):
        self.logs[filename] = {
            "status": status,
            "problem_count": count,
            "timestamp": time.time()
        }
        # Thread-safe write if multiple workers used (though we use 1 for HWP safety)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.logs, f, ensure_ascii=False, indent=2)

class HWPMetadataParserV2:
    def __init__(self, output_dir: str = "indexed_results", config_path: str = "curriculum_config.json", engine=None):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # 항상 __file__ 기준 절대 경로 사용 → CWD에 무관하게 동일한 로그 파일 참조
        _log_abs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registration_log.json")
        self.log_manager = RegistrationLogManager(_log_abs)
        self.unit_names, self.curr_map = self._load_config(config_path)
        self.medium_to_large, self.medium_names_hier = self._load_unit_hierarchy()
        # Phase 5: 활성 엔진 (LocalDBEngine | FirestoreEngine) — _post_process_file 에서 사용.
        # None 이면 legacy 직접 sqlite3 + naive _sync_to_firebase 폴백 (CLI/스크립트 호환).
        self.engine = engine

    def _load_config(self, path: str) -> tuple:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("unit_mappings", {}), data.get("curriculum_mappings", {})
            except json.JSONDecodeError as e:
                print(f"[Parser] curriculum_config JSON 파싱 오류 ({path}): {e} → 단원코드 매핑 없이 진행")
            except Exception as e:
                print(f"[Parser] curriculum_config 읽기 실패 ({path}): {e} → 단원코드 매핑 없이 진행")
        else:
            print(f"[Parser] curriculum_config 파일 없음 ({path}) → 단원코드 매핑 없이 진행")
        return {}, {}

    def _load_unit_hierarchy(self) -> tuple:
        """unit_hierarchy.json에서 중단원코드 → (대단원명, 중단원명) 매핑 로드.

        Returns:
            (medium_to_large, medium_names_hier)
            medium_to_large:  {중단원코드 → 대단원명}
            medium_names_hier: {중단원코드 → 중단원명}  ← curriculum_config 누락 코드 보완용
        """
        hier_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unit_hierarchy.json")
        medium_to_large = {}
        medium_names_hier = {}
        try:
            if os.path.exists(hier_path):
                with open(hier_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 2022를 먼저 로드하여 우선순위 확보.
                # 2015에 동일 코드가 있어도 덮어쓰지 않음 (2022 H3=지수함수 vs 2015 H3=독립시행의확률 충돌 방지)
                for version in ["2022", "2015"]:
                    for subj in data.get(version, []):
                        for large in subj.get("large_units", []):
                            large_name = large.get("name", "")
                            for med in large.get("medium_units", []):
                                code = med["code"]
                                if code not in medium_to_large:   # 2022 정의 우선, 2015가 덮어쓰지 못함
                                    medium_to_large[code] = large_name
                                if code not in medium_names_hier:
                                    medium_names_hier[code] = med.get("name", "")
        except Exception:
            pass
        return medium_to_large, medium_names_hier

    def scan_folder(self, folder_path: str, common_meta: Dict, max_workers: int = 1, visible: bool = True, force_reindex: bool = False, progress_callback: Optional[callable] = None, stealth_mode: bool = False, indexer=None):
        """
        Scans all HWP files in bulk.
        """
        print(f"\n[Bulk Indexing] Start: {folder_path} (Workers: {max_workers}, Force: {force_reindex}, Stealth: {stealth_mode})")
        
        hwp_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".hwp")]
        
        def log(msg):
            if progress_callback: progress_callback(msg)
            else: print(msg)

        tasks = []
        for filename in hwp_files:
            file_path = os.path.join(folder_path, filename)
            # [PRE-CHECK] 인덱서가 사전 조건을 정의한 경우 (e.g. 모의고사 _units.csv 필요)
            if indexer and hasattr(indexer, 'can_index') and not indexer.can_index(file_path):
                log(f"Skipping (사전조건 미충족, 단원CSV 없음?): {filename}")
                continue
            if force_reindex or not self.log_manager.is_processed(filename):
                tasks.append((folder_path, filename, common_meta, indexer))
            else:
                log(f"Skipping (done): {filename}")

        if not tasks:
            log("No new files.")
            return

        # [SESSION PERSISTENCE] Reuse one controller for the entire batch to avoid repeated popups
        # 스텔스 모드 전략: Open() 전에 창을 숨기면 "허용하시겠습니까?" 다이얼로그도
        # 숨겨져 타임아웃 발생. 대신 Open() 완료 후 숨김 (hwp_core.py CMD_OPEN 참조).
        # → 컨트롤러를 visible=not stealth_mode 로 생성해 워커에 의도 전달.
        # 매핑 실패 통계 초기화 (이번 배치 한정)
        self._mapping_failures = {}
        with RobustHwpController(visible=not stealth_mode) as ctrl:
            for task in tasks:
                self._worker_thread_file(*task, visible, log, controller=ctrl)
        # 인덱싱 종료 후 매핑 실패 요약 보고 (재발 방지)
        self._report_mapping_failures(log)

    def _report_mapping_failures(self, log_func: callable):
        """매핑 실패한 [중단원] 텍스트 요약 보고 (2026-05-23 추가).
        목적: D1(행렬) 누락 같은 매핑 누락을 인덱싱 후 즉시 발견.
        """
        failures = getattr(self, "_mapping_failures", {}) or {}
        if not failures:
            return
        total = sum(failures.values())
        log_func("")
        log_func("=" * 60)
        log_func(f"⚠️  매핑 실패 단원명 요약 ({total}건 / {len(failures)}개 고유)")
        log_func("=" * 60)
        sorted_fails = sorted(failures.items(), key=lambda x: -x[1])
        for key, n in sorted_fails[:30]:
            unit_text, school_level = key.split("|", 1) if "|" in key else (key, "?")
            log_func(f"  [{n:4d}] '{unit_text}' (school_level={school_level})")
        if len(sorted_fails) > 30:
            log_func(f"  ... 외 {len(sorted_fails)-30}개 단원명")
        log_func("")
        log_func("→ 위 단원명들이 'backend/indexers/naesin_n_unit_map.json' 에 추가되어야 합니다.")
        log_func("=" * 60)

    def scan_file(self, file_path: str, common_meta: Dict, visible: bool = True, progress_callback: Optional[callable] = None, stealth_mode: bool = False, indexer=None):
        """
        Processes a single HWP file.
        """
        folder_path = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        def log(msg):
            if progress_callback: progress_callback(msg)
            else: print(msg)

        log(f"\n[Single File Indexing] Start: {filename} (Stealth: {stealth_mode})")
        
        # 스텔스 모드 전략: Open() 전에 창을 숨기지 않는다 (타임아웃 원인).
        # Open() 완료 후 숨김은 hwp_core.py CMD_OPEN 핸들러가 처리.
        with RobustHwpController(visible=not stealth_mode) as ctrl:
            self._worker_thread_file(folder_path, filename, common_meta, indexer, visible, log, controller=ctrl)

    def _worker_thread_file(self, folder_path: str, filename: str, common_meta: Dict, indexer, visible: bool, log_func: callable, controller=None):
        try:
            from backend.hwp_core import RobustHwpController
        except ImportError:
            from hwp_core import RobustHwpController
        
        file_path = os.path.join(folder_path, filename)
        log_func(f"Processing: {filename}")
        
        try:
            if controller:
                problems = self._process_single_file(controller, file_path, filename, common_meta, indexer, log_func=log_func)
                self._post_process_file(filename, problems, log_func)
            else:
                with RobustHwpController(visible=visible) as ctrl:
                    problems = self._process_single_file(ctrl, file_path, filename, common_meta, indexer, log_func=log_func)
                    self._post_process_file(filename, problems, log_func)
                    
        except Exception as e:
            self.log_manager.save_log(filename, f"error: {str(e)}")
            log_func(f" -> ERROR: {filename}: {e}")

    def _process_single_file(self, ctrl: win32.CDispatch, file_path: str, filename: str, common_meta: Dict, indexer, log_func: callable) -> List[ProblemRecord]:
        if not ctrl.open(file_path):
            raise Exception("HWP Open Failed")

        # [METADATA] 소스별 파일명 파싱으로 common_meta 보강 (수능특강 등 파일명 기반 인덱서)
        if indexer and hasattr(indexer, 'extract_metadata'):
            common_meta = indexer.extract_metadata(file_path, common_meta)

        # [HASH] Generate file hash for change detection
        file_hash = ""
        try:
            with open(file_path, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except:
            pass

        # [PRE-PROCESSING] Remove paragraph numbers and format endnotes
        log_func(f"   - [전가공] 문단번호 삭제 및 미주 가공 중...")
        ctrl.remove_paragraph_numbers()
        endnote_positions = ctrl.find_all_endnotes()
        if endnote_positions:
            ctrl.format_endnotes(endnote_positions)
            
        # [SAVE] Ensure the cleansed file is saved (idx logic: 0-indexed)
        count = ctrl.get_doc_count()
        doc_idx = count - 1 if count > 0 else 0
        ctrl.save(doc_idx)
        log_func(f"   - [저장] 원본 파일 가공 완료 및 저장됨.")
        
        log_func(f"   -> Found {len(endnote_positions)} endnotes (COM)")
        if not endnote_positions: 
            ctrl.close_doc(doc_idx)
            return []

        # ============================================================
        # [XML-BASED PARSING] Export HWPML2X and parse in pure Python
        # Replaces: full_text, tag_matches, column detection round-trips
        # ============================================================
        xml_result = None
        col_break_positions = None  # Will be set from XML or fallback to COM
        endnote_xml_positions = None  # (note_num, para_idx) from XML
        tag_from_xml = {}           # {note_num: metadata_tag_text}
        problem_text_from_xml = {}  # {note_num: problem_text}
        
        try:
            from hwp_xml_parser import HWPXMLParser
        except ImportError:
            try:
                from backend.hwp_xml_parser import HWPXMLParser
            except ImportError:
                HWPXMLParser = None
        
        if HWPXMLParser:
            try:
                log_func(f"   - [XML] HWPML2X 내보내기 및 파싱 중...")
                xml_str = ctrl.get_xml(timeout=60)
                if xml_str:
                    xml_parser = HWPXMLParser()
                    xml_result = xml_parser.parse_xml_string(xml_str)
                    endnote_xml_positions = {num: pidx for num, pidx in xml_result.get('endnote_positions', [])}
                    col_break_positions = xml_result.get('col_break_positions', [])
                    tag_from_xml = {num: xml_parser.parse_metadata_tag(txt) 
                                    for num, txt in xml_result.get('endnote_texts', {}).items()}
                    problem_text_from_xml = xml_result.get('problem_texts', {})
                    log_func(f"   - [XML] {len(endnote_xml_positions)}개 미주, {len(col_break_positions)}개 단넘김 추출 완료")
                else:
                    log_func(f"   - [XML] 내보내기 실패, COM 방식으로 계속 진행")
            except Exception as e_xml:
                log_func(f"   - [XML] 파싱 오류 ({e_xml}), COM 방식으로 계속 진행")
        
        # [FALLBACK] Until XML covers 100% cases, get full text via COM too (for tag extraction)
        full_text = ctrl.get_text()

        # [SUNEUNG_COMPLETE] 유형 경계 기반 상급 문제 인덱스 사전 계산
        wansung_high_set = set()
        if common_meta.get("source") == "SUNEUNG_COMPLETE" and indexer:
            if hasattr(indexer, "compute_high_difficulty_indices"):
                wansung_high_set = indexer.compute_high_difficulty_indices(full_text)
                log_func(f"   - [수능완성] 상급 문제 인덱스(1-based): {sorted(wansung_high_set)}")

        # Precise Tag and Symbol Analysis - from COM full text (confirmed accurate)
        tag_matches = list(re.finditer(r'(\[[^\]/]+/[^\]]+\])', full_text))

        # [NAESIN_N] 본문 평문 태그 사전 매치 ([중단원] / [난이도])
        naesin_n_unit_matches = []
        naesin_n_diff_matches = []
        if common_meta.get("source") == "NAESIN_N":
            naesin_n_unit_matches = list(re.finditer(r'\[중단원\]\s*(.+)', full_text))
            naesin_n_diff_matches = list(re.finditer(r'\[난이도\]\s*(.+)', full_text))
            log_func(f"   - [NAESIN_N] 중단원 태그 {len(naesin_n_unit_matches)}개, 난이도 태그 {len(naesin_n_diff_matches)}개 감지")
        
        # [NEW] At-marker detection list for no-tag sources (e.g. SuneungSpecial)
        at_marker_positions = []
        if indexer and not getattr(indexer, "has_tags", lambda: True)():
            # Find all '@' characters not part of normal words. 
            # Transparent @ markers will just appear as '@' in text
            at_marker_positions = [m.start() for m in re.finditer(r'@', full_text)]

        # === GOLDEN RULES EXTRACTION (원장님 공식) ===
        # Rule 1: 단 중간 문제 → 다음 미주 -3칸
        # Rule 2: 단 끝 문제 → 단 끝 (MoveColumnEnd)
        # Rule 3: 문서 마지막 → 페이지 끝 (MovePageEnd)
        
        # 실제 미주 개수를 인덱서에 알려줌 (exam_form 보정용)
        if indexer and hasattr(indexer, 'set_actual_problem_count'):
            indexer.set_actual_problem_count(len(endnote_positions))

        # [FIX] 미주번호 연속(파일간 이어지는) 경우 대응: i+1 대신 sorted keys 상대 인덱스 사용
        # 2024 수능특강처럼 _02_ 파일 미주가 21번부터 시작하면 i+1(=1)로 key 조회 시 전부 miss → D로 오저장
        _xml_sorted_keys = sorted(problem_text_from_xml.keys()) if problem_text_from_xml else []

        problems = []
        for i, endnote_pos in enumerate(endnote_positions):
            # 시작 위치 결정:
            # 내신기출A(내기왕, NAESIN_A)만 미주 바로 윗 줄(태그 줄)부터 시작
            # 그 외 모든 소스(수능특강, 모의고사 등)는 미주가 있는 줄부터 시작
            if common_meta.get("source") == "NAESIN_A":
                start_pos = (endnote_pos[0], max(0, endnote_pos[1] - 1), 0)
            else:
                start_pos = (endnote_pos[0], endnote_pos[1], 0)
            
            # 끝 위치 결정 - COM 기반 (검증된 방식)
            if i + 1 < len(endnote_positions):
                next_endnote = endnote_positions[i+1]
                
                # 현재와 다음 문제의 단(Column) 번호 확인
                ctrl.set_pos(*start_pos)
                current_col_info = ctrl.get_column_info()
                current_col = current_col_info.get('current_col', 0) if current_col_info else 0
                
                ctrl.set_pos(next_endnote[0], next_endnote[1], 0)
                next_col_info = ctrl.get_column_info()
                next_col = next_col_info.get('current_col', 0) if next_col_info else 0
                
                if current_col == next_col:
                    # Rule 1: 같은 단 → 다음 미주 앞 N칸
                    # 수능특강/모의고사는 다음 미주 바로 위에 라벨(이미지 1줄)이 있어 -2칸 처리
                    _src = common_meta.get("source", "")
                    offset = 2 if _src in ("SUNEUNG_SPECIAL", "MOCK_EXAM") else 1
                    end_para = max(start_pos[1], next_endnote[1] - offset)
                    end_pos = (endnote_pos[0], end_para, 0)
                    log_func(f"   - [Rule 1] 단 중간 (Col {current_col}): Para {start_pos[1]} → {end_para} (offset={offset})")
                else:
                    # Rule 2: 다른 단 → 현재 단 끝
                    ctrl.set_pos(*start_pos)
                    end_pos = ctrl.move_column_end()
                    if end_pos:
                        log_func(f"   - [Rule 2] 단 끝 (Col {current_col}→{next_col}): Para {start_pos[1]} → {end_pos[1]}")
                    else:
                        end_pos = (start_pos[0], start_pos[1] + 15, 0)
                        log_func(f"   - [Rule 2 Fallback]: Para {start_pos[1]} → {end_pos[1]}")
            else:
                # Rule 3: 마지막 문제 — 소스 구분 없이 페이지 끝으로 통일
                # (Rule 3-S 삭제: 수특 종결@ 바로 위에 마커 삽입 시 end_pos가 빈 줄로 잡히는 버그)
                ctrl.set_pos(*start_pos)
                end_pos = ctrl.move_page_end()
                if end_pos:
                    log_func(f"   - [Rule 3] 마지막 문제: Para {start_pos[1]} → {end_pos[1]} (페이지 끝)")
                else:
                    end_pos = (start_pos[0], start_pos[1] + 20, 0)
                    log_func(f"   - [Rule 3 Fallback] Para {start_pos[1]} → {end_pos[1]}")

            # [NAESIN_N] end_pos를 [중단원] 바로 위 단락으로 칼같이 조정
            # 문제 내용 = 미주번호 ~ [중단원] 윗줄 (태그/서술형 안내 등 완전 제외)
            if common_meta.get("source") == "NAESIN_N":
                for para_idx in range(start_pos[1], end_pos[1] + 1):
                    para_text = ctrl.get_para_text(start_pos[0], para_idx) or ""
                    if '[중단원]' in para_text:
                        new_end = max(start_pos[1], para_idx - 1)
                        if new_end <= start_pos[1]:
                            # ★ [BUG FIX] [중단원]이 미주 단락 바로 다음(또는 같은 줄)에 위치 →
                            # new_end == start_pos[1] → end_pos = start_pos → 제로 스팬 → 빈 문제
                            # 해결: 미주 단락 끝 좌표로 설정 (단락 전체를 문제 본문으로 포함)
                            ctrl.set_pos(start_pos[0], start_pos[1], 0)
                            para_end = ctrl.get_para_end()
                            if para_end:
                                end_pos = para_end
                                log_func(f"   - [NAESIN_N] 단일 단락 문제 (Para {start_pos[1]}): end_pos = Para 끝 {para_end}")
                            else:
                                log_func(f"   - [NAESIN_N] 단일 단락 문제 (Para {start_pos[1]}): get_para_end 실패, end_pos 유지")
                        else:
                            log_func(f"   - [NAESIN_N] end_pos 조정: Para {end_pos[1]} → {new_end} ([중단원] 위 줄)")
                            end_pos = (end_pos[0], new_end, 0)
                        break

            # --- Trailing Blanks Trimming ---
            end_pos = self._trim_trailing_blanks(ctrl, start_pos, end_pos, log_func)


            # --- Precise Text Range for MCQ Analysis ---

            if common_meta.get("source") == "NAESIN_N" and i < len(naesin_n_unit_matches):
                # [NAESIN_N] [중단원] 태그가 문제 내용 뒤에 위치하므로
                # p_text_end = 이 문제의 [중단원] 시작 직전
                # p_text_start 우선순위:
                #   1) 직전 문제의 [난이도] 끝  (가장 정확)
                #   2) 직전 문제의 [중단원] 끝  (주관식 등 [난이도] 없을 때 fallback)
                #   3) 0 (첫 문제)
                p_text_end = naesin_n_unit_matches[i].start()
                if i > 0 and (i - 1) < len(naesin_n_diff_matches):
                    p_text_start = naesin_n_diff_matches[i - 1].end()
                elif i > 0 and (i - 1) < len(naesin_n_unit_matches):
                    p_text_start = naesin_n_unit_matches[i - 1].end()
                else:
                    p_text_start = 0
                problem_snippet = full_text[p_text_start:p_text_end]
            elif i < len(tag_matches):
                p_text_start = tag_matches[i].start()
                if i+1 < len(tag_matches):
                    p_text_end = tag_matches[i+1].start()
                else:
                    # [FIX] Last problem: limit to 2000 chars to avoid including
                    # answer sections that contain ①②③ from other problems
                    p_text_end = min(p_text_start + 2000, len(full_text))
                problem_snippet = full_text[p_text_start:p_text_end]
            else:
                # If there are no tags (like SuneungSpecial), use approximate snippet
                p_text_start = start_pos[1] * 30 # Rough approximation without precise char count mapping
                problem_snippet = ""
            
            tag_str = tag_matches[i].group() if i < len(tag_matches) else ""

            # [NAESIN_A Fallback] full_text 스캔에서 태그 누락 시
            # 미주 바로 위 단락(endnote_pos[1]-1)을 직접 읽어 태그 추출
            if not tag_str and common_meta.get("source") == "NAESIN_A":
                tag_para_idx = endnote_pos[1] - 1
                if tag_para_idx >= 0:
                    raw_para = ctrl.get_para_text(endnote_pos[0], tag_para_idx) or ""
                    clean_para = re.sub(r'[\r\n\t\s]+', '', raw_para)
                    if re.match(r'^\[.*\/.*\]$', clean_para):
                        tag_str = clean_para
                        log_func(f"      [NAESIN_A Fallback] Problem {i+1}: 미주 위 단락에서 태그 직접 추출 → {tag_str}")

            # [NAESIN_N] 본문 평문 태그에서 중단원/난이도 직접 추출 (_parse_tag 우회)
            if common_meta.get("source") == "NAESIN_N":
                try:
                    from backend.indexers.naesin_n import lookup_unit_code
                except ImportError:
                    from indexers.naesin_n import lookup_unit_code
                unit_text = naesin_n_unit_matches[i].group(1).strip() if i < len(naesin_n_unit_matches) else ""
                diff_raw  = naesin_n_diff_matches[i].group(1).strip() if i < len(naesin_n_diff_matches) else ""
                school_level = common_meta.get("school_level", "고등")
                u_code_n  = lookup_unit_code(unit_text, school_level)
                diff_n    = {"킬": "A", "상": "B", "중": "C", "하": "D"}.get(diff_raw, "")
                meta = dict(common_meta)
                meta["unit_code"]  = u_code_n
                meta["difficulty"] = diff_n
                if unit_text and not u_code_n:
                    log_func(f"      [NAESIN_N] Problem {i+1}: '{unit_text}' → 매핑 없음")
                    # 2026-05-23: 매핑 실패 단원명 통계 수집 (인덱싱 끝에 요약 보고)
                    if not hasattr(self, "_mapping_failures"):
                        self._mapping_failures = {}
                    key = f"{unit_text}|{school_level}"
                    self._mapping_failures[key] = self._mapping_failures.get(key, 0) + 1
                else:
                    log_func(f"      [NAESIN_N] Problem {i+1}: '{unit_text}' → {u_code_n}, '{diff_raw}' → {diff_n}")
            else:
                meta = self._parse_tag(tag_str, common_meta)
            
            # --- Type Detection (Priority: Tag -> Heuristic) ---
            prob_type = "주관식"
            difficulty = meta.get("difficulty", "")
            
            if indexer and not getattr(indexer, "has_tags", lambda: True)():
                # For tagless sources (e.g., SuneungSpecialIndexer), apply their logic
                # Extract specific field metadata from the filename previously parsed
                meta = dict(common_meta) # use filename-parsed metadata

                # Look for '@' markers BEFORE this endnote's rough position 
                # (For reliability, we simply count how many @ markers appeared before this problem's endnote)
                # Note: 'i' is the problem index (0-based)
                # Since we don't have perfect char-to-paragraph mapping here, we use a simpler approach:
                # if there are 3 @ markers total, and 30 problems, we can try to guess by approximate text position
                # But even better: we can simply use the exact character index from XML or COM text
                # We can search for the endnote tag (e.g. \x02 \x03 or just number) in text, but it's brittle.
                
                # Using XML 'problem_text_from_xml' to find @ markers
                # [FIX] _xml_sorted_keys[i] 사용: 미주번호 연속(21,22...) 파일도 올바른 key 참조
                xml_snippet = problem_text_from_xml.get(_xml_sorted_keys[i], "") if i < len(_xml_sorted_keys) else ""
                if xml_snippet:
                    problem_snippet = xml_snippet

                if hasattr(indexer, "resolve_section_type"):
                    # XML 기반 누적 @ 카운팅 (신뢰성 높음)
                    # problem_text_from_xml[k] = 미주k 단락 ~ 미주(k+1) 단락 직전까지의 텍스트
                    # @ 마커는 섹션 끝 문제의 텍스트 범위 안에 포함됨
                    # 문제 i (0-indexed) 앞에 나온 @ 개수
                    #   = sorted_keys[0..i-1] 텍스트의 @ 합계
                    # [FIX] range(1, i+1) → range(i): note_num이 1부터 시작하지 않아도 동작
                    if problem_text_from_xml:
                        at_count = sum(
                            problem_text_from_xml.get(_xml_sorted_keys[p], "").count('@')
                            for p in range(i)
                        )
                    elif at_marker_positions:
                        # XML 없을 때: 비율 추정 (fallback)
                        ratio = (i + 0.5) / max(1, len(endnote_positions))
                        est_char_idx = int(len(full_text) * ratio)
                        at_count = sum(1 for pos in at_marker_positions if pos < est_char_idx)
                    else:
                        at_count = 0
                        
                    
                    sec_type = indexer.resolve_section_type(at_count)
                    difficulty = indexer.difficulty_from_section_type(sec_type)
                    meta["difficulty"] = difficulty
                    meta["section_type"] = sec_type
                    log_func(f"      [@ Marker] Problem {i+1}: {at_count} markers found -> {sec_type} / Diff: {difficulty}")

            # [SUNEUNG_COMPLETE] 유형별 마지막 문제 = 상, 나머지 = 중
            # 전체 마지막 문제는 항상 상급
            if common_meta.get("source") == "SUNEUNG_COMPLETE":
                is_last_problem = (i == len(endnote_positions) - 1)
                difficulty = "B" if (i + 1) in wansung_high_set or is_last_problem else "C"
                meta["difficulty"] = difficulty
                log_func(f"      [수능완성] Problem {i+1}: difficulty={difficulty}")

            # [NUMBER-BASED] 번호 기반 난이도/유형 오버라이드 (모의고사 등)
            if indexer and hasattr(indexer, 'difficulty_by_number'):
                nd = indexer.difficulty_by_number(i + 1)
                if nd:
                    meta["difficulty"] = nd
                    log_func(f"      [번호기반] Problem {i+1}: difficulty={nd}")
            if indexer and hasattr(indexer, 'problem_type_by_number'):
                nt = indexer.problem_type_by_number(i + 1)
                if nt:
                    meta["problem_type"] = nt
                    log_func(f"      [번호기반] Problem {i+1}: type={nt}")

            tag_type = meta.get("problem_type")
            prob_type = tag_type if tag_type else self._detect_type_from_snippet(problem_snippet)
            
            # [RULE] 주관식 역전 방지 규칙 (내신기출 전용):
            # 내신기출 시험지에서 주관식 → 객관식 역전은 절대 없음.
            # 한 번 주관식이 나오면 이후 모든 문제는 주관식으로 강제.
            # 수능특강 등 다른 소스에는 이 가정이 성립하지 않으므로 제외.
            is_naesin = common_meta.get("source", "") in ("NAESIN_A", "NAESIN_N")
            if is_naesin and problems and problems[-1].problem_type in ("주관식", "단답형", "서답형"):
                if prob_type == "객관식":
                    log_func(f"      [RULE] 앞 문제가 주관식이므로 주관식으로 강제 지정. (내신기출 전용)")
                    prob_type = problems[-1].problem_type

            
            # Record Creation
            u_code = meta.get("unit_code", common_meta.get("unit_code", ""))

            # [NUMBER-BASED] 번호 기반 단원코드 오버라이드 (모의고사 사이드카 CSV)
            num_tag = ""
            if indexer and hasattr(indexer, 'unit_code_by_number'):
                num_unit = indexer.unit_code_by_number(i + 1)
                if num_unit:
                    u_code = num_unit
                    log_func(f"      [번호기반] Problem {i+1}: unit_code={num_unit}")
            if indexer and hasattr(indexer, 'tag_by_number'):
                num_tag = indexer.tag_by_number(i + 1)

            # --- Curriculum Mapping ---
            # 2026-05-23 정상화: 2015/2022 코드 체계가 unit_hierarchy.json 에서 통합됨 →
            # 변환 불필요. 옛 매핑(curriculum_mappings.2015_to_2022)은 폐기됨.
            # original_code 변수는 mapped_unit_code 필드 호환을 위해 빈 문자열로 유지.
            original_code = ""

            # 메타데이터 딕셔너리에 추가
            # problem_data는 아래에서 생성되므로, 여기서 미리 변수에 담아둠

            # 중단원명 조회: curriculum_config unit_mappings 우선, 없으면 unit_hierarchy fallback
            middle_name = self.unit_names.get(u_code) or self.medium_names_hier.get(u_code)
            # 대단원명 조회 (medium_to_large: 중단원코드 → 대단원명)
            large_name = self.medium_to_large.get(u_code, "")
            if not middle_name:
                if u_code:
                    log_func(f"      [WARNING] Problem {i+1}: Unknown Unit Code [{u_code}]")
                    middle_name = u_code  # 코드 자체를 이름으로 fallback
                else:
                    log_func(f"      [WARNING] Problem {i+1}: Missing/Invalid Tag")
                    middle_name = "미분류"
            # num_tag → tags 컬럼에 저장 (middle_unit은 변경하지 않음)
            # 예: N1원 → unit_code=N1, middle_unit="여러가지 순열", tags="원순열"

            problems.append(ProblemRecord(
                problem_id=f"{filename.replace('.hwp', '')}_{i+1}",
                file_name=filename,
                endnote_index=i+1,
                school=meta.get("school", common_meta.get("school", "")),
                year=common_meta.get("year", meta.get("year", "")),
                grade=common_meta.get("grade", common_meta.get("grade", "")),
                semester=common_meta.get("semester", common_meta.get("semester", "")),
                exam_type=common_meta.get("exam_type", common_meta.get("exam_type", "")),
                subject=common_meta.get("subject", common_meta.get("subject", "")),
                curriculum=common_meta.get("curriculum", common_meta.get("curriculum", "")),
                unit_code=u_code,           # 항상 2022 코드
                mapped_unit_code=original_code,  # 원본 2015 코드 (2022는 "")
                source=common_meta.get("source", ""),
                large_unit=large_name,
                middle_unit=middle_name,
                difficulty=meta.get("difficulty", ""),
                problem_type=prob_type,
                pos_start=list(start_pos),
                pos_end=list(end_pos),
                indexed_at=time.time(),
                file_hash=file_hash,
                search_text=f"{filename} {meta.get('school', '')} {common_meta.get('subject', '')} {middle_name} {prob_type}".strip(),
                tags=num_tag
            ))
            
            log_func(f"      Problem {i+1}: {prob_type} | {start_pos} -> {end_pos}")

        # [NAESIN POST-PROCESS] 단조 구조 강제: [객관식...객관식...주관식...주관식]
        # 내신기출 시험지는 반드시 객관식 블록 → 주관식 블록 순서. 역전 불가.
        # 규칙①(루프 내): 주관식 이후 객관식 역전 방지 (이미 적용됨)
        # 규칙②(여기): 원본 탐지 기준으로 [객관식 → 주관식] 경계에서
        #              한 칸씩 역방향으로 밀어 올림 (주관식 사이에 객관식 침입 방지)
        #   → detected[j]=객관식 AND detected[j+1]=주관식 이면 j를 주관식으로 보정
        #   → 원본 탐지값 기준 1회 패스 (연쇄 변환 방지)
        is_naesin_source = common_meta.get("source", "") in ("NAESIN_A", "NAESIN_N")
        if is_naesin_source and len(problems) > 1:
            original_types = [p.problem_type for p in problems]
            for j in range(len(problems) - 1):
                if (original_types[j] == "객관식" and
                        original_types[j + 1] in ("주관식", "단답형", "서답형")):
                    problems[j].problem_type = original_types[j + 1]
                    log_func(f"      [NAESIN RULE②] Problem {j+1}: 객관식→{original_types[j+1]} 보정 (다음 문제가 주관식)")

        # [CLOSE] Close document at the very end to prevent resource leak
        ctrl.close_doc(doc_idx)
        log_func(f"   - [해제] 문서 세션 반환 완료.")

        return problems

    def _post_process_file(self, filename: str, problems: List[ProblemRecord], log_func: callable):
        """Saves results locally and routes DB write through the active engine.

        Phase 5: self.engine 가 설정되면 engine.ingest_indexed_problems(results) 한
        번으로 LocalDB(SQLite) 또는 Firestore + write-through 캐시 동시 처리.
        엔진 미주입(CLI/스크립트) 시 legacy 직접 sqlite3 + naive Firestore set() 으로 폴백.
        """
        if problems:
            self.log_manager.save_log(filename, "done", len(problems))
            results = [asdict(p) for p in problems]
            save_path = os.path.join(self.output_dir, f"{filename}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            log_func(f" -> SUCCESS: Indexed {len(problems)} problems.")

            # [DB SYNC] 엔진 라우팅 (Phase 5)
            if self.engine is not None:
                try:
                    n = self.engine.ingest_indexed_problems(results)
                    log_func(f"   - [DB] {n}개 문항 DB 업데이트 완료.")
                except Exception as e:
                    log_func(f"   - [DB 오류] 엔진 ingest 실패: {e}")
            else:
                # Legacy fallback — 직접 sqlite3 + naive Firebase
                try:
                    import sqlite3 as _sqlite3
                    db_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "problem_bank.db"))
                    conn = _sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    for item in results:
                        pos_start_str = json.dumps(item.get("pos_start", []))
                        pos_end_str = json.dumps(item.get("pos_end", []))
                        pnum = item.get("endnote_index")
                        src = item.get("source", "")
                        if src == "MOCK_EXAM" and pnum is not None:
                            exam_num = pnum if pnum <= 22 else (pnum - 22 - 1) % 8 + 23
                        else:
                            exam_num = None
                        cursor.execute("""
                            INSERT OR REPLACE INTO problems (
                                id, file_name, endnote_index, school, year, grade,
                                semester, exam_type, subject, curriculum, unit_code, mapped_unit_code,
                                source, difficulty, problem_type, pos_start, pos_end,
                                large_unit, middle_unit, indexed_at, file_hash, search_text,
                                problem_number, exam_number, tags
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item.get("problem_id"),
                            item.get("file_name"),
                            item.get("endnote_index"),
                            item.get("school"),
                            item.get("year"),
                            item.get("grade"),
                            item.get("semester"),
                            item.get("exam_type"),
                            item.get("subject"),
                            item.get("curriculum"),
                            item.get("unit_code"),
                            item.get("mapped_unit_code"),
                            src,
                            item.get("difficulty"),
                            item.get("problem_type"),
                            pos_start_str,
                            pos_end_str,
                            item.get("large_unit"),
                            item.get("middle_unit"),
                            item.get("indexed_at"),
                            item.get("file_hash"),
                            item.get("search_text"),
                            pnum,
                            exam_num,
                            item.get("tags", "")
                        ))
                    conn.commit()
                    conn.close()
                    log_func(f"   - [DB] {len(problems)}개 문항 DB 업데이트 완료.")
                except Exception as e:
                    log_func(f"   - [DB 오류] DB 업데이트 실패: {e}")

                if get_firestore_db:
                    log_func(f"   - [동기화] Firebase 업로드 중...")
                    sync_count = self._sync_to_firebase(problems)
                    log_func(f"   - [완료] {sync_count}개 문항 서버 저장 완료.")
        else:
            self.log_manager.save_log(filename, "no_problems", 0)
            log_func(f" -> Warning: No problems found.")

    def _parse_tag(self, tag_str: str, common_meta: Dict) -> Dict:
        content = tag_str.strip("[]")
        parts = [p.strip() for p in content.split('/')]
        meta = {"school": "", "year": "", "unit_code": "", "difficulty": "", "problem_type": ""}
        for p in parts:
            # 1. School
            if any(k in p for k in ["고", "중", "학교"]) and len(p) > 2: 
                meta["school"] = p
            # 2. Year
            elif re.match(r'^\d{4}', p): 
                meta["year"] = p[:4]
            # 3. Unit Code — "G1"(정확), "G1이차방정식"(코드+한글명), "이차방정식"(순수한글) 모두 지원
            elif re.match(r'^[A-Z][0-9]', p):
                meta["unit_code"] = p[:2]   # "G1이차방정식" → "G1"
            # 4. Difficulty — 태그 구조: [.../단원/난이도/적합도]
            # 적합도(마지막 A/B/C)가 난이도를 덮어쓰지 않도록 first-match만 허용
            # 한글(상/중/하/최상) → 영문코드(A/B/C/D) 정규화 (DB 포맷 통일)
            elif p in ["최상", "상", "중", "하", "A", "B", "C", "D"]:
                if not meta["difficulty"]:
                    _kr = {"최상": "A", "상": "B", "중": "C", "하": "D"}
                    meta["difficulty"] = _kr.get(p, p)  # 한글이면 변환, 영문이면 그대로
            # 5. Type (Future-proofing for 단답형/서답형)
            elif any(k in p for k in ["객", "주", "단", "서"]):
                if "객" in p: meta["problem_type"] = "객관식"
                elif "서" in p: meta["problem_type"] = "서답형"
                elif "단" in p: meta["problem_type"] = "단답형"
                elif "주" in p: meta["problem_type"] = "주관식"
            # 6. 순수 한글 단원명 → 역매핑 fallback (unit_code 추출 안 된 경우)
            elif p and not meta["unit_code"] and re.search(r'[가-힣]', p):
                norm_p = p.replace(' ', '')
                for code, name in self.medium_names_hier.items():
                    if name and norm_p == name.replace(' ', ''):
                        meta["unit_code"] = code
                        break
        return meta

    def _detect_type_from_snippet(self, snippet: str) -> str:
        if any(sym in snippet for sym in ["①", "②", "③", "④", "⑤"]):
            return "객관식"
        return "주관식"

    def _sync_to_firebase(self, problems: List[ProblemRecord]) -> int:
        """Uploads problem records to Firestore."""
        db = get_firestore_db()
        if not db: return 0
        
        count = 0
        for p in problems:
            try:
                doc_ref = db.collection("problems").document(p.problem_id)
                doc_ref.set(asdict(p))
                count += 1
            except Exception as e:
                print(f"      [!] Firebase sync error: {e}")
        return count

    def _trim_trailing_blanks(self, ctrl, start_pos, rough_end_pos, log_func):
        """
        Scans backward from rough_end_pos to find the last paragraph with actual content.
        Safety: if trimming would result in span≤0, returns rough_end_pos unchanged.
        """
        if not rough_end_pos:
            return rough_end_pos

        list_id = rough_end_pos[0]
        end_para = rough_end_pos[1]
        start_para = start_pos[1]
        
        # span이 이미 0이면 트리밍 불필요
        if end_para <= start_para:
            return rough_end_pos
        
        while end_para > start_para:
            text = ctrl.get_para_text(list_id, end_para)
            if text is None:
                text = ""
                
            clean_text = re.sub(r'[\r\n\t\s]+', '', text)
            
            if clean_text:
                # 태그 줄(`[학교/년/...]`)이면 건너뜀
                if re.match(r'^\[.*\/.*\]$', clean_text):
                    if log_func:
                        log_func(f"      [Trim] Skip tag line: {clean_text}")
                    end_para -= 1
                    continue
                # 유효한 텍스트 발견 → 중지
                break
            
            # 텍스트가 없어도 인라인 수식/이미지 컨트롤이 있을 수 있음
            char_count = ctrl.get_para_char_count(list_id, end_para)
            if char_count and char_count > 0:
                break
            
            # 진짜 빈 문단
            end_para -= 1
        
        # ── 안전 장치 ──────────────────────────────────────────────────
        # 트리밍 결과 span ≤ 0이면 원본 end_pos 복원.
        # 앵커(떠있는) 이미지/수식 프레임은 char_count=0 으로 보이기 때문에
        # 과도한 트리밍이 일어날 수 있음. 그 경우 빈 줄 포함이 낫다.
        if end_para <= start_para:
            if log_func:
                log_func(f"      [Trim] Safety: trim would cause span=0, reverting to original end={rough_end_pos[1]}")
            return rough_end_pos
        
        if end_para != rough_end_pos[1]:
            if log_func:
                log_func(f"      [Trim] Adjusted end from {rough_end_pos[1]} to {end_para} (-{rough_end_pos[1] - end_para} blanks)")
            
        ctrl.set_pos(list_id, end_para, 0)
        precise_end = ctrl.get_para_end()
        if precise_end:
            return precise_end
            
        return (list_id, end_para, 0)

