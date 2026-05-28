import os
import time
import re
from typing import List, Dict
try:
    from backend.hwp_core import RobustHwpController
except ImportError as e:
    print(f"[HWPGenerator] Error importing HWP Controller: {e}")
    from hwp_core import RobustHwpController

class HWPGenerator:
    def __init__(self, controller: RobustHwpController = None):
        self.controller = controller

    def _extract_answers_from_xml(self, xml_content: str) -> List[str]:
        """
        Extracts answer text from HWPML2X XML content (endnotes).
        """
        answers = []
        try:
            if not xml_content:
                return []

            # 확인된 실제 구조: <ENDNOTE>...</ENDNOTE> (대문자, ENDNOTESHAPE와 구분)
            # 패턴 1: 대문자 ENDNOTE (한글 HWPML 구버전 포맷)
            matches = re.findall(r"<ENDNOTE>(.*?)</ENDNOTE>", xml_content, re.DOTALL)

            # 패턴 2: 소문자/네임스페이스 형태 (hp:endNote 등 신버전)
            if not matches:
                matches = re.findall(
                    r"<(?:hp:)?endNote[^>]*>(.*?)</(?:hp:)?endNote>",
                    xml_content, re.DOTALL | re.IGNORECASE
                )

            for note_body in matches:
                answer_text = ""

                # "[정답]" 키워드 위치 찾기
                ans_match = re.search(r'\[정답\]([^<]*)', note_body)
                if ans_match:
                    after_tag = ans_match.group(1).strip()
                    if after_tag:
                        # "[정답] ③" 또는 "[정답] 12" 처럼 텍스트가 바로 있는 경우
                        answer_text = after_tag
                    else:
                        # "[정답]" 뒤에 수식 등 태그가 오는 경우 → [정답] 이후 첫 번째 P만 파싱
                        remaining = note_body[ans_match.end():]
                        # 첫 번째 </P> 까지만 잘라서 사용 (풀이 부분 제외)
                        first_p_end = remaining.find('</P>')
                        first_p_area = remaining[:first_p_end] if first_p_end != -1 else remaining[:600]
                        # SCRIPT(수식 내부 텍스트) + CHAR 모두 긁어내기
                        parts = re.findall(r'<SCRIPT>(.*?)</SCRIPT>|<CHAR>([^<]+)</CHAR>', first_p_area, re.DOTALL)
                        tokens = []
                        for script_val, char_val in parts:
                            val = (script_val or char_val).strip()
                            if val:
                                tokens.append(val)
                        answer_text = " ".join(tokens).strip()

                if not answer_text:
                    # fallback: [정답] 못 찾은 경우 - 첫 번째 P에서 CHAR 합치기
                    all_p = re.findall(r"<P[^>]*>(.*?)</P>", note_body, re.DOTALL)
                    for p_body in all_p[:2]:
                        chars = re.findall(r"<CHAR>([^<]+)</CHAR>", p_body)
                        candidate = " ".join(chars).strip()
                        if candidate:
                            answer_text = candidate
                            break

                # XML 엔티티 언이스케이프 및 정리
                answer_text = answer_text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                answer_text = re.sub(r'\s+', ' ', answer_text).strip()
                answer_text = re.sub(r'^\[정답\]\s*', '', answer_text).strip()

                if answer_text:
                    answers.append(answer_text)
        except Exception as e:
            print(f"_extract_answers_from_xml error: {e}")
        return answers

    def _paste_verified(self, target_ctrl):
        """target_ctrl.paste() + 실제 붙여넣기 발생 여부 검증.
        paste 전후 커서 위치가 동일하면 클립보드 비었거나 paste 실패 → RuntimeError.
        호출자(generate_exam 루프)의 except 절이 잡아서 skipped_problems 처리."""
        pre = target_ctrl.get_pos()
        target_ctrl.paste()
        post = target_ctrl.get_pos()
        if pre and post and tuple(pre) == tuple(post):
            raise RuntimeError("paste no-op (clipboard empty or paste rejected)")

    def _remove_trailing_blank_lines(self, ctrl=None):
        """
        Remove trailing blank lines after pasting content.
        ctrl: 사용할 컨트롤러 (None이면 self.controller 사용)

        ★ [BUG FIX] 2026-03-08: 이전 구현(MovePrevPara + Delete 15회 반복)이
        그림/수식이 있는 단락에서 HWP 팝업("개체를 삭제하시겠습니까?")을 유발 →
        Delete timeout → target_ctrl Kill & Restart → target 문서 소실 → 연쇄 오류.
        → 안전을 위해 비활성화. 간격은 set_para_margin으로 조절.
        """
        pass  # 비활성화 (Delete timeout 버그 방지)

    def generate_exam(self, target_path: str, problem_list: List[Dict], progress_callback=None, exclude_tags=False, stealth_mode=False, fast_answer_key=False, db=None, exam_title="", exam_unit=""):
        """
        Generates an exam HWP file by copying problems from source files.
        stealth_mode: If True, hides HWP window after first connection.
        fast_answer_key: If True, generates a summary table of answers at the end.
        """
        def log(msg):
            if progress_callback: progress_callback(msg)
            else: print(f"[HWPGenerator] {msg}")

        print(f"[HWPGenerator] generate_exam called. fast_answer_key={fast_answer_key}, type={type(fast_answer_key)}")
        log("HWP 엔진 시동 중...")
        should_close = False
        if self.controller is None:
            # [Stealth Mode Logic]
            # 스텔스 모드: 처음부터 visible=False로 시작
            # 보안 팝업은 watchdog이 SendMessage(BM_CLICK)으로 처리 (창 숨겨도 작동)
            # 일반 모드: visible=True로 창 표시
            self.controller = RobustHwpController(visible=not stealth_mode)
            should_close = True
            if stealth_mode:
                log("스텔스 모드: 백그라운드 실행 중...")
            log("HWP 엔진 시동 완료.")

        # ★ target 전용 HWP 인스턴스 (2-인스턴스 분리 아키텍처)
        # source(self.controller)와 target(target_ctrl)을 완전히 분리 →
        # SetActive_XHwpDocument 포커스 역전 문제 원천 제거
        target_ctrl = RobustHwpController(visible=not stealth_mode)
        self.target_ctrl = target_ctrl  # helper 메서드(_insert_answer_list 등)에서 접근용
        log("target HWP 인스턴스 시동 완료.")

        # [BUG FIX] buffer_ctrl을 try 바깥에서 None으로 초기화 →
        # try 내 예외 발생 시 finally에서 안전하게 quit() 가능
        buffer_ctrl = None

        # ★ 출제 결과 추적 (불일치 감지용)
        result = {'total': 0, 'success': 0, 'skipped_problems': [], 'skipped_files': []}
        success_count = 0
        skipped_problems = []
        failed_files = set()  # try 블록 진입 전 초기화 (finally에서 참조)

        try:
            # 1. Open Target File (Template or Empty)
            template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "출제용-원본.hwp")

            # ★ [BUG FIX] 결과 저장 폴더가 없으면 미리 생성 (폴더 없음 → "디스크 에러" 원인)
            target_dir = os.path.dirname(target_path)
            if target_dir and not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                log(f"결과 폴더 생성: {target_dir}")

            # ★ [BUG FIX] 템플릿 백업 (.bak) — 템플릿이 오염됐을 때 복원용
            template_bak = template_path + ".bak"
            if os.path.exists(template_path) and not os.path.exists(template_bak):
                import shutil
                shutil.copy2(template_path, template_bak)
                log(f"템플릿 백업 생성: {os.path.basename(template_bak)}")

            if os.path.exists(template_path):
                log(f"템플릿 기반 생성: {os.path.basename(template_path)}")
                # ★ target_ctrl로 템플릿 열기 (source ctrl과 완전히 분리)
                target_doc_idx = target_ctrl.open(template_path)
                # ★ [BUG FIX] save_as 호출 — CMD_SAVE_AS 내에서 파일 존재 여부로 성공 검증
                # 실패 시 HwpCommandError가 발생하여 아래 except에서 잡혀 generate_exam 중단됨
                # → CMD_SAVE가 호출되지 않아 템플릿 오염 원천 차단
                target_ctrl.save_as(target_path)
                log(f"결과 파일 생성됨: {os.path.basename(target_path)}")
                # ★ 제목/단원 자동 치환
                def _flog(msg):
                    try:
                        import time as _t
                        with open(r"g:\문제은행\문제은행2\gui_debug.log", "a", encoding="utf-8") as _f:
                            _f.write(f"[{_t.strftime('%H:%M:%S')}][GEN] {msg}\n")
                    except Exception:
                        pass
                _flog(f"exam_title={exam_title!r}, exam_unit={exam_unit!r}")
                # ★ [BUG FIX] 빈값도 무조건 치환 → {{제목}}/{{단원}}이 그대로 남는 현상 방지
                n = target_ctrl.find_replace("{{제목}}", exam_title or '')
                _flog(f"제목 치환 {n}건 → {exam_title!r}")
                log(f"제목 치환: {{{{제목}}}} → {exam_title!r} ({n}건)")
                n = target_ctrl.find_replace("{{단원}}", exam_unit or '')
                _flog(f"단원 치환 {n}건 → {exam_unit!r}")
                log(f"단원 치환: {{{{단원}}}} → {exam_unit!r} ({n}건)")
            else:
                log(f"[!] 템플릿 없음. 빈 문서로 생성: {os.path.basename(target_path)}")
                target_doc_idx = target_ctrl.open(target_path)

            # ★ 문제 순서 보존: 파일별로 미리 열어두고(캐시), 원래 순서대로 처리
            if problem_list:
                print(f"[HWPGenerator] First problem keys: {problem_list[0].keys()}")
                print(f"[HWPGenerator] First problem file info: file_path={problem_list[0].get('file_path')}, file_name={problem_list[0].get('file_name')}")
            else:
                print("[HWPGenerator] problem_list is EMPTY!")

            # 파일 경로 정규화 및 파일별 문제 목록 (자동제외 처리용)
            by_file = {}
            for p in problem_list:
                fname = p.get('file_path') or p.get('file_name') or p.get('source_file')
                if not fname: continue
                if not os.path.isabs(fname):
                    if os.path.exists(fname): fname = os.path.abspath(fname)
                p['_resolved_path'] = fname
                if fname not in by_file: by_file[fname] = []
                by_file[fname].append(p)

            total_count = len(problem_list)
            result['total'] = total_count
            current_idx = 0

            # [Lunchbox] Container for fast answers
            all_answers = []
            global_problem_index = 0

            # Layout tracking (Daechi-dong Real-world Logic)
            COLUMN_HEIGHT_MAX_HWP = 68000 # Approximate HWP units for A4 2단 usable height
            THRESHOLD = 0.65              # 65% Threshold for 1-problem-only decision
            current_y_mm = 0

            # [NEW] Track problems per column
            problems_in_current_col = 0
            last_col_idx = -1
            first_problem_end_mm = 0.0  # 첫 문제 끝 위치 추적

            # [EXPERT TRICK 3] Invisible Buffer for Pre-rendering
            buffer_ctrl = RobustHwpController(visible=False)
            log("가상 렌더링 버퍼 준비 완료.")

            # [EXPERT TRICK 5] Lock Screen for Performance
            self.controller.lock_screen()
            target_ctrl.lock_screen()

            # ★ 온디맨드 소스 열기 - 항상 target(idx 0) + 소스(idx 1) = 2개만 유지
            # 구형: 모든 파일 미리 열기 → 30~40개 동시 → XHwpDocuments.Item() E_INVALIDARG 오류
            # 신형: 소스가 바뀔 때만 닫고 열기 → 최대 2개 → 오류 원천 차단
            # failed_files: try 바깥에서 초기화됨 (여기서 재선언 불필요)

            # 파일 존재 여부 사전 검사 (열지는 않음)
            unique_files = list(dict.fromkeys(
                p.get('_resolved_path') for p in problem_list if p.get('_resolved_path')
            ))
            for source_path in unique_files:
                if not os.path.exists(source_path):
                    log(f"[!] 경고: 소스 파일을 찾을 수 없습니다 (건너뜀): {source_path}")
                    failed_files.add(source_path)

            # 현재 열려있는 소스 파일 추적 (온디맨드)
            _cur_src_path = None
            _cur_src_idx = None

            # ★ 원래 순서대로 문제 처리
            #   request_index = 사용자가 출제 요청한 problem_list의 순서(1-base)
            #   placed_at_slot = 시험지에 실제 배치된 자리(1-base) — 이 자리는 다음 문제가 채움
            for _req_i, p in enumerate(problem_list, start=1):
                    source_path = p.get('_resolved_path', '')
                    if source_path in failed_files:
                        skipped_problems.append({
                            'id': p.get('id', '?'),
                            'file_name': p.get('file_name', '?'),
                            'request_index': _req_i,
                            'placed_at_slot': success_count + 1,
                            'reason': f'파일 없음: {os.path.basename(source_path)}'
                        })
                        continue  # 열기/찾기 실패한 파일 건너뜀

                    # 소스 파일이 바뀌면: 이전 소스 닫고, 새 소스 열기
                    if source_path != _cur_src_path:
                        if _cur_src_idx is not None:
                            try:
                                # ★ 2-인스턴스: switch_doc 불필요 (target_ctrl은 항상 target만 보유)
                                # 소스 교체 전 target 저장 (dirty 해제 → Open 후 저장 프롬프트 방지)
                                try:
                                    target_ctrl.save(target_doc_idx)
                                except Exception as e_presave:
                                    print(f"   [!] 사전 저장 실패 (무시): {e_presave}")
                                self.controller.close_doc(_cur_src_idx)
                            except Exception as e_close:
                                print(f"   [!] 소스 닫기 실패: {e_close}")
                            _cur_src_idx = None
                            _cur_src_path = None
                        log(f"원본 열기: {os.path.basename(source_path)}")
                        try:
                            # Add(True) + 사전저장 조합: 소스 파일을 새 창으로 열기
                            # Add(True)는 호출 전 target이 not-dirty여야 프롬프트 없음 (위에서 save_active로 해제)
                            _cur_src_idx = self.controller.open(source_path, timeout=90)
                            _cur_src_path = source_path
                        except Exception as e_open:
                            print(f"   [!] 파일 열기 실패 ({os.path.basename(source_path)}): {e_open}")
                            log(f"   [!] 파일 열기 실패, 건너뜀: {os.path.basename(source_path)}")
                            failed_files.add(source_path)
                            continue

                    source_doc_idx = _cur_src_idx
                    current_idx += 1
                    try:
                        # 1. Measurement in Invisible Buffer (Expert Logic)
                        self.controller.switch_doc(source_doc_idx)
                        pos_start = p.get('pos_start')
                        pos_end = p.get('pos_end')
                        
                        if not pos_start or not pos_end:
                            print(f"[HWPGenerator] [!] Missing coordinates for problem {current_idx}: {p.get('id')}")
                            print(f"   [Data keys]: {p.keys()}")
                            print(f"   [pos_start]: {pos_start} (Type: {type(pos_start)})")
                            skipped_problems.append({
                                'id': p.get('id', '?'),
                                'file_name': p.get('file_name', '?'),
                                'request_index': _req_i,
                                'placed_at_slot': success_count + 1,
                                'reason': '좌표(pos_start/pos_end) 없음 — 재인덱싱 필요'
                            })
                            continue
                        print(f"[HWPGenerator] Processing problem {current_idx}: {p.get('id')} at {pos_start}~{pos_end}")
                        
                        # Copy from source (trust indexed coordinates)
                        # exclude_tags는 NAESIN_A(내신기출A)에만 적용.
                        # SUNEUNG_SPECIAL 등은 pos_start가 이미 미주줄부터 시작하므로
                        # MoveDown을 하면 문제 첫 줄이 잘리는 버그 발생 → 항상 False 처리.
                        prob_source = p.get('source', '')
                        apply_exclude = exclude_tags and (prob_source == 'NAESIN_A')
                        if apply_exclude:
                            # NAESIN_A 전용: 태그줄(첫 줄) 건너뛰고 다음 줄부터
                            self.controller.set_pos(*pos_start)
                            self.controller.run("MoveDown")
                            self.controller.run("MoveLineBegin")
                            actual_start = self.controller.get_pos()
                            if actual_start:
                                used_moveleft = self.controller.select_range(tuple(actual_start), tuple(pos_end))
                            else:
                                used_moveleft = self.controller.select_range(tuple(pos_start), tuple(pos_end))
                        else:
                            # 기본: 전체 범위 복사 (태그 포함 / 수특 등 태그 없는 소스)
                            used_moveleft = self.controller.select_range(tuple(pos_start), tuple(pos_end))

                        self.controller.copy()

                        buffer_ctrl.clear_all()
                        buffer_ctrl.paste()
                        # 어울림(floating) 이미지가 있어 MoveLeft 방식으로 선택한 경우:
                        # 이전 단락 끝이 여분으로 포함됨 → 첫 빈 단락 삭제 후 버퍼에서 재복사
                        # (target.paste()에 전달할 클립보드를 [어울림이미지+내용]으로 갱신)
                        if used_moveleft:
                            buffer_ctrl.delete_first_empty_para()
                            buffer_ctrl.run("SelectAll")
                            buffer_ctrl.copy()
                        height_mm = buffer_ctrl.get_height_precise()

                        # [SAFETY CHECK] If height is zero, Copy probably failed. Retry.
                        if height_mm < 2.0:
                            log(f"   [!] 감지된 높이({height_mm}mm)가 너무 작음. 복사 재시도...")
                            self.controller.switch_doc(source_doc_idx)
                            # Re-select with slightly wider margin or just retry
                            used_moveleft = self.controller.select_range(tuple(pos_start), tuple(pos_end))
                            # Ensure Copy happened
                            time.sleep(0.2)
                            self.controller.copy()

                            buffer_ctrl.clear_all()
                            buffer_ctrl.paste()
                            if used_moveleft:
                                buffer_ctrl.delete_first_empty_para()
                                buffer_ctrl.run("SelectAll")
                                buffer_ctrl.copy()
                            height_mm = buffer_ctrl.get_height_precise()
                            log(f"   - 재측정 높이: {height_mm}mm")
                            if height_mm < 2.0:
                                log(f"   [!] 재시도 후도 내용 없음 → 이 문제 건너뜀 (파일 좌표 오류 의심)")
                                skipped_problems.append({
                                    'id': p.get('id', '?'),
                                    'file_name': p.get('file_name', '?'),
                                    'request_index': _req_i,
                                    'placed_at_slot': success_count + 1,
                                    'reason': f'복사 내용 없음 (높이 {height_mm:.1f}mm) — 파일 좌표 오류 의심'
                                })
                                continue
                        
                        # [SIMPLE V8] 단 가운데 배치 로직
                        # ★ 2-인스턴스: switch_doc 불필요 — target_ctrl은 항상 target만 보유
                        if current_idx == 1:
                            log("   - [Simple] 1페이지 왼쪽 단(Col 1) 선점.")
                            target_ctrl.run("MoveDocBegin")
                            for _ in range(8): target_ctrl.run("MoveDown")
                        else:
                            target_ctrl.run("MoveDocEnd")
                        
                        COLUMN_HEIGHT_MM = 250.0
                        LINE_SPACING = 12  # 문제 사이 간격 (엔터 횟수) ← 이 값을 조정하세요
                        
                        # ★ 2-인스턴스 배치: target_ctrl.paste() — SetActive 없이 항상 target에 붙여넣기
                        if problems_in_current_col == 0:
                            log(f"   - [Fixed] 1번째 문제: 단 맨 위 배치")
                            target_ctrl.run("BreakPara")   # 문제 위 빈 줄 1칸
                            self._paste_verified(target_ctrl)
                            self._remove_trailing_blank_lines(target_ctrl)
                            target_ctrl.set_para_margin(0, 5)

                            page2, col2, y2_hwp = target_ctrl.get_layout_state()
                            problems_in_current_col = 1
                            last_col_idx = col2

                        elif problems_in_current_col == 1:
                            for _ in range(LINE_SPACING):
                                target_ctrl.run("BreakPara")

                            page_before, col_before, y_before = target_ctrl.get_layout_state()
                            y_before_mm = y_before / 283.465
                            estimated_total = y_before_mm + height_mm

                            target_ctrl.run("BreakPara")   # 문제 위 빈 줄 1칸
                            self._paste_verified(target_ctrl)
                            self._remove_trailing_blank_lines(target_ctrl)
                            target_ctrl.set_para_margin(0, 5)

                            page_after, col_after, y_after = target_ctrl.get_layout_state()

                            if col_after != col_before:
                                log(f"   - [Fixed] 충돌 감지 (단 넘어감). 되돌리고 다음 단 배치.")
                                target_ctrl.undo()
                                target_ctrl.run("BreakColumn")
                                target_ctrl.run("MoveDocEnd")
                                target_ctrl.run("BreakPara")   # 문제 위 빈 줄 1칸
                                self._paste_verified(target_ctrl)
                                self._remove_trailing_blank_lines(target_ctrl)
                                target_ctrl.set_para_margin(0, 5)

                                page2, col2, y2_hwp = target_ctrl.get_layout_state()
                                problems_in_current_col = 1
                                last_col_idx = col2
                            else:
                                log(f"   - [Fixed] 2번째 문제: 10줄 간격으로 배치")
                                problems_in_current_col = 2
                                last_col_idx = col_after

                        else:  # problems_in_current_col >= 2
                            log(f"   - [Fixed] 이미 2문제. 다음 단으로.")
                            target_ctrl.run("BreakColumn")
                            target_ctrl.run("MoveDocEnd")
                            target_ctrl.run("BreakPara")   # 문제 위 빈 줄 1칸
                            self._paste_verified(target_ctrl)
                            self._remove_trailing_blank_lines(target_ctrl)
                            target_ctrl.set_para_margin(0, 5)

                            page2, col2, y2_hwp = target_ctrl.get_layout_state()
                            problems_in_current_col = 1
                            last_col_idx = col2

                        # 최종 위치 확인
                        page2, col2, y2_hwp = target_ctrl.get_layout_state()
                        log(f"   - {current_idx}/{total_count}번 배치: {page2}P, {col2+1}단")
                        success_count += 1
                        
                    except Exception as e:
                        log(f"   [!] {current_idx}번 작업 중 오류: {e}")
                        skipped_problems.append({
                            'id': p.get('id', '?'),
                            'file_name': p.get('file_name', '?'),
                            'request_index': _req_i,
                            'placed_at_slot': success_count + 1,
                            'reason': f'처리 오류: {str(e)[:80]}'
                        })

            # 2. End of Problem Loop

            # 마지막 소스 파일 닫기 (온디맨드 방식: 루프 끝에 1개만 남음)
            if _cur_src_idx is not None:
                try:
                    # ★ 2-인스턴스: switch_doc 불필요 — source_ctrl은 source만 보유
                    self.controller.close_doc(_cur_src_idx)
                except Exception as e_close:
                    print(f"   [!] 마지막 소스 닫기 실패: {e_close}")
                _cur_src_idx = None

            # [Cleanup buffer]
            buffer_ctrl.quit()
            buffer_ctrl = None  # finally에서 중복 quit() 방지
            self.controller.unlock_screen()
            target_ctrl.unlock_screen()
            log("가상 버퍼 정리 및 화면 잠금 해제 완료.")

            # ★ 정답 미주 홀수 페이지 시작: BreakSection + PageStartPosition=3
            # → 한글이 자동으로 짝수 페이지이면 빈 페이지 삽입하여 홀수 보장
            try:
                target_ctrl.run("MoveDocEnd")
                _odd_ok = target_ctrl.break_odd_section()
                if _odd_ok:
                    log("홀수 쪽 구역 나누기 완료 (정답 미주는 항상 홀수 페이지에서 시작)")
                else:
                    log("[fallback] 일반 쪽 나누기로 대체 (SectionDef 실패)")
            except Exception as e_bp:
                log(f"[!] 홀수 구역 나누기 실패: {e_bp}")

            # ★ [Fast Answer Key] target 문서 XML에서 미주(정답) 추출 후 삽입
            # all_answers를 루프 중 미리 수집하는 방식 대신,
            # 모든 문제 붙여넣기 완료 후 target_ctrl XML을 1회 파싱 → 안정적
            if fast_answer_key:
                log("정답 추출 중 (target 문서 XML 파싱)...")
                try:
                    xml_content = target_ctrl.extract_xml()
                    raw_answers = self._extract_answers_from_xml(xml_content)
                    if raw_answers:
                        all_answers = [{"no": str(i + 1), "ans": a} for i, a in enumerate(raw_answers)]
                        log(f"빠른 정답 삽입 중... (총 {len(all_answers)}개 문항)")
                        self._insert_answer_list(all_answers)
                        log(f"빠른 정답 삽입 완료 ({len(all_answers)}개 문항)")
                    else:
                        log("[!] 미주에서 정답을 찾을 수 없어 정답 페이지를 건너뜁니다.")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    log(f"[X] 빠른 정답 삽입 실패: {e}")

            # Final Save (target_ctrl로 직접 저장 — switch_doc 불필요)
            target_ctrl.save(target_doc_idx)
            log(f"[SUCCESS] 모든 문항 배치 완료! (목표 {total_count}문제 / 실제 출제 {success_count}문제)")
            if success_count < total_count:
                missed = total_count - success_count
                log(f"[⚠ 불일치] {missed}문제 누락됨 — 정답지 작업 전 문제 번호 확인 필요!")

        except Exception as e:
            log(f"[X] 전체 프로세스 오류: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # ★ result 완성 (예외 발생 여부와 무관하게 항상 실행)
            result['success'] = success_count
            result['skipped_problems'] = skipped_problems
            result['skipped_files'] = list(failed_files)

            # buffer_ctrl: try 내 예외로 quit()이 호출되지 않은 경우 여기서 보장
            if buffer_ctrl is not None:
                try:
                    buffer_ctrl.quit()
                except Exception:
                    pass
            if should_close and self.controller:
                log("엔진 종료 중...")
                self.controller.quit()
            # target_ctrl은 항상 generate_exam 내에서 생성 → 항상 종료
            try:
                target_ctrl.quit()
            except Exception:
                pass

        return result

    def _extract_answers_from_endnotes(self) -> List[Dict]:
        """
        Refactored: Uses XML extraction for 100% stability.
        Fetches the entire document XML and parses endnotes.
        """
        answers = []
        try:
            print("[XML_Mode] Extracting answers via HWPML2X...")
            
            # 1. Get Full XML
            xml_content = self.controller.extract_xml()
            
            # 2. Extract Endnote Text
            raw_answers = self._extract_answers_from_xml(xml_content)
            
            if not raw_answers:
                print("[XML_Mode] No endnotes found in XML.")
                return []

            # 3. Format
            print(f"[XML_Mode] Found {len(raw_answers)} answers.")
            for i, ans in enumerate(raw_answers):
                answers.append({
                    "no": str(i + 1),
                    "ans": ans
                })
                
        except Exception as e:
            print(f"Error extracting answers (XML Mode): {e}")
            import traceback
            traceback.print_exc()
            
        return answers


    def _insert_answer_list(self, answers: List[Dict], items_per_row: int = 3):
        """
        빠른 정답을 일렬 텍스트로 삽입합니다 (표 없음 - 안정성 최우선).
        items_per_row개씩 한 줄에 나열합니다.
        예: 1번: ③     2번: ①     3번: 12
            4번: ④     5번: ②     6번: ①
        """
        try:
            ctrl = getattr(self, 'target_ctrl', None) or self.controller
            # 1. 문서 끝으로 이동 후 홀수 쪽 구역 나누기
            ctrl.run("MoveDocEnd")
            _odd_ok2 = ctrl.break_odd_section()
            if _odd_ok2:
                print("[빠답] 홀수 쪽 구역 나누기 완료 (SectionDef PageStartPosition=3)")
            else:
                print("[빠답] fallback BreakPage 사용 (SectionDef 실패)")

            # 2. 제목 삽입 (가운데 정렬)
            ctrl.run("ParagraphShapeCentered")
            ctrl.run_command("INSERT_TEXT", "◆ 빠른 정답 ◆")
            ctrl.run("BreakPara")
            ctrl.run("BreakPara")
            ctrl.run("ParagraphShapeLeft")

            # 3. 정답 일렬 삽입 (탭 대신 공백으로 구분 - 탭은 HWP 서식 종속으로 불안정)
            total = len(answers)
            row_items = []

            for i, item in enumerate(answers):
                no  = item.get('no', str(i + 1))
                ans = item.get('ans', '?')
                row_items.append(f"{no}번: {ans}")

                is_last = (i == total - 1)
                is_row_end = (len(row_items) == items_per_row)

                if is_last or is_row_end:
                    line = "     ".join(row_items)
                    ctrl.run_command("INSERT_TEXT", line)
                    ctrl.run("BreakPara")
                    row_items = []

            ctrl.run("MoveDocEnd")
            print(f"[빠답] 총 {total}개 정답 삽입 완료 ({items_per_row}개/줄)")

        except Exception as e:
            print(f"[빠답] _insert_answer_list 오류: {e}")
            import traceback
            traceback.print_exc()
