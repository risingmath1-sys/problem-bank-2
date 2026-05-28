"""
Robust HWP Automation Core - Expert Validated Solution
Based on professional consultation with 3 HWP automation experts

Key Improvements:
1. InitScan/GetText for endnote detection (replaces unreliable HeadCtrl)
2. doc.FullName for reliable saving (fixes forceopen:true path issue)
3. hwp.Clear(3) + Quit for complete cleanup (prevents state pollution)
"""
import ctypes
import multiprocessing
import queue
import time
import os
import sys
import subprocess
import threading
import shutil
import pythoncom
import win32com.client
import win32gui
import win32clipboard
import win32api
import win32con
import win32process

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hwp_registry_manager import HwpRegistryManager

# Constants
CMD_OPEN = "OPEN"
CMD_QUIT = "QUIT"
CMD_SAVE = "SAVE"
CMD_SAVE_AS = "SAVE_AS"
CMD_SAVE_ACTIVE = "SAVE_ACTIVE"  # 현재 활성 문서를 SetActive 없이 즉시 저장
CMD_EXTRACT_XML = "EXTRACT_XML" # New XML Command
CMD_GET_TEXT = "GET_TEXT"
CMD_GET_TEXT_FILE = "GET_TEXT_FILE"
CMD_INSERT_TEXT = "INSERT_TEXT"
CMD_ALIVE = "ALIVE"
CMD_GET_POS = "GET_POS"
CMD_SET_POS = "SET_POS"
CMD_GET_SELECTED_HEIGHT = "GET_SELECTED_HEIGHT"
CMD_MOVE_POS = "MOVE_POS"
CMD_SELECT_RANGE = "SELECT_RANGE"
CMD_COPY = "COPY"
CMD_PASTE = "PASTE"
CMD_DOC_COUNT = "DOC_COUNT"
CMD_SWITCH_DOC = "SWITCH_DOC"
CMD_FIND_ENDNOTES = "FIND_ENDNOTES"
CMD_FIND_STRING = "FIND_STRING"
CMD_FIND_REPLACE = "FIND_REPLACE"
CMD_FORMAT_ENDNOTES = "FORMAT_ENDNOTES"
CMD_REMOVE_PARAGRAPH_NUMBERS = "REMOVE_PARAGRAPH_NUMBERS"
CMD_CLOSE_DOC = "CLOSE_DOC"
CMD_UNDO = "UNDO"
CMD_GET_LAYOUT_STATE = "GET_LAYOUT_STATE"
CMD_BREAK_ODD_SECTION = "BREAK_ODD_SECTION"  # 구역 나누기 (홀수 쪽 시작)
CMD_CLEAR = "CLEAR"
CMD_RUN_COMMAND = "RUN_COMMAND"
CMD_RUN = "RUN" # Explicit RUN command requested by user
CMD_LOCK_SCREEN = "LOCK_SCREEN"
CMD_UNLOCK_SCREEN = "UNLOCK_SCREEN"
CMD_SCAN_TEXT = "SCAN_TEXT"
CMD_GET_XML = "GET_XML"  # Export current document as HWPML2X XML string
CMD_GET_PARA_TEXT = "GET_PARA_TEXT"
CMD_GET_PARA_CHAR_COUNT = "GET_PARA_CHAR_COUNT"  # Count chars (including OLE/eq) in a para
CMD_FIND_BOUNDARY_CONTROL = "FIND_BOUNDARY_CONTROL"
CMD_GET_HEIGHT_PRECISE = "GET_HEIGHT_PRECISE"
CMD_GET_PARA_COUNT = "GET_PARA_COUNT"
CMD_GET_PARA_END = "GET_PARA_END"
CMD_SET_PARA_MARGIN = "SET_PARA_MARGIN"
CMD_SET_CHAR_SPACING = "SET_CHAR_SPACING"
CMD_DELETE_FIRST_EMPTY_PARA = "DELETE_FIRST_EMPTY_PARA"  # MoveLeft 선택 후 여분 빈 단락 삭제
CMD_FIND_BARRIER_POS = "FIND_BARRIER_POS"
CMD_MOVE_COLUMN_END = "MOVE_COLUMN_END"
CMD_GET_COLUMN_INFO = "GET_COLUMN_INFO"
CMD_MOVE_PAGE_END = "MOVE_PAGE_END"
CMD_SET_VISIBLE = "SET_VISIBLE"
CMD_SWITCH_AND_PASTE = "SWITCH_AND_PASTE"  # switch_doc + paste 원자적 실행 (IPC 왕복 제거)

class HwpCommandError(Exception):
    """Raised when a specific HWP command fails logically (non-fatal)."""
    pass

def _clean_gen_py_cache():
    """
    Cleans up the gen_py cache to prevent COM conflicts.
    """
    try:
        temp_dir = os.environ.get('TEMP')
        if not temp_dir: return
        
        gen_py_dir = os.path.join(temp_dir, 'gen_py')
        if os.path.exists(gen_py_dir):
            shutil.rmtree(gen_py_dir, ignore_errors=True)
    except Exception as e:
        print(f"[System] Warning: Failed to clean gen_py: {e}")

def get_hwp_pids():
    """Helper to get current Hwp.exe process IDs - Window Hidden"""
    try:
        # Use CREATE_NO_WINDOW to prevent black flickering
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        cmd = ['powershell', '-Command', 'Get-Process Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id']
        output = subprocess.check_output(cmd, startupinfo=startupinfo, creationflags=win32con.CREATE_NO_WINDOW).decode().strip()
        if not output: return set()
        return set(int(pid) for pid in output.splitlines())
    except:
        return set()

def _popup_watchdog(stop_event, log_queue, hwp_pid_holder=None, stealth=False):
    """Background thread to auto-click HWP security popups.

    Strategy (3-tier):
    1. PID filter: enumerate only windows belonging to the HWP process
    2. Class-agnostic: check ALL windows from HWP (not just #32770),
       because HWP may use custom dialog classes
    3. Button text variants: '허용', '허용(A)', '예', '예(Y)', '확인'

    Also handles the case where HWP or its dialogs are currently hidden.
    """
    BM_CLICK = 0x00F5  # Standard Windows button-click message
    # 클릭 허용 버튼 텍스트 (우선순위 순서: 모두 허용 > 허용 > 예 > 확인)
    ALLOW_PRIORITY = ('모두 허용', '허용', '예(Y)', '예', '허락', '확인(O)', '확인')
    # 절대 클릭하면 안 되는 텍스트 (거부/취소 버튼)
    DENY_TEXTS = ('안 함', '취소', '아니오', 'Cancel', 'No')
    # HWP main frame class names to SKIP
    SKIP_CLASSES = ('HwpParentFrame', 'HwpEditMain', 'MDIClient',
                    'HwpMain',        'HwpView',     'RICHEDIT')

    def _find_allow_button(child_hwnd, results):
        """EnumChildWindows callback: 허용 버튼 수집 (거부 버튼 제외, 우선순위 정렬)."""
        try:
            cls  = win32gui.GetClassName(child_hwnd)
            text = win32gui.GetWindowText(child_hwnd)
            if cls.upper() == 'BUTTON':
                # 거부 텍스트 포함 시 제외
                if any(d in text for d in DENY_TEXTS):
                    return True
                # 허용 텍스트 포함 시 우선순위 점수와 함께 수집
                for priority, t in enumerate(ALLOW_PRIORITY):
                    if t in text:
                        results.append((priority, child_hwnd, text))
                        break
        except Exception:
            pass
        return True

    def _scan_hwp_windows(hwnd, out):
        """EnumWindows callback: HWP 보안 팝업 수집."""
        try:
            if hwp_pid_holder and hwp_pid_holder[0]:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid != hwp_pid_holder[0]:
                        return True
                except Exception:
                    return True

            cls = win32gui.GetClassName(hwnd)
            if any(skip in cls for skip in SKIP_CLASSES):
                return True

            buttons = []
            try:
                win32gui.EnumChildWindows(hwnd, _find_allow_button, buttons)
            except Exception:
                pass

            if buttons:
                # 우선순위 낮은 번호(=높은 우선순위) 버튼 선택 (모두 허용 우선)
                buttons.sort(key=lambda x: x[0])
                best = buttons[0]
                title = win32gui.GetWindowText(hwnd)
                out.append((hwnd, best[1], title, best[2]))
        except Exception:
            pass
        return True

    while not stop_event.is_set():
        try:
            found = []
            win32gui.EnumWindows(_scan_hwp_windows, found)

            for dlg_hwnd, btn_hwnd, title, btn_text in found:
                log_queue.put(("LOG",
                    f"[Watchdog] 보안 팝업 발견 cls={win32gui.GetClassName(dlg_hwnd)!r} "
                    f"title={title!r} btn={btn_text!r}"))

                # 팝업 창 보이게 하기
                if not win32gui.IsWindowVisible(dlg_hwnd):
                    win32gui.ShowWindow(dlg_hwnd, win32con.SW_SHOW)
                    time.sleep(0.15)

                if stealth:
                    # 스텔스 모드: 현재 포커스 앱 저장 → 팝업에 잠깐 포커스 → SendMessage → 원래 앱 복원
                    prev_hwnd = None
                    try:
                        prev_hwnd = win32gui.GetForegroundWindow()
                    except Exception:
                        pass
                    try:
                        win32gui.SetForegroundWindow(dlg_hwnd)
                        time.sleep(0.08)
                    except Exception:
                        pass
                else:
                    # 일반 모드: 팝업 포커스
                    try:
                        win32gui.SetForegroundWindow(dlg_hwnd)
                        time.sleep(0.1)
                    except Exception:
                        pass

                # SendMessage(BM_CLICK)
                clicked = False
                try:
                    win32gui.SendMessage(btn_hwnd, BM_CLICK, 0, 0)
                    log_queue.put(("LOG", f"[Watchdog] '{btn_text}' SendMessage(BM_CLICK) 완료"))
                    clicked = True
                except Exception as e:
                    log_queue.put(("LOG", f"[Watchdog] BM_CLICK 실패({e})"))

                if stealth and prev_hwnd:
                    # 스텔스: 클릭 직후 원래 포커스 앱으로 복원
                    try:
                        time.sleep(0.05)
                        win32gui.SetForegroundWindow(prev_hwnd)
                    except Exception:
                        pass

                if not clicked and not stealth:
                    # Fallback 키보드 (스텔스에서는 생략)
                    log_queue.put(("LOG", "[Watchdog] 키보드(Alt+A/Enter) 대체 시도"))
                    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                    win32api.keybd_event(ord('A'), 0, 0, 0)
                    time.sleep(0.05)
                    win32api.keybd_event(ord('A'), 0, win32con.KEYEVENTF_KEYUP, 0)
                    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                    time.sleep(0.4)
                    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

                time.sleep(1.0)   # wait for dialog to close before next scan
        except Exception:
            pass
        time.sleep(0.2)   # 0.5s → 0.2s: 팝업 감지 더 빠르게

def _hwp_worker_loop(cmd_queue, result_queue, visible=True):
    pythoncom.CoInitialize()
    hwp = None
    hwp_pid = None
    # Mutable holder so watchdog thread can access PID after HWP starts
    hwp_pid_holder = [None]
    stop_watchdog = threading.Event()
    watchdog = threading.Thread(
        target=_popup_watchdog,
        args=(stop_watchdog, result_queue, hwp_pid_holder, not visible),  # stealth = not visible
        daemon=True
    )
    watchdog.start()

    try:
        # Track PIDs
        pids_before = get_hwp_pids()

        # Create HWP Object
        try:
            # Use DispatchEx to ensure a fresh process and better security module behavior
            hwp = win32com.client.DispatchEx("HWPFrame.HwpObject")
            pids_after = get_hwp_pids()
            new_pids = pids_after - pids_before
            if new_pids:
                hwp_pid = new_pids.pop()
                hwp_pid_holder[0] = hwp_pid   # share with watchdog thread
                result_queue.put(("LOG", f"[Worker] Hwp.exe PID: {hwp_pid}"))
            else:
                hwp_pid = "Unknown"
        except Exception as e:
            result_queue.put(("INIT_ERROR", str(e)))
            return

        # Security Module
        try:
            reg_name = HwpRegistryManager.get_registered_value_name()
            result = hwp.RegisterModule("FilePathCheckDLL", reg_name)
            if not result:
                result_queue.put(("LOG", f"[Warning] RegisterModule('{reg_name}') failed."))
            else:
                result_queue.put(("LOG", f"[Worker] RegisterModule('{reg_name}') SUCCESS."))
        except Exception as e:
            result_queue.put(("LOG", f"[Error] RegisterModule Exception: {e}"))

        # Visibility: 초기화 시점에는 창을 숨기지 않는다.
        # 이유: Open() 호출 전에 숨기면 "허용하시겠습니까?" 다이얼로그도 숨겨져
        #       watchdog이 클릭 불가 → 무한 대기 → 타임아웃.
        # 대신 CMD_OPEN 완료 후에 숨긴다 (아래 CMD_OPEN 핸들러 참조).
        # (visible=True 모드에서는 이전과 동일하게 동작)

        result_queue.put(("INIT_SUCCESS", hwp_pid))

        # Command Loop
        while True:
            cmd_data = cmd_queue.get()
            cmd_type = cmd_data[0]
            
            if cmd_type == CMD_QUIT: break
            
            try:
                if cmd_type == CMD_ALIVE:
                    result_queue.put(("ALIVE_ACK", True))
                
                elif cmd_type == CMD_OPEN:
                    filepath = cmd_data[1]
                    readonly = cmd_data[2] if len(cmd_data) > 2 else False
                    # Add(True): 새 창으로 소스 파일 열기
                    # ★ 주의: 호출 전 반드시 시험지(target)를 저장해 dirty 해제해야 프롬프트 없음
                    # (generator에서 open() 직전 CMD_SAVE_ACTIVE로 저장 후 호출)
                    hwp.XHwpDocuments.Add(True)

                    # ── 보안 팝업 대응 ──────────────────────────────────────
                    # RegisterModule 실패 시 Open()마다 "허용하시겠습니까?" 팝업.
                    # Watchdog이 팝업 클릭 → hwp.Open() 반환 → 정상 완료.

                    if not visible:
                        # 스텔스: Open() 전에 포커스 잠금 → 창이 잠깐 보여도 포커스 탈취 불가
                        try:
                            ctypes.windll.user32.LockSetForegroundWindow(1)  # LSFW_LOCK
                        except Exception:
                            pass

                    # 스텔스 모드: 메인 창은 숨긴 채로 Open()
                    # 보안 팝업은 별도 Win32 창으로 뜨므로 watchdog이 팝업만 독립적으로 표시·클릭
                    # 일반 모드: 메인 창 표시 후 Open()
                    if visible:
                        try:
                            hwp.XHwpWindows.Item(0).Visible = True
                        except Exception:
                            pass

                    # readonly:true 는 이 HWP 버전에서 미지원 → COM RPC 크래시 유발
                    # Add(False)로 이미 저장 다이얼로그 방지됨; 소스파일은 SelectRange/Copy만 사용하므로 dirty 없음
                    hwp.Open(filepath, "HWP", "forceopen:true")

                    # Open() 완료 후 스텔스면 즉시 숨김
                    try:
                        hwp.XHwpWindows.Item(0).Visible = visible
                    except Exception:
                        pass

                    if not visible:
                        # Win32 API로도 확실히 숨김
                        try:
                            hwnd = hwp.XHwpWindows.Active_XHwpWindow.WindowHandle
                            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                        except Exception:
                            pass
                        # 포커스 잠금 해제
                        try:
                            ctypes.windll.user32.LockSetForegroundWindow(2)  # LSFW_UNLOCK
                        except Exception:
                            pass
                    else:
                        try:
                            hwnd = hwp.XHwpWindows.Active_XHwpWindow.WindowHandle
                            win32gui.SetForegroundWindow(hwnd)
                        except Exception:
                            pass

                    result_queue.put(("SUCCESS", hwp.XHwpDocuments.Count - 1))

                elif cmd_type == CMD_SAVE:
                    doc_idx = cmd_data[1]
                    count = hwp.XHwpDocuments.Count
                    # Safety: clamp doc_idx to valid range
                    safe_idx = min(max(0, doc_idx), count - 1) if count > 0 else 0
                    doc = hwp.XHwpDocuments.Item(safe_idx)

                    # 핵심: 문서 객체에서 직접 경로를 얻은 뒤 SetActive + SaveAs
                    # (FileSave_S는 HWP의 "현재 활성 문서"에 의존해 타이밍 문제 발생)
                    file_path = doc.FullName   # 이 문서의 실제 저장 경로

                    # ★ [BUG FIX] 템플릿 경로에 저장하는 것을 원천 차단
                    # save_as() 실패 시 doc.FullName = template_path 그대로 → 템플릿 오염 방지
                    _basename = os.path.basename(file_path)
                    if "출제용-원본" in _basename:
                        result_queue.put(("ERROR",
                            f"[SAFETY] CMD_SAVE 차단: 템플릿 경로({_basename})에 저장 시도. "
                            f"save_as() 실패 후 FullName이 템플릿으로 남아있음. "
                            f"generate_exam을 중단하여 템플릿 오염을 방지합니다."))
                    else:
                        doc.SetActive_XHwpDocument()
                        time.sleep(0.5)              # 활성화 대기 (0.2s → 0.5s)
                        # ★ [BUG FIX] 덮어쓰기 팝업 방지: 기존 파일 삭제 후 SaveAs
                        # hwp.SaveAs()는 파일이 존재하면 "덮어쓰시겠습니까?" 팝업을 띄워
                        # COM call이 블로킹 → TimeoutError 발생. 미리 삭제로 팝업 원천 제거.
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                        hwp.SaveAs(file_path, "HWP", "")   # 명시적 경로에 저장
                        result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_SAVE_AS:
                    _sa_path = cmd_data[1]
                    _sa_fmt  = cmd_data[2]
                    # ★ [BUG FIX] 저장 대상 폴더가 없으면 미리 생성 (폴더 없음 → 디스크 에러 원인)
                    _sa_dir = os.path.dirname(_sa_path)
                    if _sa_dir and not os.path.exists(_sa_dir):
                        os.makedirs(_sa_dir, exist_ok=True)
                    # ★ [BUG FIX] 덮어쓰기 팝업 방지: 기존 파일 삭제 후 SaveAs
                    # 파일이 존재하면 "덮어쓰시겠습니까?" 팝업 → 팝업 처리 실패 시 save_as 실패
                    # → target_doc_idx가 template을 가리킨 채 문제들이 template에 붙여넣어짐 → template 오염
                    if os.path.exists(_sa_path):
                        try:
                            os.remove(_sa_path)
                        except Exception:
                            pass
                    hwp.SaveAs(_sa_path, _sa_fmt, "")
                    # ★ [BUG FIX] 저장 성공 여부 확인: 파일이 실제로 생성됐는지
                    # hwp.SaveAs()가 "디스크" 에러 다이얼로그를 띄우고 예외 없이 반환하는 경우 방어
                    # (watchdog이 다이얼로그를 자동 닫으면 코드는 성공으로 착각 → 이를 파일 존재로 검증)
                    time.sleep(0.3)
                    if os.path.exists(_sa_path):
                        result_queue.put(("SUCCESS", True))
                    else:
                        result_queue.put(("ERROR",
                            f"SaveAs 실패: 파일이 생성되지 않음 ({os.path.basename(_sa_path)}). "
                            f"'디스크가 올바른지 확인하십시오' 에러가 발생했을 수 있습니다."))

                elif cmd_type == CMD_SAVE_ACTIVE:
                    # 현재 활성 문서를 SetActive 없이 즉시 저장 (switch_doc 직후 호출용)
                    # ★ 현재는 사용 안 함 (save(target_doc_idx)로 대체) - 안전 로그만 유지
                    file_path = cmd_data[1]
                    try:
                        active_name = hwp.XHwpDocuments.Active_XHwpDocument.FullName
                        print(f"[Worker] SAVE_ACTIVE → active doc: {os.path.basename(active_name)} → to: {os.path.basename(file_path)}", flush=True)
                    except Exception:
                        pass
                    hwp.SaveAs(file_path, "HWP", "")
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_GET_POS:
                    pos_info = hwp.GetPos()
                    result_queue.put(("SUCCESS", pos_info))

                elif cmd_type == CMD_SELECT_RANGE:
                    start = cmd_data[1]
                    end = cmd_data[2]
                    try:
                        # Ensure no previous selection interference
                        hwp.Run("Cancel")
                        hwp.SetPos(*start)
                        actual = list(hwp.GetPos())
                        used_moveleft = False
                        # 어울림(floating) 앵커 감지: SetPos 후 커서가 같은 단락에서 앞으로 밀리면
                        # 앵커 ctrl char가 start 위치에 있는 것 → MoveLeft로 이전 단락 끝으로 이동
                        if actual[1] == start[1] and actual[2] > start[2]:
                            hwp.Run("MoveLeft")
                            used_moveleft = True
                        else:
                            hwp.Run("MoveParaBegin")  # 글자처럼 이미지 / 일반 텍스트 포함용
                        hwp.Run("Select")
                        hwp.SetPos(*end)
                        result_queue.put(("SUCCESS", used_moveleft))
                    except Exception as e:
                         result_queue.put(("ERROR", f"Select failed: {e}"))

                elif cmd_type == CMD_DELETE_FIRST_EMPTY_PARA:
                    # MoveLeft 선택으로 이전 단락 끝이 여분으로 포함된 경우,
                    # 버퍼 붙여넣기 후 맨 첫 단락이 빈 단락으로 남음.
                    # MoveDocBegin == MoveParaEnd이면 빈 단락 → Delete 1회로 제거.
                    # ★ MoveDown+Select 방식은 어울림 앵커 ctrl char까지 선택하여 앵커 삭제 버그 있음
                    #    → MoveDocBegin에서 Delete 1회만: 단락 구분자만 제거, 앵커 보존
                    try:
                        hwp.Run("MoveDocBegin")
                        before_pos = list(hwp.GetPos())
                        hwp.Run("MoveParaEnd")
                        after_pos = list(hwp.GetPos())
                        if before_pos == after_pos:  # 첫 단락이 빈 단락
                            hwp.Run("MoveDocBegin")
                            hwp.Run("Delete")
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"DeleteFirstEmptyPara failed: {e}"))

                elif cmd_type == CMD_GET_TEXT:
                    """
                    GetTextFile을 사용하여 문서 전체 텍스트 추출 (표/글상자 포함)
                    클립보드 방식보다 훨씬 강력하고 안정적임.
                    """
                    try:
                        # "TEXT" 포맷으로 추출, 옵션 "" (기본)
                        # 이 방식은 문서 내의 모든 텍스트를 문자열로 반환함
                        full_text = hwp.GetTextFile("TEXT", "")
                        result_queue.put(("SUCCESS", full_text))
                    except Exception as e:
                        result_queue.put(("ERROR", f"GetTextFile failed: {str(e)}"))

                elif cmd_type == CMD_GET_TEXT_FILE:
                    """
                    Generic GetTextFile wrapper.
                    args: (format, option)
                    e.g. ("HWPML2X", "saveblock")
                    """
                    try:
                        fmt = cmd_data[1]
                        opt = cmd_data[2]
                        res = hwp.GetTextFile(fmt, opt)
                        result_queue.put(("SUCCESS", res))
                    except Exception as e:
                        result_queue.put(("ERROR", f"GetTextFile({fmt}, {opt}) failed: {e}"))

                elif cmd_type == CMD_FIND_ENDNOTES:
                    positions = []
                    time.sleep(0.5)
                    try:
                        ctrl = hwp.HeadCtrl
                        while ctrl:
                            try:
                                if hasattr(ctrl, 'CtrlID') and ctrl.CtrlID == "en":
                                    pos_obj = ctrl.GetAnchorPos(0)
                                    hwp.SetPosBySet(pos_obj)
                                    pos_tuple = hwp.GetPos()
                                    positions.append(pos_tuple)
                            except: pass
                            ctrl = ctrl.Next
                    except Exception as e:
                        result_queue.put(("LOG", f"[Worker] Error: {e}"))
                    result_queue.put(("SUCCESS", positions))

                elif cmd_type == CMD_SWITCH_DOC:
                    idx = cmd_data[1]
                    doc = hwp.XHwpDocuments.Item(idx)
                    try:
                        target_name = doc.FullName
                    except Exception:
                        target_name = None
                    # SetActive는 비동기 UI API → 최대 1.5s 재시도로 전환 완료 확인
                    switched = False
                    for attempt in range(15):
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(1)
                            except: pass
                        doc.SetActive_XHwpDocument()
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(2)
                            except: pass
                        time.sleep(0.1)
                        if target_name is not None:
                            try:
                                cur_name = hwp.XHwpDocuments.Active_XHwpDocument.FullName
                                if cur_name == target_name:
                                    switched = True
                                    print(f"[Worker] SWITCH_DOC OK (attempt {attempt+1}): {os.path.basename(target_name)}", flush=True)
                                    break
                            except Exception:
                                pass
                        else:
                            switched = True
                            break
                    if not switched:
                        print(f"[Worker] SWITCH_DOC WARN: 전환 미확인 after 15 attempts → {target_name}", flush=True)
                    result_queue.put(("SUCCESS", switched))

                elif cmd_type == CMD_MOVE_POS:
                    move_id = cmd_data[1]
                    para = cmd_data[2] if len(cmd_data) > 2 else 0
                    pos = cmd_data[3] if len(cmd_data) > 3 else 0
                    hwp.MovePos(move_id, para, pos)
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_COPY:
                    try:
                        # 스텔스: 복사 전 포커스 탈취 방지 잠금
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(1)
                            except: pass

                        # Clear Clipboard first to prevent "stale" copy
                        try:
                            win32clipboard.OpenClipboard()
                            win32clipboard.EmptyClipboard()
                            win32clipboard.CloseClipboard()
                        except: pass

                        hwp.Run("Copy")

                        # 복사 완료 후 잠금 해제
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(2)
                            except: pass

                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(2)
                            except: pass
                        result_queue.put(("ERROR", f"Copy failed: {e}"))

                elif cmd_type == CMD_PASTE:
                    try:
                        # 스텔스: 붙여넣기 전 포커스 탈취 방지 잠금
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(1)
                            except: pass

                        # ★ 진단 로그: 실제로 어떤 문서에 붙여넣는지 확인
                        try:
                            active_name = hwp.XHwpDocuments.Active_XHwpDocument.FullName
                            print(f"[Worker] PASTE → active doc: {os.path.basename(active_name)}", flush=True)
                        except Exception:
                            pass

                        time.sleep(0.1)
                        hwp.Run("Paste")

                        # 붙여넣기 완료 후 잠금 해제
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(2)
                            except: pass

                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        if not visible:
                            try: ctypes.windll.user32.LockSetForegroundWindow(2)
                            except: pass
                        result_queue.put(("ERROR", f"Paste failed: {e}"))

                elif cmd_type == CMD_SWITCH_AND_PASTE:
                    # ★ 핵심: switch + paste를 Worker 안에서 원자적으로 실행
                    # IPC 왕복(switch SUCCESS 반환 → main → paste 요청) 사이에
                    # HWP 메시지 큐가 소스 WM_ACTIVATE를 처리해서 포커스 역전되는 문제 해결
                    target_idx = cmd_data[1]
                    try:
                        doc = hwp.XHwpDocuments.Item(target_idx)
                        try:
                            target_name = doc.FullName
                        except Exception:
                            target_name = None

                        # SetActive + 검증 (최대 15회)
                        for attempt in range(15):
                            if not visible:
                                try: ctypes.windll.user32.LockSetForegroundWindow(1)
                                except: pass
                            doc.SetActive_XHwpDocument()
                            if not visible:
                                try: ctypes.windll.user32.LockSetForegroundWindow(2)
                                except: pass
                            time.sleep(0.1)
                            if target_name is not None:
                                try:
                                    cur = hwp.XHwpDocuments.Active_XHwpDocument.FullName
                                    if cur == target_name:
                                        print(f"[Worker] SWITCH_AND_PASTE switch OK (attempt {attempt+1}): {os.path.basename(target_name)}", flush=True)
                                        break
                                except Exception:
                                    pass
                            else:
                                break

                        # ★ SendMessage(WM_PASTE) - COM active 무관, HWND 직접 지정
                        # hwp.Run("Paste")는 Win32 UI 포커스 기준 → 포커스 역전 시 소스로 감
                        # SendMessage는 지정 HWND에 직접 전달 → 포커스 상태 무관
                        WM_PASTE = 0x0302
                        paste_sent = False
                        target_hwnd = None
                        try:
                            target_hwnd = doc.WindowHandle
                        except Exception:
                            pass

                        try:
                            active_name = hwp.XHwpDocuments.Active_XHwpDocument.FullName
                            print(f"[Worker] SWITCH_AND_PASTE before paste → active: {os.path.basename(active_name)}, hwnd={target_hwnd}", flush=True)
                        except Exception:
                            pass

                        if target_hwnd:
                            try:
                                # 1차: 최상위 문서 창에 WM_PASTE 직접 전송
                                ret = ctypes.windll.user32.SendMessageW(
                                    target_hwnd, WM_PASTE, 0, 0)
                                print(f"[Worker] SendMessage(WM_PASTE) → hwnd={target_hwnd}, ret={ret}", flush=True)
                                paste_sent = True
                            except Exception as e_send:
                                print(f"[Worker] SendMessage failed: {e_send}", flush=True)

                            if not paste_sent:
                                # 2차: EnumChildWindows로 편집 자식창 탐색 후 전송
                                try:
                                    child_hwnds = []
                                    def _enum_cb(hwnd, _):
                                        child_hwnds.append(hwnd)
                                        return True
                                    ctypes.windll.user32.EnumChildWindows(
                                        target_hwnd,
                                        ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(_enum_cb),
                                        0)
                                    for ch in child_hwnds:
                                        ctypes.windll.user32.SendMessageW(ch, WM_PASTE, 0, 0)
                                    print(f"[Worker] SendMessage(WM_PASTE) → {len(child_hwnds)} child hwnds", flush=True)
                                    paste_sent = True
                                except Exception as e_child:
                                    print(f"[Worker] EnumChild SendMessage failed: {e_child}", flush=True)

                        if not paste_sent:
                            # 최후 fallback: hwp.Run (포커스 의존)
                            print(f"[Worker] fallback → hwp.Run(Paste)", flush=True)
                            hwp.Run("Paste")

                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"SwitchAndPaste failed: {e}"))

                elif cmd_type == CMD_INSERT_TEXT:
                    text_content = cmd_data[1]
                    try:
                        act = hwp.CreateAction("InsertText")
                        pset = act.CreateSet()
                        act.GetDefault(pset)
                        pset.SetItem("Text", text_content)
                        act.Execute(pset)
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"InsertText failed: {e}"))

                elif cmd_type == CMD_DOC_COUNT:
                    result_queue.put(("SUCCESS", hwp.XHwpDocuments.Count))

                elif cmd_type == CMD_GET_SELECTED_HEIGHT:
                    """
                    Measures the height of the currently selected area in mm.
                    For invisible instances, GetSelectedPos might be less reliable.
                    If selection fails, we use a fallback by checking the Y-coordinates of start/end.
                    """
                    try:
                        pos_data = hwp.GetSelectedPos() # (x1, y1, x2, y2, ...)
                        if pos_data:
                            x1, y1, x2, y2 = pos_data[:4]
                            x1, y1, x2, y2 = pos_data[:4]
                            height_units = abs(y2 - y1)
                            height_mm = height_units / 283.465
                            result_queue.put(("SUCCESS", height_mm))
                        else:
                            # Fallback: Use distance between two points if no selection object returned
                            # Try to get positions from selection
                            hwp.Run("MoveSelBegin")
                            p1 = hwp.GetPos()
                            hwp.Run("MoveSelEnd")
                            p2 = hwp.GetPos()
                            
                            if p1 and p2:
                                # Simple Para diff calc if getting detailed pos fails
                                # This is rough estimate but better than 0
                                # 1 para ~= 10mm estimate
                                para_diff = abs(p2[1] - p1[1]) + 1
                                result_queue.put(("SUCCESS", para_diff * 15.0))
                            else:
                                result_queue.put(("SUCCESS", 0.0))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Height measurement failed: {e}"))

                elif cmd_type == CMD_FIND_STRING:
                    text = cmd_data[1]
                    direction = cmd_data[2] if len(cmd_data) > 2 else 1
                    # Basic find string logic
                    hset = hwp.HParameterSet.HFindReplace
                    hwp.HAction.GetDefault("RepeatFind", hset.HSet)
                    hset.FindString = text
                    hset.Direction = direction
                    res = hwp.HAction.Execute("RepeatFind", hset.HSet)
                    result_queue.put(("SUCCESS", res))

                elif cmd_type == CMD_FIND_REPLACE:
                    find_str = cmd_data[1]
                    replace_str = cmd_data[2]
                    # 문서 처음으로 이동 (Run 방식)
                    hwp.Run("MoveDocBegin")
                    replaced = 0
                    for _ in range(100):  # 최대 100회 반복
                        hset = hwp.HParameterSet.HFindReplace
                        hwp.HAction.GetDefault("RepeatFind", hset.HSet)
                        hset.FindString = find_str
                        hset.Direction = 1
                        hset.IgnoreMessage = 1  # "검색 결과 없음" 다이얼로그 억제 → timeout 방지
                        found = hwp.HAction.Execute("RepeatFind", hset.HSet)
                        if not found:
                            break
                        # 찾은 텍스트 선택 상태에서 바로 입력으로 교체
                        hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
                        hwp.HParameterSet.HInsertText.Text = replace_str
                        hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)
                        replaced += 1
                    result_queue.put(("SUCCESS", replaced))

                elif cmd_type == CMD_RUN_COMMAND:
                    hwp_cmd = cmd_data[1]
                    hwp.Run(hwp_cmd)
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_SET_POS:
                    hwp.SetPos(cmd_data[1], cmd_data[2], cmd_data[3])
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_FORMAT_ENDNOTES:
                    # '나이수 성공' 버전: 정확한 범위 선택 및 속성 적용
                    endnote_positions = cmd_data[1]
                    formatted_count = 0
                    
                    for list_id, para, pos in endnote_positions:
                        try:
                            # 시작과 끝 위치를 이용해 정확히 3글자 선택 (예: "1) ")
                            start_pos = (list_id, para, pos)
                            end_pos = (list_id, para, pos + 3)
                            
                            hwp.SetPos(*start_pos)
                            hwp.Run("Select")
                            hwp.SetPos(*end_pos)
                            
                            # 글자 모양 변경 (성공했던 속성명)
                            hset = hwp.HParameterSet.HCharShape
                            hwp.HAction.GetDefault("CharShape", hset.HSet)
                            hset.Height = 1800  # 18pt
                            hset.Bold = 1
                            hset.TextColor = 0x000000 
                            hwp.HAction.Execute("CharShape", hset.HSet)
                            
                            hwp.Run("Cancel")
                            formatted_count += 1
                        except: pass
                    
                    result_queue.put(("SUCCESS", formatted_count))

                elif cmd_type == CMD_REMOVE_PARAGRAPH_NUMBERS:
                    """
                    Double Lock Solution: 1차 액션(ParagraphShapeNone) + 2차 속성 강제(HeadingType=0)
                    안그 친구분의 조언대로 '단축키 흉내'가 아닌 '진짜 명령'을 이중으로 적용
                    """
                    try:
                        # 1. 문서 전체 선택
                        hwp.Run("MoveDocBegin")
                        hwp.Run("SelectAll")
                        time.sleep(0.5)
                        
                        # [1타] 직통 버튼 액션 실행
                        hwp.HAction.Run("ParagraphShapeNone")
                        time.sleep(0.2)
                        
                        # [2타] 속성 강제 확인 사살 (HeadingType=0) - 안전한 CreateAction 패턴 사용
                        act = hwp.CreateAction("ParagraphShape")
                        pset = act.CreateSet()
                        act.GetDefault(pset)
                        pset.SetItem("HeadingType", 0)
                        act.Execute(pset)
                        
                        # 3. 선택 해제
                        hwp.Run("Cancel")
                        
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Remove paragraph numbers failed: {str(e)}"))

                elif cmd_type == CMD_LOCK_SCREEN:
                    try:
                        # Some versions of HWP require no parameters, others might need a boolean
                        hwp.LockCommand()
                    except:
                        try: hwp.LockCommand(True)
                        except: pass
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_UNLOCK_SCREEN:
                    try:
                        hwp.UnlockCommand()
                    except:
                        try: hwp.UnlockCommand(False)
                        except: pass
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_SCAN_TEXT:
                    """
                    Uses GetTextFile("TEXT", "") as a more stable alternative to InitScan 
                    for fetching the entire document text at once.
                    """
                    try:
                        full_text = hwp.GetTextFile("TEXT", "")
                        result_queue.put(("SUCCESS", full_text))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Full text scan failed: {e}"))

                elif cmd_type == CMD_GET_XML:
                    """Exports the current HWP document as HWPML2X XML string."""
                    try:
                        xml_content = hwp.GetTextFile("HWPML2X", "")
                        result_queue.put(("SUCCESS", xml_content if xml_content else ""))
                    except Exception as e:
                        result_queue.put(("ERROR", f"XML export failed: {e}"))
                        
                elif cmd_type == CMD_GET_PARA_TEXT:
                    """Gets the text of a specific paragraph using InitScan (prevents focus stealing)."""
                    try:
                        list_id, para = cmd_data[1], cmd_data[2]
                        hwp.SetPos(list_id, para, 0)
                        
                        # Range: 0 (All), 1 (Block), 2 (Current Para)
                        # Option: 15 (0x0F) includes all text and control characters (e.g. images)
                        hwp.InitScan(15, 2, 0, 0, 0, 0)
                        ret, text = hwp.GetText()
                        hwp.ReleaseScan()
                        
                        result_queue.put(("SUCCESS", text if text else ""))
                    except Exception as e:
                        try:
                            hwp.ReleaseScan()
                        except: pass
                        result_queue.put(("SUCCESS", ""))

                elif cmd_type == CMD_GET_PARA_CHAR_COUNT:
                    """Count total characters (including OLE controls like equations) in a para.
                    Returns 0 for truly empty paragraphs, >0 if any content (text or embedded objects).
                    """
                    try:
                        list_id, para = cmd_data[1], cmd_data[2]
                        hwp.SetPos(list_id, para, 0)
                        # SelectPara selects the entire paragraph
                        hwp.Run("MoveParaBegin")
                        hwp.Run("Select")
                        hwp.Run("MoveParaEnd")
                        # GetSelectedPos gives char extents
                        p1 = hwp.GetPos()
                        hwp.Run("MoveParaBegin")
                        p0 = hwp.GetPos()
                        hwp.Run("Cancel")
                        # char count = difference in char position within same para
                        char_count = abs(p1[2] - p0[2]) if p1 and p0 and p1[1] == p0[1] else 0
                        result_queue.put(("SUCCESS", char_count))
                    except Exception:
                        result_queue.put(("SUCCESS", 0))

                elif cmd_type == CMD_FIND_BOUNDARY_CONTROL:
                    """
                    Boundary Detection:
                    Moves cursor to end of current paragraph as a safe baseline.
                    This prevents over-selection while still capturing multi-line problems.
                    """
                    try:
                        curr_pos = hwp.GetPos()
                        # Move to current paragraph end
                        hwp.Run("MoveParaEnd")
                        final_pos = hwp.GetPos()
                        
                        # Anti-wrap-around safety: if we wrapped to doc start, reset
                        if final_pos[1] < curr_pos[1]:
                            hwp.SetPos(*curr_pos)
                            hwp.Run("MoveLineEnd")
                            final_pos = hwp.GetPos()
                        
                        result_queue.put(("SUCCESS", final_pos))
                    except Exception as e:
                        result_queue.put(("LOG", f"[Boundary] Core Error: {e}"))
                        result_queue.put(("SUCCESS", None))


                        

                elif cmd_type == CMD_GET_HEIGHT_PRECISE:
                    """
                    Expert Method: Uses GetPagePos() or Estimation Fallback.
                    NEVER returns error (prevents worker restarts).
                    """
                    height_mm = 0
                    try:
                        # 1. Standard GetPagePos (Preferred)
                        hwp.Run("MoveDocBegin")
                        p1 = hwp.GetPagePos()
                        hwp.Run("MoveDocEnd")
                        p2 = hwp.GetPagePos()
                        
                        if p1 and p2 and len(p1) > 4 and len(p2) > 4:
                            y1, y2 = p1[4], p2[4]
                            # Simple height calculation in same document
                            height_mm = abs(y2 - y1) / 283.465
                    except: pass
                    
                    # 2. Fallback: Paragraph-based Estimation if pixel measurement failed
                    if height_mm < 1.0:
                        try:
                            # Forces document scan to update ParaCount if needed
                            hwp.Run("MoveDocEnd")
                            last_pos = hwp.GetPos()
                            para_count = last_pos[1] + 1
                            # Heuristic: ~12mm per paragraph for common math fonts
                            height_mm = 10.0 + (para_count * 12.0)
                        except:
                            height_mm = 60.0 # Extreme fallback (typical problem height)
                    
                    result_queue.put(("SUCCESS", height_mm))

                elif cmd_type == CMD_GET_PARA_COUNT:
                    """Returns the total number of paragraphs in the main body."""
                    try:
                        # Try to get it from the XHwpDocuments collection which is most reliable
                        count = hwp.XHwpDocuments.Item(0).ParaCount
                        result_queue.put(("SUCCESS", count))
                    except:
                        try:
                            # Fallback 1: Property on object
                            count = hwp.ParaCount
                            result_queue.put(("SUCCESS", count))
                        except:
                            try:
                                # Fallback 2: GetPos at document end
                                hwp.Run("MoveDocEnd")
                                pos = hwp.GetPos()
                                result_queue.put(("SUCCESS", pos[1] + 1))
                            except:
                                result_queue.put(("SUCCESS", 0))

                elif cmd_type == CMD_GET_PARA_END:
                    """
                    Moves to end of current paragraph and returns position.
                    Uses Run("MoveParaEnd") which is safer than MovePos(2).
                    """
                    try:
                        curr = hwp.GetPos()
                        hwp.Run("MoveParaEnd")
                        new_pos = hwp.GetPos()
                        # If it wrapped to doc start (para 0), reset to original or try better
                        if new_pos[1] < curr[1]:
                            hwp.SetPos(*curr)
                            hwp.Run("MoveLineEnd") # Next best thing
                            new_pos = hwp.GetPos()
                        result_queue.put(("SUCCESS", new_pos))
                    except:
                        result_queue.put(("SUCCESS", None))


                elif cmd_type == CMD_CLOSE_DOC:
                    idx = cmd_data[1]
                    count = hwp.XHwpDocuments.Count
                    safe_idx = min(max(0, idx), count - 1) if count > 0 else 0
                    try:
                        doc = hwp.XHwpDocuments.Item(safe_idx)
                        doc.Close(False) # False = Do not save
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Close doc failed: {e}"))

                elif cmd_type == CMD_UNDO:
                    hwp.Run("Undo")
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_BREAK_ODD_SECTION:
                    # 구역 나누기 후 "홀수 쪽에서 시작" 설정
                    # → 한글이 자동으로 짝수 페이지이면 빈 페이지 추가 보장
                    try:
                        hwp.Run("BreakSection")
                        hwp.HAction.GetDefault("SectionDef", hwp.HParameterSet.HSecDef.HSet)
                        # PageStartPosition: 0=이어서, 1=새쪽, 2=짝수쪽, 3=홀수쪽
                        hwp.HParameterSet.HSecDef.PageStartPosition = 3
                        hwp.HAction.Execute("SectionDef", hwp.HParameterSet.HSecDef.HSet)
                        print("[BreakOddSection] 홀수 구역 나누기 완료 (PageStartPosition=3)")
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        print(f"[BreakOddSection] SectionDef 실패, BreakPage로 대체: {e}")
                        try:
                            hwp.Run("BreakPage")
                            result_queue.put(("SUCCESS", False))  # False = fallback
                        except Exception as e2:
                            result_queue.put(("ERROR", f"BreakOddSection fallback도 실패: {e2}"))

                elif cmd_type == CMD_GET_LAYOUT_STATE:
                    """
                    Returns (Page, ListID, Y_pos) for layout monitoring.
                    Page is 1-based, ListID is 0 for main/1 for column etc.
                    Y_pos is in HWP units.
                    """
                    try:
                        # Get KeyIndicator (Page info): (SPage, Page, FramePage, TotalPage, ...)
                        # Caution: Some environments return (True, SPage, ...) or similar wrapper
                        indicator = hwp.KeyIndicator()
                        # KeyIndicator 공식 반환 형식: (IsModified, SPoint, Point, FramePoint, FoNo, IsFoNoHead)
                        # IsModified=bool, SPoint=구역번호, Point=현재쪽(1-based), FramePoint=인쇄용지번호
                        offset = 1 if isinstance(indicator[0], bool) else 0

                        # offset+1 = Point (현재 쪽 번호) ← 핵심
                        # offset+2 = FramePoint (인쇄 용지 번호, 페이지 아님)
                        page = indicator[offset + 1]
                        col = indicator[offset + 2]
                        
                        # Get Pos (ListID, Para, Pos)
                        pos_info = hwp.GetPos()
                        
                        # Get absolute Y position
                        hwp.Run("Select")
                        sel_pos = hwp.GetSelectedPos()
                        hwp.Run("Cancel")
                        
                        y_pos = sel_pos[1] if sel_pos else 0
                        
                        result_queue.put(("SUCCESS", (page, col, y_pos)))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Get layout state failed: {e}"))

                elif cmd_type == CMD_SET_PARA_MARGIN:
                    """
                    Adjust paragraph spacing (prev/next). 
                    payload: (prev_mm, next_mm)
                    """
                    try:
                        prev_mm, next_mm = cmd_data[1]
                        hset = hwp.HParameterSet.HParaShape
                        hwp.HAction.GetDefault("ParaShape", hset.HSet)
                        # HWP uses 1/100 mm units for spacing
                        hset.PrevSpacing = int(prev_mm * 100)
                        hset.NextSpacing = int(next_mm * 100)
                        hwp.HAction.Execute("ParaShape", hset.HSet)
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Set para margin failed: {e}"))

                elif cmd_type == CMD_SET_CHAR_SPACING:
                    """
                    Adjust character spacing (micro-compression).
                    payload: spacing_percent (-50 to 50)
                    """
                    try:
                        spacing = int(cmd_data[1])
                        hset = hwp.HParameterSet.HCharShape
                        hwp.HAction.GetDefault("CharShape", hset.HSet)
                        hset.Spacing = spacing
                        hwp.HAction.Execute("CharShape", hset.HSet)
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Set char spacing failed: {e}"))

                elif cmd_type == CMD_FIND_BARRIER_POS:
                    """
                    Searches for a list of barrier keywords and returns the position of the FIRST one found.
                    Used to detect 'Answer & Explanation' sections.
                    """
                    keywords = cmd_data[1]
                    min_pos = None

                    try:
                        for kw in keywords:
                            hwp.Run("MoveDocBegin")
                            
                            hset = hwp.HParameterSet.HFindReplace
                            hwp.HAction.GetDefault("RepeatFind", hset.HSet)
                            hset.FindString = kw
                            hset.Direction = 1
                            hset.IgnoreMessage = 1
                            
                            if hwp.HAction.Execute("RepeatFind", hset.HSet):
                                hwp.Run("MoveSelBegin")
                                pos = hwp.GetPos() # (List, Para, Pos)
                                
                                if min_pos is None:
                                    min_pos = pos
                                else:
                                    # Compare paragraphs
                                    if pos[1] < min_pos[1] or (pos[1] == min_pos[1] and pos[2] < min_pos[2]):
                                        min_pos = pos
                        
                        result_queue.put(("SUCCESS", min_pos))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Find barrier failed: {e}"))

                elif cmd_type == CMD_CLEAR:
                    """
                    Clear all documents and ensure a fresh one is open.
                    """
                    try:
                        hwp.Clear(1) # 1 = discard current, keep window
                        # Force new if count is 0
                        if hwp.XHwpDocuments.Count == 0:
                            hwp.XHwpDocuments.Add(True)
                    except Exception as e:
                        result_queue.put(("LOG", f"[Warning] Clear failed: {e}"))
                    
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_MOVE_COLUMN_END:
                    """
                    Moves cursor to the end of the current column.
                    Returns the final position.
                    """
                    try:
                        # Move to end of current column
                        hwp.Run("MoveColumnEnd")
                        final_pos = hwp.GetPos()
                        result_queue.put(("SUCCESS", final_pos))
                    except Exception as e:
                        # Fallback: try paragraph end
                        try:
                            hwp.Run("MoveParaEnd")
                            final_pos = hwp.GetPos()
                            result_queue.put(("SUCCESS", final_pos))
                        except:
                            result_queue.put(("ERROR", f"MoveColumnEnd failed: {e}"))

                elif cmd_type == CMD_GET_COLUMN_INFO:
                    """
                    Returns (current_column, total_columns) based on KeyIndicator.
                    """
                    try:
                        indicator = hwp.KeyIndicator()
                        offset = 1 if isinstance(indicator[0], bool) else 0
                        current_col = indicator[offset + 3]  # Column index
                        # Total columns is harder to get, return current for now
                        result_queue.put(("SUCCESS", {"current_col": current_col}))
                    except Exception as e:
                        result_queue.put(("ERROR", f"GetColumnInfo failed: {e}"))

                elif cmd_type == CMD_MOVE_PAGE_END:
                    """
                    Moves cursor to the end of the current page.
                    Returns the final position.
                    """
                    try:
                        # Move to end of current page
                        hwp.Run("MovePageEnd")
                        final_pos = hwp.GetPos()
                        result_queue.put(("SUCCESS", final_pos))
                    except Exception as e:
                        # Fallback: try column end
                        try:
                            hwp.Run("MoveColumnEnd")
                            final_pos = hwp.GetPos()
                            result_queue.put(("SUCCESS", final_pos))
                        except:
                            result_queue.put(("ERROR", f"MovePageEnd failed: {e}"))

                elif cmd_type == CMD_SET_VISIBLE:
                    is_visible = cmd_data[1]
                    try:
                        hwp.XHwpWindows.Item(0).Visible = is_visible
                    except: pass
                    result_queue.put(("SUCCESS", True))

                elif cmd_type == CMD_RUN:
                    # User requested explicit RUN command
                    try:
                        hwp.Run(cmd_data[1])
                        result_queue.put(("SUCCESS", True))
                    except Exception as e:
                        result_queue.put(("ERROR", f"Run failed: {e}"))

                elif cmd_type == CMD_EXTRACT_XML:
                    # Generic HWPML2X extraction
                    try:
                        xml = hwp.GetTextFile("HWPML2X", "")
                        result_queue.put(("SUCCESS", xml))
                    except Exception as e:
                        result_queue.put(("ERROR", f"XML Extraction failed: {e}"))


                else:
                    result_queue.put(("ERROR", f"Unknown Command: {cmd_type}"))

            except Exception as e:
                result_queue.put(("ERROR", f"Worker Cmd Error ({cmd_type}): {str(e)}"))

    except Exception as e:
        result_queue.put(("FATAL", str(e)))
    finally:
        stop_watchdog.set()
        if hwp:
            try:
                hwp.Clear(3)  # Expert recommendation: Clear before Quit
                hwp.Quit()
            except: pass
        pythoncom.CoUninitialize()

class RobustHwpController:
    def __init__(self, visible=True, max_restarts=3, cleanup_cache=True):
        if cleanup_cache:
            _clean_gen_py_cache()
            
        self._process = None
        self._cmd_queue = None
        self._result_queue = None
        self._visible = visible
        self._hwp_pid = None
        self._restart_count = 0
        self._max_restarts = max_restarts
        self.start_worker()

    def start_worker(self):
        self._kill_process()
        
        self._cmd_queue = multiprocessing.Queue()
        self._result_queue = multiprocessing.Queue()
        
        self._process = multiprocessing.Process(
            target=_hwp_worker_loop,
            args=(self._cmd_queue, self._result_queue, self._visible)
        )
        self._process.daemon = True
        self._process.start()
        
        try:
            self._wait_for_response(timeout=30, context="INIT")
        except Exception as e:
            self._kill_process()
            raise e

    def _wait_for_response(self, timeout, context):
        """Absolute time-based timeout"""
        deadline = time.time() + timeout
        
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"HWP Timeout ({context})")
                
            try:
                status, payload = self._result_queue.get(timeout=min(remaining, 1.0))
                
                if status == "SUCCESS": return payload
                if status == "INIT_SUCCESS":
                    self._hwp_pid = payload
                    return True
                if status == "LOG":
                    print(payload)
                    continue
                if status == "ALIVE_ACK": return True
                if status == "ERROR": raise HwpCommandError(payload)
                if status == "FATAL": raise Exception(f"Worker Fatal: {payload}")
                
            except queue.Empty:
                continue

    def _kill_process(self):
        if self._process:
            if self._process.is_alive():
                print("[HwpController] Terminating worker process...")
                self._process.terminate()
                self._process.join(timeout=2)
            self._process = None

        if self._hwp_pid:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(self._hwp_pid)], 
                               capture_output=True, check=False, creationflags=win32con.CREATE_NO_WINDOW)
            except:
                pass
            self._hwp_pid = None

    def _execute(self, cmd_type, *args, timeout=30):
        """Execute command with strict Auto-Restart logic"""
        if not self._process or not self._process.is_alive():
            print("[HwpController] Process died. Restarting...")
            self.start_worker()

        try:
            # 원상복구: *args를 풀지 않고 튜플 그대로 전달 (이전 방식)
            if len(args) == 0:
                self._cmd_queue.put((cmd_type,))
            elif len(args) == 1:
                self._cmd_queue.put((cmd_type, args[0]))
            else:
                self._cmd_queue.put((cmd_type, *args))
            
            result = self._wait_for_response(timeout, context=cmd_type)
            self._restart_count = 0
            return result
            
        except HwpCommandError as e:
            # Logic error from worker - DO NOT RESTART
            print(f"[HwpController] Command Error (Non-fatal) during '{cmd_type}': {e}")
            raise e
            
        except (TimeoutError, Exception) as e:
            print(f"[HwpController] Error during '{cmd_type}': {e}")
            print("[HwpController] Perform 'Kill & Restart'...")
            
            self._kill_process()
            
            self._restart_count += 1
            if self._restart_count > self._max_restarts:
                raise Exception(f"Max HWP restarts exceeded ({self._max_restarts}). Last error: {e}")
            
            print(f"[HwpController] Auto-restarting worker (attempt {self._restart_count}/{self._max_restarts})...")
            try:
                self.start_worker()
                print("[HwpController] Worker restarted successfully. Ready for next command.")
            except Exception as restart_err:
                raise Exception(f"Failed to restart worker: {restart_err}")
            
            raise e

    # Interface Methods
    def open(self, path, timeout=120, readonly=False):
        return self._execute(CMD_OPEN, os.path.abspath(path), readonly, timeout=timeout)
    
    def save(self, doc_idx):
        """Save using doc.FullName (expert solution)"""
        return self._execute(CMD_SAVE, doc_idx)

    def save_active(self, file_path, timeout=30):
        """현재 활성 문서를 SetActive 없이 즉시 저장 (switch_doc 직후 호출 전용)"""
        return self._execute(CMD_SAVE_ACTIVE, os.path.abspath(file_path), timeout=timeout)
    
    def close_doc(self, doc_idx):
        """Close a specific document without saving (assumes already saved)"""
        return self._execute(CMD_CLOSE_DOC, doc_idx)

    def save_as(self, path, format="HWP"):
        """Save As new file"""
        return self._execute(CMD_SAVE_AS, os.path.abspath(path), format)

    def undo(self):
        """Undo last action"""
        return self._execute(CMD_UNDO)

    def get_layout_state(self):
        """Returns (Page, ListID, Y_pos)"""
        return self._execute(CMD_GET_LAYOUT_STATE)

    def break_odd_section(self):
        """구역 나누기 + 홀수 쪽에서 시작 설정. 미주가 항상 홀수 페이지에서 시작되도록 보장."""
        return self._execute(CMD_BREAK_ODD_SECTION)
    
    def switch_doc(self, idx): 
        return self._execute(CMD_SWITCH_DOC, idx)
    
    def get_text(self, timeout=30): 
        """
        Get text from document using GetTextFile (Worker returns full text)
        """
        # Worker가 GetTextFile("TEXT", "") 결과를 반환함
        return self._execute(CMD_GET_TEXT, timeout=timeout)
    
    def get_doc_count(self): 
        return self._execute(CMD_DOC_COUNT)
    
    def get_pos(self): 
        return self._execute(CMD_GET_POS)
    
    def select_range(self, start_pos, end_pos):
        return self._execute(CMD_SELECT_RANGE, start_pos, end_pos)

    def delete_first_empty_para(self):
        """버퍼 문서의 첫 빈 단락 삭제 (MoveLeft 선택으로 여분 포함된 경우)"""
        return self._execute(CMD_DELETE_FIRST_EMPTY_PARA)

    def copy(self):
        return self._execute(CMD_COPY)
    
    def paste(self):
        return self._execute(CMD_PASTE)

    def switch_and_paste(self, target_doc_idx, timeout=30):
        """switch_doc + paste를 Worker 내부에서 원자적으로 실행.
        IPC 왕복 사이에 HWP 메시지 큐가 소스 WM_ACTIVATE를 처리해서
        포커스가 역전되는 레이스 컨디션을 제거."""
        return self._execute(CMD_SWITCH_AND_PASTE, target_doc_idx, timeout=timeout)

    def move_pos(self, move_id): 
        return self._execute(CMD_MOVE_POS, move_id)
    
    def set_pos(self, list_id, para, pos):
        """Set cursor to specific position (list_id, para, pos)"""
        return self._execute(CMD_SET_POS, list_id, para, pos)
        
    def get_para_text(self, list_id, para):
        """Gets text content of a specific paragraph."""
        return self._execute(CMD_GET_PARA_TEXT, list_id, para)

    def get_para_char_count(self, list_id, para):
        """Returns character count in paragraph (includes OLE/equation controls).
        Use to detect equation/image-only paragraphs that are non-blank but return empty text."""
        return self._execute(CMD_GET_PARA_CHAR_COUNT, list_id, para)
    
    def find_string(self, text, direction=1):
        """Find string in document. Returns True if found, False otherwise."""
        return self._execute(CMD_FIND_STRING, text, direction)

    def find_replace(self, find_str, replace_str):
        """문서 전체에서 find_str을 replace_str로 일괄 치환."""
        return self._execute(CMD_FIND_REPLACE, find_str, replace_str)
    
    def get_selected_height(self):
        """Measures the vertical height of the current selection in mm."""
        return self._execute(CMD_GET_SELECTED_HEIGHT)

    # Shadowed run_command removed to avoid conflict
    # def run_command(self, hwp_cmd):
    #     return self._execute(CMD_RUN_COMMAND, hwp_cmd)

        
    def find_barrier_pos(self, keywords):
        """Finds the earliest position of any keyword in the list."""
        return self._execute(CMD_FIND_BARRIER_POS, keywords)
    
    def move_column_end(self):
        """Moves cursor to the end of the current column. Returns final position."""
        return self._execute(CMD_MOVE_COLUMN_END)
    
    def get_column_info(self):
        """Returns column information dict with 'current_col' key."""
        return self._execute(CMD_GET_COLUMN_INFO)
    
    def move_page_end(self):
        """Moves cursor to the end of the current page. Returns final position."""
        return self._execute(CMD_MOVE_PAGE_END)

    def find_all_endnotes(self):
        """Find all endnote positions using InitScan (expert solution)"""
        return self._execute(CMD_FIND_ENDNOTES, timeout=60)
    
    def format_endnotes(self, endnote_positions):
        """Format all endnotes: Bold + 18pt + Black"""
        return self._execute(CMD_FORMAT_ENDNOTES, endnote_positions, timeout=60)
    
    def remove_paragraph_numbers(self):
        """Remove all paragraph numbers (Ctrl+Shift+Insert)"""
        return self._execute(CMD_REMOVE_PARAGRAPH_NUMBERS)

    def lock_screen(self):
        """Lock screen/Hwp commands to boost performance."""
        return self._execute(CMD_LOCK_SCREEN)

    def unlock_screen(self):
        """Unlock screen."""
        return self._execute(CMD_UNLOCK_SCREEN)

    def scan_text(self):
        """Fetch all text from document using buffered InitScan."""
        return self._execute(CMD_SCAN_TEXT)

    def get_xml(self, timeout=30):
        """Exports the current HWP document as HWPML2X XML string (used by HWPXMLParser)."""
        return self._execute(CMD_GET_XML, timeout=timeout)

    def get_para_count(self):
        """Returns the total number of paragraphs in the document."""
        return self._execute(CMD_GET_PARA_COUNT)

    def get_para_end(self):
        """Moves to the end of the current paragraph and returns its coordinates."""
        return self._execute(CMD_GET_PARA_END)

    def get_height_precise(self):
        """Measures the total height of the document content in mm using GetPagePos."""
        return self._execute(CMD_GET_HEIGHT_PRECISE)

    def find_boundary_control(self):
        """Find the next Table ($tbl) or boundary after current position."""
        return self._execute(CMD_FIND_BOUNDARY_CONTROL)
    
    def clear_all(self):
        """Clear all documents (expert solution)"""
        return self._execute(CMD_CLEAR)
    
    def set_visible(self, is_visible: bool):
        """Dynamically change HWP window visibility"""
        return self._execute(CMD_SET_VISIBLE, is_visible)

    def run(self, action_name):
        """
        Executes an HWP action (e.g., 'MoveDocEnd', 'BreakPara').
        Wrapper for threading/automation robustness.
        """
        try:
            # This HwpController class communicates with a worker process.
            # Direct COM calls like self.hwp.HAction.Run(action_name) are not
            # possible here. The original implementation correctly used _execute.
            # Reverting to the _execute pattern for consistency.
            return self._execute(CMD_RUN, action_name)
        except Exception as e:
            try:
                print(f"HWP Action Failed: {action_name} - {e}")
            except:
                print(f"HWP Action Failed: {action_name} - (Encoding Error)")

    def extract_xml(self):
        """
        Extracts the entire document as HWPML2X XML.
        대용량 파일(1MB+)도 안전하게 처리하기 위해 타임아웃 60초 적용.
        """
        return self._execute(CMD_EXTRACT_XML, timeout=60)

    def run_command(self, cmd_type, *args):
        """
        Generic wrapper for _execute. 
        Unpacks tuple args if passed as a single argument for compatibility.
        """
        # If args is a tuple, check if first element is a tuple (nested)
        if len(args) == 1 and isinstance(args[0], tuple):
            return self._execute(cmd_type, *args[0])
        return self._execute(cmd_type, *args)

    def quit(self):
        """Complete cleanup sequence (expert validated)"""
        try:
            if self._process and self._process.is_alive():
                # Clear all documents first (expert recommendation)
                try:
                    self._cmd_queue.put((CMD_CLEAR,))
                    time.sleep(0.5)
                except:
                    pass
                
                self._cmd_queue.put((CMD_QUIT,))
                self._process.join(timeout=3)
        except: pass
        self._kill_process()

    def __enter__(self): return self
    def __exit__(self, *args): self.quit()

    def set_para_margin(self, prev_mm: float, next_mm: float):
        return self._execute(CMD_SET_PARA_MARGIN, (prev_mm, next_mm))
    
    def set_char_spacing(self, spacing_percent: int):
        return self._execute(CMD_SET_CHAR_SPACING, spacing_percent)
