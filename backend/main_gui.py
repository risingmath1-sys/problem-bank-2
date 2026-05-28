"""문제은행2 로컬 GUI 메인 (데스크탑 / Windows + HWP COM 필수).

📌 운영 역할 분리 정책 (2026-05-23 확정):
  - 문제 출제 = SC (server/, FastAPI) — 브라우저로 접근
  - 문제 등록(인덱싱) = 로컬 (이 파일 + HWP COM)
  - 인덱싱 관련 코드(backend/indexers/*, naesin_n_unit_map.json, hwp_metadata_parser_v2.py)
    는 로컬 위주로 손볼 것. 서버는 같은 backend/ 모듈을 import 만 함.
  - 자세한 내용: 서버클라이언트_설계도.md § 0-B / system_architecture.md "핵심 원칙"
"""
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog
import os
import sys
import threading
import time
import json
import math
from typing import List, Dict

# ★ SQLite-only 모드 강제 (2026-05-26)
#   - Firestore 쓰기 차단 (인덱싱 / 출제 / 저장 모두 SQLite 만)
#   - data_engine.py 의 default 도 'sqlite' 이지만, 안전망으로 여기서도 명시
#   - Firebase Auth (로그인) 는 backend/auth.py 에서 그대로 사용
os.environ.setdefault("DATA_ENGINE", "sqlite")

# ── 경로 결정 (frozen vs dev) ─────────────────────────────────
# base_dir       : 사용자 데이터 (DB / 로그 / 출제 결과) — 쓰기 가능
# resource_dir   : PyInstaller 번들 내부 리소스 (JSON / Firebase 키) — 읽기 전용
if getattr(sys, 'frozen', False):
    # PyInstaller 동결 모드: .exe 옆이 base, _MEIPASS 가 resource
    base_dir = os.path.dirname(sys.executable)
    resource_dir = sys._MEIPASS
    # frozen 모드에서 main_gui.py 는 _MEIPASS 루트에 있으나 backend/* 리소스는
    # _MEIPASS/backend/ 아래에 번들됨. dev 모드에서는 main_gui.py 가 backend/ 안.
    # 그래서 "main_gui.py 와 같은 폴더에 있는 리소스" 는 frozen 에서 _MEIPASS/backend/
    _backend_dir = os.path.join(sys._MEIPASS, 'backend')
else:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resource_dir = base_dir
    _backend_dir = os.path.dirname(os.path.abspath(__file__))

# ★ 콘솔 출력을 파일로도 저장 (디버깅용)
_log_path = os.path.join(base_dir, "debug_console.log")
class _Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except: pass
    def flush(self):
        for s in self.streams:
            try: s.flush()
            except: pass
_log_file = open(_log_path, "w", encoding="utf-8", buffering=1)
sys.stdout = _Tee(sys.__stdout__, _log_file)
sys.stderr = _Tee(sys.__stderr__, _log_file)

# Add the project root to sys.path to allow 'from backend.xxx' imports
if not getattr(sys, 'frozen', False):
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

import shutil
from backend.hwp_metadata_parser_v2 import HWPMetadataParserV2
from backend.hwp_generator import HWPGenerator
from backend.db_engine import LocalDBEngine
from backend.data_engine import make_engine, get_engine_mode
from backend.indexer_registry import get_indexer

# --- UI Constants ---
CLR_BG = "#1e1e1e"        # Deep Charcoal
CLR_FG = "#ffffff"        # White
CLR_ACCENT = "#3a86ff"    # Vibrant Blue
CLR_PANEL = "#2d2d2d"     # Panel Gray
CLR_BORDER = "#404040"    # Border Gray
FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 12, "bold")

class ModernProblemScannerGUI:
    def __init__(self, root, session=None):
        self.root = root
        self.session = session or {}
        self.root.title("AnG HWP Management Engine")
        self.root.geometry("800x900")
        self.root.configure(bg=CLR_BG)
        
        self.output_dir = os.path.join(base_dir, "indexed_results")
        _cfg_path = os.path.join(_backend_dir, "curriculum_config.json")
        # Phase 4-A: DATA_ENGINE=firestore 일 때 캐시 + Firestore 하이브리드,
        # 기본은 LocalDBEngine 그대로 (env 미설정 시).
        # Phase 5: parser 가 엔진 ingest_indexed_problems 를 사용 → 엔진 먼저 생성.
        _local_db_path = os.path.join(base_dir, "problem_bank.db")
        print(f"[main_gui] DATA_ENGINE={get_engine_mode()}")
        self.db_engine = make_engine(_local_db_path)
        self.parser = HWPMetadataParserV2(
            output_dir=self.output_dir,
            config_path=_cfg_path,
            engine=self.db_engine,
        )
        self.folder_path = None
        self.source_hwp_dir = tk.StringVar(value=os.path.join(base_dir, "exercise"))
        self.force_update_var = tk.BooleanVar(value=False)
        self.stealth_var = tk.BooleanVar(value=True)  # Instantiated here to avoid AttributeError
        self.current_indexer = None  # 현재 선택된 소스 인덱서

        # ── 사용자 정보 (Phase 2 로그인 시스템에서 주입) ─────────────
        # 세션 없이 직접 실행되는 경우(테스트 등)는 익명 user1 로 폴백.
        if self.session:
            self.current_user_id = self.session.get("uid", "user1")
            self.current_user_role = self.session.get("role", "user")
            self.current_user_display_id = self.session.get("display_id", "user1")
            self.current_user_display_name = self.session.get("display_name", "")
        else:
            self.current_user_id = "user1"
            self.current_user_role = "user"
            self.current_user_display_id = "user1"
            self.current_user_display_name = ""

        # ── 선호도 필터 저장값 (settings.json 로드 전 기본값) ───────
        self._saved_pref_filter_enabled = False
        self._saved_pref_Good  = True
        self._saved_pref_Soso  = True
        self._saved_pref_Bad   = True
        self._saved_pref_scope = "mine"

        # ── 일회성 출제 제외 (탭 1 랜덤출제 전용, DB 미저장) ──────────
        # 한 시험지 작성 세션 동안 유지되며, "돌아가기"/"닫기"/"전체 해제" 시 비워짐.
        # ExclusionSettingDialog에서 시험지 단위로 체크 → 그 시험지의 problem_ids가 채워짐.
        self._oneshot_excluded_problem_ids: set = set()
        self._oneshot_excluded_test_ids: set = set()  # UI 상태(어떤 시험지 체크되었는지)
        self._load_curriculum_config()
        self._load_unit_hierarchy()
        
        self._apply_styles()
        
        # --- Main Layout with Tabs ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tab 0 (홈)
        self.tab_home = tk.Frame(self.notebook, bg="#1a1a2e")
        self.notebook.add(self.tab_home, text="  홈  ")

        # Tab 1: 랜덤출제
        self.tab_random = tk.Frame(self.notebook, bg=CLR_BG)
        self.notebook.add(self.tab_random, text=" 랜덤 출제 (Random) ")

        # Tab 2: 원본출제
        self.tab_exam = tk.Frame(self.notebook, bg=CLR_BG)
        self.notebook.add(self.tab_exam, text=" 원본출제 ")

        # Tab 3: 시험지 관리
        self.tab_library = tk.Frame(self.notebook, bg=CLR_BG)
        self.notebook.add(self.tab_library, text=" 시험지 관리 (Library) ")

        # Tab 4: 문제 등록 (admin 전용)
        self.tab_reg = tk.Frame(self.notebook, bg=CLR_BG)
        if self.current_user_role == "admin":
            self.notebook.add(self.tab_reg, text=" 문제 등록 (Scan/Register) ")

        # Tab 5: 문제 관리 (admin 전용)
        self.tab_manage = tk.Frame(self.notebook, bg=CLR_BG)
        if self.current_user_role == "admin":
            self.notebook.add(self.tab_manage, text=" 문제 관리 (Management) ")

        # Tab 6: 사용자 관리 (admin 전용) — Phase 2-H
        self.tab_users = tk.Frame(self.notebook, bg=CLR_BG)
        if self.current_user_role == "admin":
            self.notebook.add(self.tab_users, text=" 사용자 관리 ")

        # 저장된 설정 불러오기 (source_hwp_dir 등)
        self._load_settings()

        # Build tabs (admin 전용 탭은 admin 일 때만 빌드)
        self._build_home_tab()
        self._build_random_tab()
        self._build_exam_gen_tab()
        self._build_library_tab()
        if self.current_user_role == "admin":
            self._build_registration_tab()
            self._build_management_tab()
            self._build_users_tab()

        # 홈 탭 진입 시 통계 갱신
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # =========================================================
    # 홈 화면
    # =========================================================
    def _build_home_tab(self):
        """메인 홈 화면 구성"""
        tab = self.tab_home
        BG = "#1a1a2e"
        BG2 = "#16213e"
        tab.configure(bg=BG)

        # ── 헤더 ──────────────────────────────────────────────
        header = tk.Frame(tab, bg=BG)
        header.pack(fill="x", padx=30, pady=(24, 12))

        # 학원 로고 이미지 — 텍스트 상단에 맞춰 top-align
        try:
            from PIL import Image, ImageTk
            _logo_path = os.path.join(_backend_dir, "logo.png")
            _img = Image.open(_logo_path).convert("RGBA")
            _img.putdata([
                (r, g, b, 0) if r > 200 and g > 200 and b > 200 else (r, g, b, a)
                for r, g, b, a in _img.getdata()
            ])
            _img = _img.resize((54, 54), Image.LANCZOS)
            self._logo_photo = ImageTk.PhotoImage(_img)
            tk.Label(header, image=self._logo_photo, bg=BG).pack(
                side="left", anchor="n", padx=(38, 16))
        except Exception as e:
            print(f"[Home] 로고 로드 실패: {e}")
            tk.Label(header, text="SS", bg="#3a86ff", fg="white",
                     font=("Segoe UI", 22, "bold"), width=2, relief="flat").pack(
                side="left", anchor="n", padx=(38, 16))

        # 타이틀 + 부제목 (로고 오른쪽, 상단 기준 정렬)
        title_fr = tk.Frame(header, bg=BG)
        title_fr.pack(side="left", anchor="n")
        tk.Label(title_fr, text="상승 Solution", bg=BG, fg="#ffffff",
                 font=("Segoe UI", 24, "bold")).pack(anchor="w")
        tk.Label(title_fr, text="Problem Bank Management System",
                 bg=BG, fg="#7777aa", font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 0))

        # ── 구분선 ─────────────────────────────────────────────
        tk.Frame(tab, bg="#2a2a4c", height=1).pack(fill="x", padx=24, pady=(0, 18))

        # ── 메뉴 카드 ──────────────────────────────────────────
        tk.Label(tab, text="M E N U", bg=BG, fg="#555588",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=30, pady=(0, 6))

        cards_fr = tk.Frame(tab, bg=BG)
        cards_fr.pack(fill="x", padx=20, pady=(0, 22))

        menus = [
            ("랜덤 출제",   "단원 선택 후\n랜덤 출제",   "#3a86ff",
             lambda: self.notebook.select(self.tab_random),  False),
            ("원본 출제",   "원본 그대로\n출제·내보내기", "#06c98a",
             lambda: self.notebook.select(self.tab_exam),    False),
            ("시험지 관리", "생성된 시험지\n열람·관리",   "#7c3aed",
             lambda: self.notebook.select(self.tab_library), False),
            ("문제 등록",   "HWP 스캔 및\nDB 등록",       "#f4700c",
             lambda: self.notebook.select(self.tab_reg),     True),
            ("문제 관리",   "등록 문제\n검색·제외 설정",  "#4a5568",
             lambda: self.notebook.select(self.tab_manage),  True),
        ]
        for title, desc, color, cmd, admin_only in menus:
            if admin_only and self.current_user_role != "admin":
                continue
            self._make_home_card(cards_fr, title, desc, color, cmd)

        # ── 구분선 ─────────────────────────────────────────────
        tk.Frame(tab, bg="#2a2a4c", height=1).pack(fill="x", padx=24, pady=(0, 18))

        # ── 문제 현황 통계 ─────────────────────────────────────
        tk.Label(tab, text="문 제 현 황", bg=BG, fg="#555588",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=30, pady=(0, 8))

        stats_fr = tk.Frame(tab, bg=BG)
        stats_fr.pack(fill="x", padx=20)

        self._home_stat_labels = {}
        stat_defs = [
            ("NAESIN_A",         "내신기출A",  "#f4700c"),
            ("NAESIN_N",         "내신기출B",  "#e85d9a"),
            ("SUNEUNG_SPECIAL",  "수능특강",   "#3a86ff"),
            ("SUNEUNG_COMPLETE", "수능완성",   "#06c98a"),
            ("MOCK_EXAM",        "모의고사",   "#7c3aed"),
        ]
        for src, label_txt, color in stat_defs:
            sc = tk.Frame(stats_fr, bg="#20203c", relief="flat")
            sc.pack(side="left", fill="both", expand=True, padx=5)
            tk.Label(sc, text=label_txt, bg="#20203c", fg="#9999bb",
                     font=("Segoe UI", 9)).pack(pady=(14, 4))
            num_lbl = tk.Label(sc, text="…", bg="#20203c", fg=color,
                               font=("Segoe UI", 22, "bold"))
            num_lbl.pack()
            tk.Label(sc, text="문제", bg="#20203c", fg="#9999bb",
                     font=("Segoe UI", 9)).pack(pady=(2, 14))
            self._home_stat_labels[src] = num_lbl

        # 합계 행
        total_fr = tk.Frame(tab, bg=BG)
        total_fr.pack(fill="x", padx=24, pady=(14, 20))
        tk.Label(total_fr, text="총 등록 문제", bg=BG, fg="#9999bb",
                 font=("Segoe UI", 11)).pack(side="left")
        self._home_total_lbl = tk.Label(total_fr, text="…", bg=BG,
                                        fg="#ffffff",
                                        font=("Segoe UI", 15, "bold"))
        self._home_total_lbl.pack(side="left", padx=(8, 4))
        tk.Label(total_fr, text="문제", bg=BG, fg="#9999bb",
                 font=("Segoe UI", 11)).pack(side="left")

        # ── 구분선 ─────────────────────────────────────────────
        tk.Frame(tab, bg="#2a2a4c", height=1).pack(fill="x", padx=24, pady=(4, 14))

        # ── 원본 파일 폴더 설정 ────────────────────────────────
        tk.Label(tab, text="원 본 파 일 폴 더", bg=BG, fg="#555588",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=30, pady=(0, 6))

        folder_fr = tk.Frame(tab, bg="#20203c")
        folder_fr.pack(fill="x", padx=20, pady=(0, 20))

        tk.Label(folder_fr, text="폴더 경로:", bg="#20203c", fg="#9999bb",
                 font=("Segoe UI", 9)).pack(side="left", padx=(14, 6), pady=12)
        tk.Entry(folder_fr, textvariable=self.source_hwp_dir,
                 bg="#2e2e4e", fg="#ccccff", insertbackground="white",
                 relief="flat", font=("Segoe UI", 9), state="readonly",
                 readonlybackground="#2e2e4e").pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(folder_fr, text="  폴더 선택  ", command=self._browse_source_dir,
                  bg="#3a86ff", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2").pack(side="left", padx=10, pady=8)

        # 초기 통계 로드
        self.root.after(200, self._update_home_stats)

    def _make_home_card(self, parent, title, desc, color, command):
        """홈 메뉴 카드 생성 (클릭 가능)"""
        card = tk.Frame(parent, bg=color, cursor="hand2")
        card.pack(side="left", fill="both", expand=True, padx=5, pady=4)

        tk.Label(card, text=title, bg=color, fg="#ffffff",
                 font=("Segoe UI", 11, "bold")).pack(pady=(18, 5), padx=8)
        tk.Label(card, text=desc, bg=color, fg="#dddddd",
                 font=("Segoe UI", 9), justify="center").pack(pady=(0, 18), padx=8)

        def on_click(e):
            command()

        card.bind("<Button-1>", on_click)
        for w in card.winfo_children():
            w.bind("<Button-1>", on_click)

    def _update_home_stats(self):
        """소스별 문제 수를 DB에서 조회하여 홈 통계 갱신"""
        if not hasattr(self, '_home_stat_labels'):
            return
        total = 0
        had_error = False
        for src, lbl in self._home_stat_labels.items():
            try:
                cnt = self.db_engine.query_counts({"source": src},
                                                  include_excluded=True)
                lbl.config(text=f"{cnt:,}", foreground="black")
            except Exception as e:
                had_error = True
                cnt = 0
                print(f"[home_stats] {src} 조회 실패: {e}")
                lbl.config(text="—", foreground="red")
            total += cnt
        if hasattr(self, '_home_total_lbl'):
            if had_error:
                self._home_total_lbl.config(text="DB 오류", foreground="red")
            else:
                self._home_total_lbl.config(text=f"{total:,}", foreground="black")

    def _on_tab_changed(self, event=None):
        """탭 변경 이벤트 — 홈 탭 진입 시 통계 갱신"""
        try:
            if self.notebook.select() == str(self.tab_home):
                self._update_home_stats()
        except Exception as e:
            print(f"[on_tab_changed] {e}")

    def _load_curriculum_config(self):
        config_path = os.path.join(_backend_dir, "curriculum_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.curr_config = json.load(f)
        except Exception as e:
            print(f"Error loading curriculum config: {e}")
            self.curr_config = {"curriculums": {"2022개정교육과정": {"subjects": []}, "2015개정교육과정": {"subjects": []}}}
        
        # 2026-05-23: 2015/2022 코드 체계가 unit_hierarchy.json 에서 동일하게 통합됨
        # → 변환 불필요. 옛 매핑(curriculum_mappings.2015_to_2022)은 잔재로 사고 원인이었음.
        # _reverse_mapping 은 다른 코드 호환성을 위해 빈 dict 로 유지.
        self._reverse_mapping = {}
        print(f"[Curriculum] 2015/2022 코드 통합 — 변환 매핑 비활성")

    def _load_unit_hierarchy(self):
        hierarchy_path = os.path.join(_backend_dir, "unit_hierarchy.json")
        try:
            with open(hierarchy_path, "r", encoding="utf-8") as f:
                self.unit_hierarchy = json.load(f)
        except Exception as e:
            print(f"Error loading unit hierarchy: {e}")
            self.unit_hierarchy = {"2015": [], "2022": []}

    def _apply_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Notebook Tab Colors
        style.configure("TNotebook", background=CLR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=CLR_PANEL, foreground="#aaaaaa", padding=[15, 5])
        style.map("TNotebook.Tab", 
                  background=[("selected", CLR_ACCENT)], 
                  foreground=[("selected", "white")])
        
        # Frame
        style.configure("TFrame", background=CLR_BG)
        style.configure("Panel.TFrame", background=CLR_PANEL)
        
        # Label
        style.configure("TLabel", background=CLR_BG, foreground=CLR_FG, font=FONT_MAIN)
        style.configure("Title.TLabel", font=FONT_TITLE, foreground=CLR_ACCENT)
        style.configure("Panel.TLabel", background=CLR_PANEL, foreground=CLR_FG, font=FONT_MAIN)
        
        # Entry / Combobox — 흰 배경 + 검은 글자
        style.configure("TEntry", fieldbackground="white", foreground="#111111", borderwidth=1)
        style.configure("TCombobox", fieldbackground="white", background="white", foreground="#111111", borderwidth=1, selectbackground="#d0e4ff", selectforeground="#111111")
        style.map("TCombobox",
                  fieldbackground=[("readonly", "white"), ("disabled", "#e0e0e0")],
                  foreground=[("readonly", "#111111"), ("disabled", "#888888")],
                  background=[("readonly", "white")])
        
        # Button
        style.configure("TButton", font=FONT_BOLD, padding=10)
        style.map("TButton", 
                  background=[('pressed', CLR_ACCENT), ('active', '#5495ff')],
                  foreground=[('active', 'white')])
        
        # Progressbar
        style.configure("Horizontal.TProgressbar", thickness=10, troughcolor=CLR_PANEL, background=CLR_ACCENT)

    def _build_registration_tab(self):
        """Entry point for registration tab: always shows source selector first."""
        self.current_source_type = None
        self._build_source_selector()

    # ──────────────────────────────────────────────────────────────
    # SOURCE SELECTOR  (6 big buttons)
    # ──────────────────────────────────────────────────────────────
    def _build_source_selector(self):
        """Shows the 6-button source selection screen."""
        for w in self.tab_reg.winfo_children():
            w.destroy()

        # ── 전체 배경 ──
        bg = tk.Frame(self.tab_reg, bg=CLR_BG)
        bg.pack(fill="both", expand=True)

        # ── 타이틀 영역 ──
        title_frame = tk.Frame(bg, bg=CLR_BG, pady=30)
        title_frame.pack(fill="x")
        tk.Label(title_frame,
                 text="📚  문제 등록  —  소스를 선택하세요",
                 font=("Segoe UI", 18, "bold"),
                 bg=CLR_BG, fg=CLR_FG).pack()
        tk.Label(title_frame,
                 text="등록할 문제의 출처에 맞는 버튼을 클릭하세요",
                 font=("Segoe UI", 10),
                 bg=CLR_BG, fg="#888888").pack(pady=(4, 0))

        # ── 버튼 그리드 (2열 × 3행) ──
        grid = tk.Frame(bg, bg=CLR_BG)
        grid.pack(expand=True)  # 수직 가운데 정렬

        # 소스 정의: (코드, 아이콘, 줄1, 줄2, 배경색, hover색)
        SOURCES = [
            ("NAESIN_A",        "📝", "내신기출A",  "(내기왕)",         "#1a4ed8", "#1e40af"),
            ("NAESIN_N",        "📝", "내신기출B",  "(N)",              "#0f766e", "#0d6161"),
            ("SUNEUNG_SPECIAL", "📖", "수능특강",   "",                 "#b45309", "#92400e"),
            ("SUNEUNG_COMPLETE","📖", "수능완성",   "",                 "#7c3aed", "#6d28d9"),
            ("MOCK_EXAM",       "🏆", "모의고사",   "",                 "#be185d", "#9d174d"),
            ("TEXTBOOK",        "📗", "일반 문제집", "쎈 / RPM / 고쟁이", "#15803d", "#166534"),
        ]

        BTN_W, BTN_H = 22, 5   # 버튼 너비(문자), 높이(줄)
        FONT_ICON  = ("Segoe UI Emoji", 26)
        FONT_LINE1 = ("Segoe UI", 16, "bold")
        FONT_LINE2 = ("Segoe UI", 10)

        for idx, (code, icon, line1, line2, clr, hover_clr) in enumerate(SOURCES):
            row, col = divmod(idx, 2)

            # 버튼을 Frame으로 감싸서 패딩 추가
            cell = tk.Frame(grid, bg=CLR_BG, padx=12, pady=10)
            cell.grid(row=row, column=col)

            # 내부 버튼 컨테이너 (실제 버튼처럼 보이는 Frame)
            btn_frame = tk.Frame(cell, bg=clr, cursor="hand2",
                                 width=220, height=130)
            btn_frame.pack_propagate(False)
            btn_frame.pack()

            # 아이콘
            icon_lbl = tk.Label(btn_frame, text=icon,
                                font=FONT_ICON, bg=clr, fg="white")
            icon_lbl.pack(pady=(18, 0))

            # 첫째 줄 (과목명)
            lbl1 = tk.Label(btn_frame, text=line1,
                            font=FONT_LINE1, bg=clr, fg="white")
            lbl1.pack()

            # 둘째 줄 (부제목 — 없으면 빈 줄)
            lbl2 = tk.Label(btn_frame, text=line2,
                            font=FONT_LINE2, bg=clr, fg="#dddddd")
            lbl2.pack()

            # 호버 + 클릭 효과
            all_widgets = [btn_frame, icon_lbl, lbl1, lbl2]
            def _enter(e, f=btn_frame, ww=all_widgets, hc=hover_clr):
                f.config(bg=hc)
                for w in ww: w.config(bg=hc)
            def _leave(e, f=btn_frame, ww=all_widgets, nc=clr):
                f.config(bg=nc)
                for w in ww: w.config(bg=nc)
            def _click(e, c=code):
                self._on_source_selected(c)

            for w in all_widgets:
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)
                w.bind("<Button-1>", _click)

    def _on_source_selected(self, source_type: str):
        """소스 버튼 클릭 시 해당 등록 폼으로 전환."""
        self.current_source_type = source_type
        self.current_indexer = get_indexer(source_type)
        for w in self.tab_reg.winfo_children():
            w.destroy()
        if self.current_indexer is not None:
            self._build_reg_form(source_type)
        else:
            self._build_reg_form_placeholder(source_type)

    def _build_reg_back_button(self, parent):
        """등록 폼 상단에 공통으로 붙는 '← 소스 선택으로' 뒤로가기 버튼."""
        back_bar = tk.Frame(parent, bg=CLR_BG, pady=6, padx=10)
        back_bar.pack(fill="x", side="top")
        tk.Button(back_bar, text="←  소스 선택으로",
                  command=self._build_source_selector,
                  bg=CLR_PANEL, fg="#aaaaaa",
                  font=("Segoe UI", 9), relief="flat",
                  padx=10, pady=4, cursor="hand2").pack(side="left")
        tk.Label(back_bar,
                 text=f"현재 소스:  {self.current_source_type}",
                 font=("Segoe UI", 9, "bold"),
                 bg=CLR_BG, fg=CLR_ACCENT).pack(side="left", padx=15)

    # ──────────────────────────────────────────────────────────────
    # REGISTRATION FORM  — 공통 폼 (모든 소스 공용)
    # 소스별 차이는 self.current_indexer.get_schema()["fields"]로만 표현
    # ──────────────────────────────────────────────────────────────
    def _build_reg_form(self, source_type: str):
        """공통 등록 폼 — get_schema()의 fields를 읽어 사이드바를 동적으로 렌더링."""
        schema = self.current_indexer.get_schema()

        # ── 뒤로가기 버튼 ──
        self._build_reg_back_button(self.tab_reg)

        # ── 사이드바 ──
        self.sidebar = tk.Frame(self.tab_reg, width=250, bg=CLR_PANEL, bd=0)
        self.sidebar.pack(side="left", fill="y")

        tk.Label(self.sidebar, text="스캔 설정", font=FONT_TITLE,
                 bg=CLR_PANEL, fg=CLR_ACCENT, pady=20).pack()

        input_container = tk.Frame(self.sidebar, bg=CLR_PANEL, padx=20)
        input_container.pack(fill="x")

        self.entries = {}
        curr_keys = list(self.curr_config.get("curriculums", {}).keys())

        # ── 소스별 필드 동적 렌더링 ──
        for field in schema["fields"]:
            key     = field["key"]
            ftype   = field["type"]
            default = field.get("default", "")

            tk.Label(input_container, text=key, font=FONT_MAIN,
                     bg=CLR_PANEL, fg="#aaaaaa", anchor="w").pack(fill="x", pady=(10, 2))

            if ftype == "entry":
                w = tk.Entry(input_container, bg=CLR_BORDER, fg=CLR_FG,
                             insertbackground="white", bd=0, font=FONT_MAIN)
                w.pack(fill="x", ipady=5)
                if default:
                    w.insert(0, default)

            elif ftype == "combo":
                w = ttk.Combobox(input_container, values=field.get("values", []), state="readonly")
                w.pack(fill="x")
                w.set(default)

            elif ftype == "curr":
                # 교육과정 드롭다운 — 과목명(subj)과 연동
                w = ttk.Combobox(input_container, values=curr_keys, state="readonly")
                w.pack(fill="x")
                preferred = default if default in curr_keys else (curr_keys[0] if curr_keys else "")
                w.set(preferred)
                w.bind("<<ComboboxSelected>>", self._on_curriculum_change)

            elif ftype == "subj":
                # 과목명 드롭다운 — _on_curriculum_change()가 값을 채움
                w = ttk.Combobox(input_container, state="readonly")
                w.pack(fill="x")

            else:
                # 알 수 없는 타입 — entry로 폴백
                w = tk.Entry(input_container, bg=CLR_BORDER, fg=CLR_FG,
                             insertbackground="white", bd=0, font=FONT_MAIN)
                w.pack(fill="x", ipady=5)

            self.entries[key] = w

        # subj 필드가 있으면 초기 과목 목록 채우기
        if "과목명" in self.entries:
            self._on_curriculum_change()

        # ── 공통 옵션 ──
        tk.Label(input_container, text="인덱싱 옵션", font=FONT_MAIN,
                 bg=CLR_PANEL, fg="#aaaaaa", anchor="w").pack(fill="x", pady=(10, 2))
        tk.Checkbutton(input_container, text="기존 데이터 덮어쓰기",
                       variable=self.force_update_var,
                       bg=CLR_PANEL, fg=CLR_FG, selectcolor=CLR_PANEL,
                       activebackground=CLR_PANEL, activeforeground=CLR_FG,
                       font=FONT_MAIN, bd=0, highlightthickness=0).pack(fill="x", pady=2)
        tk.Checkbutton(input_container, text="스텔스 모드 (백그라운드)",
                       variable=self.stealth_var,
                       bg=CLR_PANEL, fg=CLR_FG, selectcolor=CLR_PANEL,
                       activebackground=CLR_PANEL, activeforeground=CLR_FG,
                       font=FONT_MAIN, bd=0, highlightthickness=0).pack(fill="x", pady=2)

        self.cancel_btn = tk.Button(self.sidebar, text="취소",
                                    command=self.cancel_scan,
                                    bg="#666666", fg="white", font=FONT_BOLD,
                                    relief="flat", pady=10, cursor="hand2",
                                    state="disabled")
        self.cancel_btn.pack(side="bottom", fill="x", padx=20, pady=(0, 10))

        self.start_btn = tk.Button(self.sidebar, text="엔진 가동 시작",
                                   command=self.start_scan,
                                   bg=CLR_ACCENT, fg="white", font=FONT_BOLD,
                                   relief="flat", pady=15, cursor="hand2")
        self.start_btn.pack(side="bottom", fill="x", padx=20, pady=(30, 0))

        self._scan_cancel = threading.Event()

        # ── 메인 컨텐츠 영역 (모든 소스 동일) ──
        self.main_content = tk.Frame(self.tab_reg, bg=CLR_BG, padx=30, pady=20)
        self.main_content.pack(side="right", fill="both", expand=True)

        header = tk.Frame(self.main_content, bg=CLR_BG)
        header.pack(fill="x")
        tk.Label(header, text="엔진 상태 모니터", font=FONT_TITLE,
                 bg=CLR_BG, fg=CLR_FG).pack(side="left")

        btn_container = tk.Frame(header, bg=CLR_BG)
        btn_container.pack(side="right")
        self.folder_btn = tk.Button(btn_container, text="폴더 선택",
                                    command=self.select_folder,
                                    bg=CLR_PANEL, fg=CLR_FG, font=FONT_MAIN,
                                    relief="flat", padx=15)
        self.folder_btn.pack(side="right", padx=(5, 0))
        self.file_btn = tk.Button(btn_container, text="파일 선택",
                                  command=self.select_file,
                                  bg=CLR_PANEL, fg=CLR_FG, font=FONT_MAIN,
                                  relief="flat", padx=15)
        self.file_btn.pack(side="right")

        self.working_path = None
        self.working_mode = "folder"

        self.folder_info = tk.Label(self.main_content,
                                    text="대상을 선택해 주세요 (폴더 또는 파일)",
                                    font=FONT_MAIN, bg=CLR_BG, fg="#777777", pady=10)
        self.folder_info.pack(anchor="w")

        # 통계
        self.stats_frame = tk.Frame(self.main_content, bg=CLR_PANEL, pady=15, padx=20)
        self.stats_frame.pack(fill="x", pady=(0, 10))
        self.stats_labels = {}
        for i, (label_text, key) in enumerate([
                ("총 가공 파일", "files"), ("총 추출 문항", "problems"), ("오류/누락", "errors")]):
            frame = tk.Frame(self.stats_frame, bg=CLR_PANEL)
            frame.grid(row=0, column=i, sticky="nsew", padx=20)
            self.stats_frame.grid_columnconfigure(i, weight=1)
            tk.Label(frame, text=label_text, font=FONT_MAIN,
                     bg=CLR_PANEL, fg="#888888").pack()
            self.stats_labels[key] = tk.Label(frame, text="0",
                                              font=("Segoe UI", 14, "bold"),
                                              bg=CLR_PANEL, fg=CLR_FG)
            self.stats_labels[key].pack()
        self._update_stats()

        # 진행바
        prog_frame = tk.Frame(self.main_content, bg=CLR_BG, pady=10)
        prog_frame.pack(fill="x")
        self.progress = ttk.Progressbar(prog_frame, mode="indeterminate",
                                        style="Horizontal.TProgressbar")
        self.progress.pack(fill="x")
        self.status_label = tk.Label(prog_frame, text="준비 완료",
                                     bg=CLR_BG, fg=CLR_ACCENT, font=FONT_BOLD)
        self.status_label.pack(side="left", pady=5)

        # 로그
        tk.Label(self.main_content, text="실시간 가공 로그", font=FONT_BOLD,
                 bg=CLR_BG, fg="#777777").pack(anchor="w", pady=(20, 5))
        self.log_widget = scrolledtext.ScrolledText(
            self.main_content, bg=CLR_PANEL, fg="#bbbbbb",
            insertbackground="white", bd=0, font=("Consolas", 10), height=30)
        self.log_widget.pack(fill="both", expand=True)

    # ──────────────────────────────────────────────────────────────
    # REGISTRATION FORM  ②~⑥  준비 중 플레이스홀더
    # ──────────────────────────────────────────────────────────────
    def _build_reg_form_placeholder(self, source_type: str):
        """아직 구현되지 않은 소스의 임시 화면."""
        LABEL_MAP = {
            "NAESIN_N":        "내신기출B (N)",
            "SUNEUNG_SPECIAL": "수능특강",
            "SUNEUNG_COMPLETE":"수능완성",
            "MOCK_EXAM":       "모의고사",
            "TEXTBOOK":        "일반 문제집",
        }
        self._build_reg_back_button(self.tab_reg)

        center = tk.Frame(self.tab_reg, bg=CLR_BG)
        center.pack(fill="both", expand=True)

        tk.Label(center,
                 text=f"🚧  {LABEL_MAP.get(source_type, source_type)}",
                 font=("Segoe UI", 22, "bold"),
                 bg=CLR_BG, fg=CLR_FG).pack(expand=True, pady=(80, 10))
        tk.Label(center,
                 text="해당 소스 등록 기능은 현재 개발 중입니다.",
                 font=("Segoe UI", 12),
                 bg=CLR_BG, fg="#888888").pack()
        tk.Label(center,
                 text="← 소스 선택으로 돌아가 다른 소스를 이용하세요.",
                 font=("Segoe UI", 10),
                 bg=CLR_BG, fg="#666666").pack(pady=(8, 0))

    def _build_exam_gen_tab(self):
        """원본출제 탭 - 소스 선택 → 필터 → 파일 목록 → 문제 미리보기"""
        container = tk.Frame(self.tab_exam, bg="white", padx=15, pady=15)
        container.pack(fill="both", expand=True)

        # ── 1. 헤더 + 액션 버튼 ──────────────────────────────────────────
        header_row = tk.Frame(container, bg="white")
        header_row.pack(fill="x", pady=(0, 8))

        tk.Label(header_row, text="원본출제", font=("Segoe UI", 16, "bold"),
                 bg="white", fg="#333").pack(side="left")

        btn_frame = tk.Frame(header_row, bg="white")
        btn_frame.pack(side="right")
        tk.Button(btn_frame, text="마침", command=self._orig_finish,
                  bg="#555", fg="white", font=FONT_MAIN, width=8).pack(side="right", padx=5)
        tk.Button(btn_frame, text="시험지출제", command=self._orig_generate,
                  bg="#1976d2", fg="white", font=("Segoe UI", 10, "bold"), padx=10).pack(side="right", padx=5)
        tk.Button(btn_frame, text="시험지저장", command=self._orig_save_to_db,
                  bg="white", fg="#1976d2", font=("Segoe UI", 10, "bold"), padx=10).pack(side="right", padx=5)

        # ── 2. 소스 선택 (토글 라디오버튼) ───────────────────────────────
        src_row = tk.Frame(container, bg="white")
        src_row.pack(fill="x", pady=(0, 6))
        tk.Label(src_row, text="소스:", font=FONT_BOLD, bg="white", fg="#333").pack(side="left", padx=(0, 8))

        ORIG_SOURCES = [
            ("NAESIN_A",        "내신기출A"),
            ("NAESIN_N",        "내신기출B"),
            ("SUNEUNG_SPECIAL", "수능특강"),
            ("SUNEUNG_COMPLETE","수능완성"),
            ("MOCK_EXAM",       "모의고사"),
        ]
        self.orig_source_var = tk.StringVar(value="NAESIN_A")
        for code, label in ORIG_SOURCES:
            tk.Radiobutton(src_row, text=label, variable=self.orig_source_var, value=code,
                           bg="white", font=FONT_MAIN, command=self._orig_on_source_change,
                           indicatoron=False, padx=10, pady=3, relief="groove",
                           selectcolor="#1976d2", fg="#333",
                           activebackground="#e3f0ff").pack(side="left", padx=3)

        # ── 4. 필터 영역 ──────────────────────────────────────────────────
        filter_frame = tk.Frame(container, bg="white", pady=6, padx=10, relief="solid", bd=1)
        filter_frame.pack(fill="x", pady=(0, 8))
        self.orig_filters = {}
        self.orig_filter_rows = {}

        f_grid = tk.Frame(filter_frame, bg="white")
        f_grid.pack(fill="x")

        # ── 4-A. 단일 행: 연도·학년·학기·시험·교육과정·과목·시험범위·난이도·학교 ─
        row1 = tk.Frame(f_grid, bg="white")
        row1.pack(fill="x", pady=2)

        tk.Label(row1, text="연도:", bg="white").pack(side="left", padx=(0, 3))
        self.orig_filters['year'] = tk.Entry(row1, width=6, bg="#f0f0f0")
        self.orig_filters['year'].pack(side="left", padx=(0, 8))
        self.orig_filters['year'].bind("<Return>", self._orig_search)

        # 내신기출 전용 위젯 — 생성만, pack은 _orig_on_source_change()에서
        curr_keys = list(self.curr_config.get("curriculums", {}).keys())
        self.orig_filters['grade']      = ttk.Combobox(row1, values=["", "고1", "고2", "고3", "중1", "중2", "중3"], width=5, state="readonly")
        self.orig_filters['semester']   = ttk.Combobox(row1, values=["", "1학기", "2학기"], width=6, state="readonly")
        self.orig_filters['exam_type']  = ttk.Combobox(row1, values=["", "중간고사", "기말고사"], width=8, state="readonly")
        self.orig_filters['curriculum'] = ttk.Combobox(row1, values=[""] + curr_keys, width=13, state="readonly")
        self.orig_filters['curriculum'].bind("<<ComboboxSelected>>", self._orig_on_curriculum_change)
        subjs = [""] + self.curr_config.get("curriculums", {}).get("2015개정교육과정", {}).get("subjects", [])
        self.orig_filters['subject']    = ttk.Combobox(row1, values=subjs, width=11)
        self.orig_filters['subject'].bind("<<ComboboxSelected>>", self._orig_on_subject_change)
        # 시험범위 드롭다운 — 과목 미선택 시 disabled
        self.orig_filters['unit_start'] = ttk.Combobox(row1, values=[], width=14, state="disabled")
        self.orig_filters['unit_end']   = ttk.Combobox(row1, values=[], width=14, state="disabled")
        self.orig_filters['diff_level'] = ttk.Combobox(row1, values=["", "최상", "상", "중", "하"],
                                                        width=5, state="readonly")
        self.orig_filters['school']     = tk.Entry(row1, width=9, bg="#f0f0f0")

        # 순서: 학년·학기·시험·교육과정·과목·시험범위(시작~끝)·난이도·학교
        _lbl = lambda t: tk.Label(row1, text=t, bg="white")
        self.orig_filter_rows['row1_naesin'] = [
            (_lbl("학년:"),                              (0, 3)),
            (self.orig_filters['grade'],                 (0, 5)),
            (_lbl("학기:"),                              (0, 3)),
            (self.orig_filters['semester'],              (0, 5)),
            (_lbl("시험:"),                              (0, 3)),
            (self.orig_filters['exam_type'],             (0, 5)),
            (_lbl("교육과정:"),                          (0, 3)),
            (self.orig_filters['curriculum'],            (0, 5)),
            (_lbl("과목:"),                              (0, 3)),
            (self.orig_filters['subject'],               (0, 5)),
            (_lbl("시험범위:"),                          (0, 3)),
            (self.orig_filters['unit_start'],            (0, 2)),
            (_lbl("~"),                                  (0, 2)),
            (self.orig_filters['unit_end'],              (0, 5)),
            (_lbl("난이도:"),                            (0, 3)),
            (self.orig_filters['diff_level'],            (0, 5)),
            (_lbl("학교:"),                              (0, 3)),
            (self.orig_filters['school'],                (0, 3)),
        ]

        # ── 4-C. 3행: 검색 입력창 + 검색 버튼 (모든 소스 공통) ──────────
        row3 = tk.Frame(f_grid, bg="white")
        row3.pack(fill="x", pady=(0, 4))

        tk.Label(row3, text="검색:", bg="white").pack(side="left", padx=(0, 5))
        self.orig_filters['search'] = tk.Entry(row3, width=35, bg="#f0f0f0")
        self.orig_filters['search'].pack(side="left", padx=(0, 8))
        self.orig_filters['search'].bind("<Return>", self._orig_search)
        tk.Button(row3, text="검색 (Search)", command=self._orig_search,
                  bg=CLR_ACCENT, fg="white", font=FONT_BOLD, relief="flat", padx=20).pack(side="left")

        # ── 5. 좌우 분할 뷰 ──────────────────────────────────────────────
        paned = tk.PanedWindow(container, orient="horizontal", sashwidth=4, bg="#ddd")
        paned.pack(fill="both", expand=True, pady=(0, 10))

        # 왼쪽: 파일 트리
        left_frame = tk.Frame(paned, bg="white")
        paned.add(left_frame, minsize=350)

        self.lbl_orig_file_count = tk.Label(left_frame, text="시험지 목록",
                                            font=FONT_BOLD, bg="white", fg="#555")
        self.lbl_orig_file_count.pack(anchor="w", pady=5)

        self.orig_file_tree = ttk.Treeview(
            left_frame,
            columns=("info", "units", "count", "diff", "filename"),
            show="tree headings", height=20, style="Surian.Treeview"
        )
        self.orig_file_tree.heading("#0",    text="분류 / 파일")
        self.orig_file_tree.heading("info",  text="정보")
        self.orig_file_tree.heading("units", text="시험범위")
        self.orig_file_tree.heading("count", text="문항")
        self.orig_file_tree.heading("diff",  text="난이도")
        self.orig_file_tree.column("#0",    width=180)
        self.orig_file_tree.column("info",  width=140)
        self.orig_file_tree.column("units", width=200)
        self.orig_file_tree.column("count", width=45,  anchor="center")
        self.orig_file_tree.column("diff",  width=70,  anchor="center")
        self.orig_file_tree.column("filename", width=0, stretch=False)

        sc_l = ttk.Scrollbar(left_frame, orient="vertical", command=self.orig_file_tree.yview)
        self.orig_file_tree.configure(yscrollcommand=sc_l.set)
        self.orig_file_tree.pack(side="left", fill="both", expand=True)
        sc_l.pack(side="right", fill="y")
        self.orig_file_tree.bind("<<TreeviewSelect>>", self._on_orig_file_select)

        # 오른쪽: 문제 목록 (읽기 전용)
        right_frame = tk.Frame(paned, bg="white", padx=10)
        paned.add(right_frame, minsize=400)

        self.lbl_orig_count = tk.Label(right_frame, text="출제 문항 목록 (0문항)",
                                       font=FONT_BOLD, bg="white", fg="#555")
        self.lbl_orig_count.pack(anchor="w", pady=5)

        cols = ("sys_id", "no", "unit", "type", "diff")
        self.orig_prob_tree = ttk.Treeview(right_frame, columns=cols, show="headings", height=20)
        self.orig_prob_tree.heading("sys_id", text="SysID")
        self.orig_prob_tree.heading("no", text="번호")
        self.orig_prob_tree.heading("unit", text="단원 (대/중)")
        self.orig_prob_tree.heading("type", text="유형")
        self.orig_prob_tree.heading("diff", text="난이도")
        self.orig_prob_tree.column("sys_id", width=0, stretch=False)
        self.orig_prob_tree.column("no", width=50, anchor="center")
        self.orig_prob_tree.column("unit", width=210)
        self.orig_prob_tree.column("type", width=80, anchor="center")
        self.orig_prob_tree.column("diff", width=60, anchor="center")

        sc_r = ttk.Scrollbar(right_frame, orient="vertical", command=self.orig_prob_tree.yview)
        self.orig_prob_tree.configure(yscrollcommand=sc_r.set)
        self.orig_prob_tree.pack(side="left", fill="both", expand=True)
        sc_r.pack(side="right", fill="y")

        # 초기 로드: 소스 기본값(NAESIN_A) 기준으로 필터 표시 및 검색
        self._orig_on_source_change()


    def _orig_on_curriculum_change(self, event=None):
        """교육과정 선택 시 과목 목록 갱신 + 단원범위 초기화"""
        curr = self.orig_filters['curriculum'].get()
        subjects = self.curr_config.get("curriculums", {}).get(curr, {}).get("subjects", [])
        self.orig_filters['subject']['values'] = [""] + subjects
        self.orig_filters['subject'].set("")
        self._orig_on_subject_change()  # 단원범위 드롭다운도 초기화

    def _get_ordered_units_for_subject(self, subject: str) -> list:
        """과목명으로 교육과정 순서대로 정렬된 중단원 (code, name) 리스트 반환.
        unit_hierarchy.json의 2022→2015 순서로 탐색."""
        for version in ("2022", "2015"):
            for subj_data in self.unit_hierarchy.get(version, []):
                if subj_data.get("subject") == subject:
                    units = []
                    for large in subj_data.get("large_units", []):
                        for medium in large.get("medium_units", []):
                            units.append((medium["code"], medium["name"]))
                    return units
        return []

    def _orig_on_subject_change(self, event=None):
        """과목 변경 시 단원범위 드롭다운 갱신 / 초기화"""
        subj = self.orig_filters['subject'].get()
        unit_start_w = self.orig_filters.get('unit_start')
        unit_end_w   = self.orig_filters.get('unit_end')
        if unit_start_w is None or unit_end_w is None:
            return

        if not subj:
            # 과목 미선택 → 드롭다운 비활성
            for w in (unit_start_w, unit_end_w):
                w.set("")
                w['values'] = []
                w.configure(state="disabled")
            self._naesin_unit_order = []
            return

        # 해당 과목의 순서 단원 목록
        units = self._get_ordered_units_for_subject(subj)
        self._naesin_unit_order = units           # [(code, name), ...]
        labels = [name for _, name in units]      # 드롭다운에는 이름만 표시

        for w in (unit_start_w, unit_end_w):
            w['values'] = labels
            w.set("")
            w.configure(state="readonly")

    def _orig_on_source_change(self):
        """소스 버튼 변경 시 → 내신기출 전용 필터 위젯 show/hide 후 검색 갱신"""
        source = self.orig_source_var.get() if hasattr(self, 'orig_source_var') else 'NAESIN_A'
        is_naesin = source in ('NAESIN_A', 'NAESIN_N')

        for widget, padx in self.orig_filter_rows['row1_naesin']:
            if is_naesin:
                widget.pack(side="left", padx=padx)
            else:
                widget.pack_forget()

        for widget, padx in self.orig_filter_rows.get('row2_naesin', []):
            if is_naesin:
                widget.pack(side="left", padx=padx)
            else:
                widget.pack_forget()

        # 소스 전환 시 모든 필터 초기화 (이전 소스 값 잔존 방지)
        for key, w in self.orig_filters.items():
            try:
                if isinstance(w, ttk.Combobox):
                    w.set("")
                elif isinstance(w, tk.Entry):
                    w.delete(0, "end")
            except Exception:
                pass

        self._orig_search()

    def _orig_search(self, event=None):
        """소스 + 필터 조건으로 파일 목록 검색"""
        source = self.orig_source_var.get() if hasattr(self, 'orig_source_var') else 'NAESIN_A'
        is_naesin = source in ('NAESIN_A', 'NAESIN_N')

        filters = {"source": source}
        filters["year"] = self.orig_filters['year'].get().strip()

        if is_naesin:
            filters["grade"]      = self.orig_filters['grade'].get()
            filters["semester"]   = self.orig_filters['semester'].get()
            filters["exam_type"]  = self.orig_filters['exam_type'].get()
            filters["curriculum"] = self.orig_filters['curriculum'].get()
            filters["school"]     = self.orig_filters['school'].get().strip()
            filters["subject"]    = self.orig_filters['subject'].get()
            _unit_w = self.orig_filters.get('unit')
            unit_kw = _unit_w.get().strip() if _unit_w else ""
            if unit_kw:
                filters['unit_like'] = unit_kw

            # ── 단원 범위 코드 필터 (unit_start ~ unit_end) ──────────────
            unit_start_w = self.orig_filters.get('unit_start')
            unit_end_w   = self.orig_filters.get('unit_end')
            if unit_start_w and unit_end_w:
                start_name = unit_start_w.get().strip()
                end_name   = unit_end_w.get().strip()
                order = getattr(self, '_naesin_unit_order', [])
                if start_name and end_name and order:
                    name_to_idx = {name: i for i, (_, name) in enumerate(order)}
                    si = name_to_idx.get(start_name)
                    ei = name_to_idx.get(end_name)
                    if si is not None and ei is not None:
                        lo, hi = min(si, ei), max(si, ei)
                        range_codes = [order[i][0] for i in range(lo, hi + 1)]
                        if range_codes:
                            filters['unit_range_codes'] = range_codes

        kw = self.orig_filters['search'].get().strip()
        if kw:
            filters['file_name_like'] = kw

        # 트리 초기화
        for item in self.orig_file_tree.get_children():
            self.orig_file_tree.delete(item)

        results = self.db_engine.search_exams_grouped(filters)

        if is_naesin:
            # ── 백분위 임계값 (NAESIN_A 전수조사) ───────────────────
            th10, th30, th60 = self.db_engine.get_naesin_score_thresholds()

            def _diff_badge(score):
                s = score or 0
                if s >= th10 and th10 > 0: return "🔴 최상"
                if s >= th30 and th30 > 0: return "🟠 상"
                if s >= th60 and th60 > 0: return "🟡 중"
                return "🟢 하"

            # 난이도 필터 (UI 선택값)
            diff_filter = self.orig_filters.get('diff_level')
            diff_sel = diff_filter.get() if diff_filter else ""

            school_nodes = {}
            shown = 0
            for r in results:
                score = r.get('adv_score') or 0
                badge = _diff_badge(score)

                # 난이도 필터 적용
                if diff_sel and diff_sel not in badge:
                    continue

                sch = r['school'] or "미분류"
                if sch not in school_nodes:
                    school_nodes[sch] = self.orig_file_tree.insert(
                        "", "end", text=sch, open=True)

                info_parts = [r.get('year',''), r.get('semester',''), r.get('exam_type','')]
                subj = r.get('subject', '')
                info = " ".join(p for p in info_parts if p) + (f" ({subj})" if subj else "")

                # 시험범위 단원 (중복 제거 후 최대 4개 표시)
                units_raw = r.get('units_concat', '') or ''
                unit_list = list(dict.fromkeys(
                    u.strip() for u in units_raw.split(',') if u.strip()))
                units_str = ", ".join(unit_list[:4])
                if len(unit_list) > 4:
                    units_str += f" 외 {len(unit_list)-4}개"

                self.orig_file_tree.insert(
                    school_nodes[sch], "end",
                    text=r['file_name'],
                    values=(info, units_str,
                            f"{r['problem_count']}문항",
                            f"{badge} ({score}점)",
                            r['file_name'])
                )
                shown += 1

            total = shown
        else:
            # 연도 → 파일 그룹 (수특/수완/모의고사 — 기존 방식)
            year_nodes = {}
            for r in results:
                yr = r.get('year') or "연도미상"
                if yr not in year_nodes:
                    year_nodes[yr] = self.orig_file_tree.insert(
                        "", "end", text=yr, open=True)
                subj = r.get('subject', '') or ''
                self.orig_file_tree.insert(
                    year_nodes[yr], "end",
                    text=r['file_name'],
                    values=(subj, "", f"{r['problem_count']}문항", "", r['file_name'])
                )
            total = len(results)

        if hasattr(self, 'lbl_orig_file_count'):
            self.lbl_orig_file_count.config(text=f"시험지 목록 ({total}개)")

    def _on_orig_file_select(self, event):
        """Auto-load problems when a file is selected"""
        selected = self.orig_file_tree.selection()
        if not selected: return

        # Find file node
        file_name = None
        for item in selected:
            vals = self.orig_file_tree.item(item, "values")
            if vals and len(vals) >= 5 and vals[4]:  # filename은 index 4
                file_name = vals[4]
                break
        
        if not file_name:
            # 학교/연도 그룹 노드 클릭 → 우측 패널 초기화 + 카운트 라벨 갱신
            for item in self.orig_prob_tree.get_children():
                self.orig_prob_tree.delete(item)
            self.current_orig_problems = []
            if hasattr(self, 'lbl_orig_count'):
                self.lbl_orig_count.config(text="출제 문항 목록 (파일을 선택하세요)")
            return

        # 원본 파일 전체 문제 로드 (is_excluded 무시 — 원본 그대로)
        problems = self.db_engine.get_problems_by_files([file_name])

        # 오른쪽 패널 초기화
        for item in self.orig_prob_tree.get_children():
            self.orig_prob_tree.delete(item)

        self.current_orig_problems = []

        for p in problems:
            self.current_orig_problems.append(p)
            u_name = f"{p['large_unit']} > {p['middle_unit']}" if p.get('middle_unit') else (p.get('large_unit') or '')
            p_no = p.get('problem_number') or p.get('endnote_index') or '?'
            self.orig_prob_tree.insert("", "end", values=(
                p['id'],
                p_no,
                u_name,
                p.get('problem_type', ''),
                p.get('difficulty', ''),
            ))

        # 카운트 라벨 갱신
        if hasattr(self, 'lbl_orig_count'):
            self.lbl_orig_count.config(text=f"출제 문항 목록 ({len(problems)}문항)")

    def _orig_add_all(self):
        """Adds all problems from selected file to right panel"""
        selected = self.orig_file_tree.selection()
        if not selected: return

        # Find file node
        file_name = None
        for item in selected:
            vals = self.orig_file_tree.item(item, "values")
            if vals and len(vals) >= 5 and vals[4]:  # filename은 index 4
                file_name = vals[4]
                break
        
        if not file_name:
            messagebox.showwarning("선택", "시험지 파일(항목)을 선택해주세요.")
            return

        # Fetch all problems (including excluded)
        # db_engine.get_problems_by_files already sorts by endnote_index
        problems = self.db_engine.get_problems_by_files([file_name])
        
        # [DEBUG] Check if we have coordinates
        if problems:
            print(f"[DEBUG] First problem keys from DB: {list(problems[0].keys())}")
            print(f"[DEBUG] First problem pos_start: {problems[0].get('pos_start')}")

        
        # Clear right panel
        for item in self.orig_prob_tree.get_children():
            self.orig_prob_tree.delete(item)
            
        # Populate
        self.current_orig_problems = [] # For generation
        
        for p in problems:
            self.current_orig_problems.append(p)
            
            # Status text
            status = "정상"
            tags = ()
            if p['is_excluded']:
                 status = "제외됨(출제)"
                 tags = ("excluded",)
            
            u_name = f"{p['large_unit']} > {p['middle_unit']}" if p['middle_unit'] else p['large_unit']
            p_no = p.get('endnote_index', '?')
            
            # Match columns: sys_id, no, unit, type, diff, status
            self.orig_prob_tree.insert("", "end", values=(
                p['id'],
                p_no,
                u_name,
                p['problem_type'],
                p['difficulty'],
                status
            ), tags=tags)
            
        self.orig_prob_tree.tag_configure("excluded", foreground="red")

    def _orig_generate(self):
        """Generates the HWP file using Random Extraction logic"""
        if not hasattr(self, 'current_orig_problems') or not self.current_orig_problems:
            messagebox.showwarning("경고", "출제할 문항이 없습니다. 왼쪽에서 시험지 파일을 선택해주세요.")
            return

        # Set final_problems for _start_hwp_generation_process
        self.final_problems = self.current_orig_problems
        # ★ 이전 저장 시험지의 제목/단원이 따라붙지 않도록 초기화
        self.saved_exam_title = ''
        self.saved_exam_unit = ''

        self._start_hwp_generation_process(exclude_tags=False, fast_answer_key=False)

    def _orig_save_to_db(self):
        """Saves current original exam list as a User Test in DB (Full Dialog)"""
        if not hasattr(self, 'current_orig_problems') or not self.current_orig_problems:
            messagebox.showwarning("경고", "저장할 문항이 없습니다.")
            return

        self.final_problems = self.current_orig_problems
        
        # --- Full Save Dialog (same as Random Extraction tab) ---
        dlg = tk.Toplevel(self.root)
        dlg.title("시험지 저장")
        dlg.geometry("420x380")
        dlg.resizable(False, False)
        dlg.grab_set()
        
        # Center
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 210
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 190
        dlg.geometry(f"+{x}+{y}")
        
        container = tk.Frame(dlg, padx=20, pady=20)
        container.pack(fill="both", expand=True)
        
        # 1. Test Name
        tk.Label(container, text="시험지 이름", font=FONT_BOLD).pack(anchor="w")
        from datetime import datetime
        # Auto-generate title from selected file info
        default_title = f"원본_{datetime.now().strftime('%Y-%m-%d')}"
        if self.current_orig_problems:
            p = self.current_orig_problems[0]
            school = p.get('school', '')
            year = p.get('year', '')
            if school and year:
                default_title = f"[{year}] {school} 원본"
        
        entry_title = tk.Entry(container, font=FONT_MAIN)
        entry_title.pack(fill="x", pady=(0, 10))
        entry_title.insert(0, default_title)
        
        # 2. Unit Summary
        tk.Label(container, text="단원 정보 (선택)", font=FONT_BOLD).pack(anchor="w")
        entry_unit = tk.Entry(container, font=FONT_MAIN)
        entry_unit.pack(fill="x", pady=(0, 10))
        # Auto-fill from problems
        units = list(dict.fromkeys([p.get('large_unit', '') for p in self.current_orig_problems if p.get('large_unit')]))
        entry_unit.insert(0, ", ".join(units[:3]))
        
        # 3. Folder Select
        tk.Label(container, text="저장 폴더", font=FONT_BOLD).pack(anchor="w")
        
        folder_opts, folder_ids = self._build_folder_options()

        cbo_folder = ttk.Combobox(container, values=folder_opts, state="readonly")
        cbo_folder.pack(fill="x", pady=(0, 5))
        cbo_folder.current(0)

        def _add_folder_local():
            name = simpledialog.askstring("새 폴더", "폴더 이름:")
            if name:
                try:
                    res = self.db_engine.create_folder(name, self.current_user_id)
                except Exception as e:
                    messagebox.showerror("오류", f"폴더 생성 실패:\n{e}")
                    return
                if res and res.get('success'):
                    f_opts, f_ids = self._build_folder_options()
                    cbo_folder['values'] = f_opts
                    new_idx = next((i for i, fid in enumerate(f_ids) if fid == res.get('id')), -1)
                    if new_idx != -1:
                        cbo_folder.current(new_idx)
                    nonlocal folder_ids
                    folder_ids = f_ids
                else:
                    messagebox.showerror("오류", (res or {}).get('message', '알 수 없는 오류'))

        tk.Button(container, text="+ 새 폴더 만들기", command=_add_folder_local, bg="#f0f0f0").pack(anchor="e", pady=(0, 15))

        # Save Action
        def _do_save():
            title = entry_title.get().strip()
            summary = entry_unit.get().strip()
            if not title:
                messagebox.showwarning("필수", "시험지 이름을 입력하세요.")
                return

            idx = cbo_folder.current()
            if idx < 0: idx = 0
            dir_id = folder_ids[idx]

            p_ids = [p['id'] for p in self.final_problems]

            data = {
                "title": title,
                "unit_summary": summary,
                "directory_id": dir_id,
                "problem_ids": p_ids,
                "metadata": {}
            }

            try:
                res = self.db_engine.save_test(data, self.current_user_id)
            except Exception as e:
                messagebox.showerror("저장 실패", f"DB 오류:\n{e}")
                return
            if res and res.get('success'):
                messagebox.showinfo("저장 완료", "시험지가 저장되었습니다.")
                # ★ 제목/단원 저장 (출제 시 HWP 파일명·제목 자동생성에 사용)
                self.saved_exam_title = title
                self.saved_exam_unit = summary
                dlg.destroy()
                self._refresh_step_4_explorer()
            else:
                msg = (res or {}).get('message', '알 수 없는 오류')
                messagebox.showerror("저장 실패", msg)
        
        # Buttons
        btn_area = tk.Frame(dlg, pady=10)
        btn_area.pack(fill="x", side="bottom")
        tk.Button(btn_area, text="저장", command=_do_save, bg="#1976d2", fg="white", width=10).pack(side="right", padx=10)
        tk.Button(btn_area, text="취소", command=dlg.destroy, width=8).pack(side="right")


    def _orig_finish(self):
        """Clears selection and resets view, returns to home"""
        if messagebox.askyesno("확인", "작업을 마치고 초기화하시겠습니까?"):
            # Clear Tree Selection
            self.orig_file_tree.selection_remove(self.orig_file_tree.selection())

            # Clear Problem List
            for item in self.orig_prob_tree.get_children():
                self.orig_prob_tree.delete(item)

            self.current_orig_problems = []
            if hasattr(self, 'lbl_orig_count'):
                self.lbl_orig_count.config(text="출제 문항 목록 (0문항)")
            self.notebook.select(self.tab_home)

    def _browse_source_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.source_hwp_dir.set(path)
            self._save_settings()

    def _build_folder_options(self):
        """저장 다이얼로그용 계층형 폴더 목록 생성.
        Returns (folder_opts: list[str], folder_ids: list[int|None])
        하위폴더는 들여쓰기(└)로 계층 표시.
        """
        folders = self.db_engine.get_folders(self.current_user_id)
        opts = ["/ (최상위)"]
        ids = [None]

        def _add_children(parent_id, depth):
            children = [f for f in folders if f.get("parent_id") == parent_id]
            children.sort(key=lambda x: x.get("id", 0))  # 생성 순서 유지
            for f in children:
                prefix = "  " * depth + ("└ " if depth > 0 else "")
                icon = "🔒" if f.get("is_protected") else "📁"
                opts.append(f"{prefix}{icon} {f['name']}")
                ids.append(f["id"])
                _add_children(f["id"], depth + 1)

        _add_children(None, 0)
        return opts, ids

    # ── 설정 저장/불러오기 ────────────────────────────────────────────
    _SETTINGS_PATH = os.path.join(
        base_dir, "settings.json"
    )

    def _load_settings(self):
        """settings.json 에서 설정 불러오기"""
        try:
            with open(self._SETTINGS_PATH, "r", encoding="utf-8") as f:
                s = json.load(f)
            saved = s.get("source_hwp_dir", "")
            if saved and os.path.isdir(saved):
                self.source_hwp_dir.set(saved)
            # 선호도 필터 저장값 복원 (tk.Var 생성 전이므로 plain attr에 저장)
            self._saved_pref_filter_enabled = s.get("pref_filter_enabled", False)
            self._saved_pref_Good  = s.get("pref_Good",  True)
            self._saved_pref_Soso  = s.get("pref_Soso",  True)
            self._saved_pref_Bad   = s.get("pref_Bad",   True)
            self._saved_pref_scope = s.get("pref_scope", "mine")
            self._saved_pref_scope_expanded = s.get("pref_scope_expanded", False)
        except Exception:
            pass  # 파일 없으면 기본값 유지

    def _save_settings(self):
        """source_hwp_dir 등 설정을 settings.json 에 저장"""
        try:
            s = {}
            try:
                with open(self._SETTINGS_PATH, "r", encoding="utf-8") as f:
                    s = json.load(f)
            except Exception:
                pass
            s["source_hwp_dir"] = self.source_hwp_dir.get()
            # 선호도 필터 상태 저장
            if hasattr(self, 'var_pref_filter'):
                s["pref_filter_enabled"] = self.var_pref_filter.get()
            for pref_name in ("Good", "Soso", "Bad"):
                if hasattr(self, 'vars_pref') and pref_name in self.vars_pref:
                    s[f"pref_{pref_name}"] = self.vars_pref[pref_name].get()
            if hasattr(self, 'var_pref_scope'):
                s["pref_scope"] = self.var_pref_scope.get()
            with open(self._SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Settings] 저장 실패: {e}")

    def _find_source_hwp(self, filename, user_dir=None):
        """Helper to find HWP file in project dirs with performance optimization"""
        # [FIX] Prefer passed user_dir (Main Thread captured), fallback to getter (if called from main thread)
        # However, accessing .get() from background thread is unsafe.
        # So we trust user_dir if passed.
        
        if user_dir is None:
             # Fallback (Only safe if Main Thread)
             try:
                 user_dir = self.source_hwp_dir.get()
             except:
                 user_dir = None
        
        parent_dir = os.path.dirname(base_dir)

        # 1. Quick check for prioritized directories
        scan_dirs = []
        if user_dir and os.path.exists(user_dir):
            scan_dirs.append(user_dir)
            
        scan_dirs.extend([
            os.path.join(base_dir, "exercise"),
            os.path.join(parent_dir, "문제들"),
            base_dir
        ])
        
        for d in scan_dirs:
            if not os.path.exists(d): continue
            cand = os.path.join(d, filename)
            if os.path.exists(cand): return cand

        # 2. Recursive walk in user specified dir (High Priority)
        if user_dir and os.path.exists(user_dir):
            # self.log(f"🔍 '{filename}' 지정 폴더 탐색 중...") # Log unavailable in thread if not careful
            for root, dirs, files in os.walk(user_dir):
                if filename in files:
                    return os.path.join(root, filename)

        # 3. Recursive walk in workspace root
        for root, dirs, files in os.walk(base_dir):
            if filename in files:
                return os.path.join(root, filename)

        # 4. Recursive walk in parent folder (Deep search)
        # self.log(f"🔍 '{filename}' 상위 폴더 탐색 중...")
        for root, dirs, files in os.walk(parent_dir):
            if filename in files:
                return os.path.join(root, filename)
        return None

    def log_exam(self, message):
        """Logs to both terminal and the UI with status indicator"""
        print(f"[ExamEngine] {message}")
        self.log(f"[Exam] {message}")

    def log(self, message):
        """Thread-safe log. parser/스레드 어디서 호출되어도 메인 스레드로 마샬링."""
        timestamp = time.strftime('%H:%M:%S')
        line = f"[{timestamp}] {message}\n"

        def _do():
            try:
                self.log_widget.insert(tk.END, line)
                self.log_widget.see(tk.END)
            except Exception:
                pass

        try:
            self.root.after(0, _do)
        except Exception:
            # root가 destroyed인 경우 무시 (앱 종료 중)
            pass

    def _on_curriculum_change(self, event=None):
        """Update subject list based on curriculum choice"""
        if "과목명" not in self.entries:
            return
        curr = self.entries["교육과정"].get()
        subjects = self.curr_config.get("curriculums", {}).get(curr, {}).get("subjects", [])

        self.entries["과목명"]["values"] = subjects
        if subjects:
            self.entries["과목명"].set(subjects[0])
        else:
            self.entries["과목명"].set("")

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("HWP Files", "*.hwp")])
        if file_path:
            self.working_path = file_path
            self.working_mode = "file"
            self.folder_info.config(text=f"[단일 파일] {os.path.basename(file_path)}", fg=CLR_ACCENT)
            self.log(f"단일 파일 선택됨: {file_path}")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.working_path = folder
            self.working_mode = "folder"
            self.folder_info.config(text=f"[폴더 대규모] {folder}", fg=CLR_FG)
            self.log(f"대상 폴더 선택됨: {folder}")

    def start_scan(self):
        if not self.working_path:
            self.log("오류: 폴더 또는 파일을 먼저 선택해 주세요.")
            return

        # 인덱서에서 폼 값 수집 (소스별 db_key 매핑 포함)
        common_meta = self.current_indexer.collect_form_values(self.entries)
        # source는 schema field가 아니므로 현재 선택된 소스 타입을 직접 주입
        common_meta["source"] = self.current_source_type or ""

        required_key = self.current_indexer.get_required_db_key()
        if required_key and not common_meta.get(required_key):
            self.log(f"오류: 필수 항목을 입력해 주세요 ({required_key}).")
            return

        # [Duplicate Check Logic]
        # Check if exam exists in DB
        try:
            existing_files = self.db_engine.check_duplicate_exam(common_meta)
        except Exception as e:
            self.log(f"중복 체크 실패 (계속 진행): {e}")
            existing_files = []
        
        if existing_files:
            current_target_file = ""
            if self.working_mode == "file" and self.working_path:
                current_target_file = os.path.basename(self.working_path)
            
            # Scenario A: Same exam info, but different file -> BLOCK
            # Check if any existing file is DIFFERENT from current target
            # Caveat: If folder mode, we can't easily check 1-to-1 without iterating.
            # Simplified Policy: 
            # If "Force Update" is OFF, and record exists -> Warning or Block.
            # User request: "Different file name? Block." "Same file name? Update."
            
            is_same_file = False
            if self.working_mode == "file":
                 if current_target_file in existing_files:
                     is_same_file = True
            
            if not is_same_file and not self.force_update_var.get():
                # Block or Ask?
                # User wants BLOCK for different files if duplicate exam info.
                msg = "이미 동일한 시험 정보로 등록된 파일이 존재합니다.\n\n"
                msg += f"등록된 파일: {', '.join(existing_files[:3])}...\n"
                msg += "중복 등록을 방지하기 위해 작업을 중단합니다.\n"
                msg += "(기존 파일을 갱신하려면 '기존 데이터 덮어쓰기'를 체크하거나, 같은 파일명을 사용하세요.)"
                messagebox.showerror("중복 등록 차단", msg)
                return
            
            if is_same_file:
                # Notify Update
                if not messagebox.askyesno("갱신 확인", f"이미 등록된 파일({current_target_file})입니다.\n내용을 갱신하시겠습니까?"):
                    return
                # Auto-enable force update for this run (logic inside parser handles force_reindex)
                # We interpret "Same file" as valid update.
            else:
                # Force Update is ON, but file name different?
                # This might mean user wants to FORCE replace or add.
                # If Force Update var is checked, we proceed.
                pass

            
        self.start_btn.config(state="disabled", text="가공 중...", bg="#444444")
        self.cancel_btn.config(state="normal", bg="#c62828")
        self._scan_cancel.clear()
        self.status_label.config(text="데이터 추출 중...", fg="#ffaa00")
        try:
            self.progress.start(15)  # 진행 애니메이션 시작 (15ms 간격)
        except Exception:
            pass

        # 위젯 접근은 모두 메인 스레드로 마샬링 (tkinter thread-safety)
        force_reindex_val = self.force_update_var.get()
        stealth_val = self.stealth_var.get()

        # 취소 가능한 progress_callback — 사용자가 취소 누르면 예외로 루프 탈출
        class _ScanCancelled(Exception):
            pass
        def _cancellable_log(msg):
            if self._scan_cancel.is_set():
                raise _ScanCancelled("사용자가 취소함")
            self.log(msg)

        def run():
            try:
                if self.working_mode == "folder":
                    self.parser.scan_folder(
                        self.working_path,
                        common_meta,
                        max_workers=1,
                        visible=True,
                        force_reindex=force_reindex_val,
                        progress_callback=_cancellable_log,
                        stealth_mode=stealth_val,
                        indexer=self.current_indexer
                    )
                else:
                    self.parser.scan_file(
                        self.working_path,
                        common_meta,
                        visible=True,
                        progress_callback=_cancellable_log,
                        stealth_mode=stealth_val,
                        indexer=self.current_indexer
                    )
                self.root.after(0, lambda: self.status_label.config(text="가공 완료", fg="#00ff88"))
                self.root.after(0, self._update_stats)
                self.root.after(0, self.load_indexed_problems)
            except _ScanCancelled:
                self.log("⚠ 사용자가 작업을 취소했습니다.")
                self.root.after(0, lambda: self.status_label.config(text="취소됨", fg="#ffaa00"))
                self.root.after(0, self._update_stats)
            except Exception as e:
                err_msg = str(e)
                self.log(f"치명적 오류 발생: {err_msg}")
                self.root.after(0, lambda: self.status_label.config(text="실패", fg="#ff4d4d"))
            finally:
                self.root.after(0, lambda: self.start_btn.config(state="normal", text="엔진 가동 시작", bg=CLR_ACCENT))
                self.root.after(0, lambda: self.cancel_btn.config(state="disabled", bg="#666666"))
                def _stop_progress():
                    try: self.progress.stop()
                    except Exception: pass
                self.root.after(0, _stop_progress)

        threading.Thread(target=run, daemon=True).start()

    def cancel_scan(self):
        """진행 중인 가공 작업 취소 요청 — 다음 progress_callback 시점에 반영."""
        if not self._scan_cancel.is_set():
            self._scan_cancel.set()
            try:
                self.cancel_btn.config(state="disabled", text="취소 중...", bg="#666666")
                self.status_label.config(text="취소 중...", fg="#ffaa00")
                self.log("⏹ 취소 요청됨 — 현재 처리 중인 파일 후 중단합니다...")
            except Exception:
                pass
            # 취소 라벨/상태 일정 시간 후 원복은 finally 에서 처리되지만,
            # 텍스트만 원복해 둔다.
            try:
                self.root.after(800, lambda: self.cancel_btn.config(text="취소"))
            except Exception:
                pass

    def _update_stats(self):
        """Calculates stats from registration_log.json and updates UI"""
        log_path = os.path.join(base_dir, "registration_log.json")

        try:
            with open(log_path, "r", encoding="utf-8") as f:
                logs = json.load(f)
            
            total_files = 0
            total_problems = 0
            total_errors = 0
            
            for entry in logs.values():
                if entry.get("status") == "done":
                    total_files += 1
                    total_problems += entry.get("problem_count", 0)
                else:
                    total_errors += 1
            
            self.stats_labels["files"].config(text=str(total_files))
            self.stats_labels["problems"].config(text=str(total_problems))
            self.stats_labels["errors"].config(text=str(total_errors))
        except Exception as e:
            print(f"Error updating stats: {e}")

    def load_indexed_problems(self):
        """Refreshes the Management tab after indexing so new data is immediately visible."""
        try:
            # If the management tab has a search/refresh function, call it
            if hasattr(self, '_mgmt_search'):
                self._mgmt_search()
            elif hasattr(self, '_refresh_mgmt'):
                self._refresh_mgmt()
            self.log("[UI] 문제 관리 탭 새로고침 완료.")
        except Exception as e:
            print(f"[load_indexed_problems] 새로고침 실패: {e}")

    def _build_random_tab(self):
        """Builds Step 1 of Random Extraction: Unit Selection Tree - Surian Match"""
        # Clear existing content if wrapping back
        if hasattr(self, 'random_container') and self.random_container.winfo_exists():
            for widget in self.random_container.winfo_children():
                widget.destroy()
        else:
            self.random_container = tk.Frame(self.tab_random, bg="white", padx=0, pady=0) # Surian style is white-based
            self.random_container.pack(fill="both", expand=True)

        # 1. Header (Title like Surian) - WITH BUTTONS
        header_title = tk.Frame(self.random_container, bg="white", pady=20, padx=30)
        header_title.pack(fill="x")
        
        # Left: Title
        tk.Label(header_title, text="랜덤출제(단원선택)", font=("Segoe UI", 18, "bold"), bg="white", fg="#333333").pack(side="left")
        
        # Right: Buttons (Next, Close)
        header_buttons = tk.Frame(header_title, bg="white")
        header_buttons.pack(side="right")
        
        # Close Button (Gray/White simple) - Moves to Main Screen (Tab 0)
        tk.Button(header_buttons, text="닫기", command=self._close_random_tab,
                  bg="#f5f5f5", fg="#333333", font=FONT_MAIN, relief="flat", padx=15, pady=5).pack(side="right", padx=(10, 0))

        # Next Button (Blue/White simple) - Moves to Step 2
        tk.Button(header_buttons, text="다음", command=self._go_to_step_2,
                  bg="#1976d2", fg="white", font=FONT_BOLD, relief="flat", padx=20, pady=5).pack(side="right")
        
        # 2. (REMOVED) Course Selection Bar - Only High School supported

        # 3. Instruction Bar (Subtle Gray Line)
        # instr_bar = tk.Frame(self.random_container, bg="#f5f5f5", pady=10)
        # instr_bar.pack(fill="x")
        # tk.Label(instr_bar, text="원하는 단원을 체크하세요~", font=FONT_MAIN, bg="#f5f5f5", fg="#888888").pack()

        # 4. Main Tree View
        # Description Label
        tk.Label(self.random_container, text="원하는 단원을 체크하세요~", 
                 font=("Pretendard", 12), bg="#f5f5f5", fg="#666666").pack(fill="x", pady=5) # Reduced pady

        # Use a specific style for Surian tree
        style = ttk.Style()
        style.configure("Surian.Treeview", background="white", foreground="#333333", fieldbackground="white", rowheight=50) # Increased rowheight
        
        # Treeview (Hierarchical Unit Selection)
        tree_frame = tk.Frame(self.random_container, bg="white", bd=1, relief="solid")
        tree_frame.pack(fill="both", expand=True, pady=5)
        
        self.unit_tree = ttk.Treeview(tree_frame, columns=("count",), show="tree headings", selectmode="extended", style="Surian.Treeview")
        self.unit_tree.heading("#0", text="원하는 단원을 체크하세요~", anchor="w")
        self.unit_tree.heading("count", text="문항수", anchor="center")
        self.unit_tree.column("#0", stretch=True)
        self.unit_tree.column("count", width=80, anchor="center")
        
        # Scrollbar
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.unit_tree.yview)
        self.unit_tree.configure(yscrollcommand=yscroll.set)
        
        self.unit_tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # Initial Refresh
        self._refresh_unit_tree()

        # Selection Logic
        # Double click removed as per user request (One-click logic implemented in _on_tree_click)
        self.unit_tree.bind("<Button-1>", self._on_tree_click)

        # Footer Removed as per request (Buttons moved to top right)

    def _toggle_pref_scope(self):
        """내 것만/남의 것도 영역 펼침/접기"""
        self._pref_scope_expanded = not getattr(self, '_pref_scope_expanded', False)
        if self._pref_scope_expanded:
            self.pref_scope_frame.pack(fill="x", pady=(0, 3))
            self._btn_pref_expand.configure(text="▲")
        else:
            self.pref_scope_frame.pack_forget()
            self._btn_pref_expand.configure(text="▼")
        self._save_pref_settings()

    def _on_pref_filter_toggle(self):
        """문항선호도 마스터 체크박스 ON/OFF → 하위 위젯 활성화 + 저장 + 갱신"""
        is_on = getattr(self, 'var_pref_filter', None) and self.var_pref_filter.get()
        state = "normal" if is_on else "disabled"
        # Good/Soso/Bad 체크박스
        for cb in getattr(self, '_pref_cb_widgets', {}).values():
            try:
                cb.configure(state=state)
            except Exception:
                pass
        # 내 것만 / 남의 것도 라디오
        for rb in getattr(self, '_pref_scope_widgets', []):
            try:
                rb.configure(state=state)
            except Exception:
                pass
        # ▼ 펼치기 버튼
        try:
            self._btn_pref_expand.configure(state=state)
        except Exception:
            pass
        self._save_pref_settings()
        self._on_any_filter_change()

    def _on_pref_cb_change(self):
        """선호도 체크박스·스코프 변경 → 저장 + 갱신"""
        self._save_pref_settings()
        self._on_any_filter_change()

    def _save_pref_settings(self):
        """현재 선호도 필터 상태를 settings.json 에 저장"""
        try:
            s = {}
            try:
                with open(self._SETTINGS_PATH, "r", encoding="utf-8") as fp:
                    s = json.load(fp)
            except Exception:
                pass
            if hasattr(self, 'var_pref_filter'):
                s["pref_filter_enabled"] = self.var_pref_filter.get()
            for pref_name in ("Good", "Soso", "Bad"):
                if hasattr(self, 'vars_pref') and pref_name in self.vars_pref:
                    s[f"pref_{pref_name}"] = self.vars_pref[pref_name].get()
            if hasattr(self, 'var_pref_scope'):
                s["pref_scope"] = self.var_pref_scope.get()
            s["pref_scope_expanded"] = getattr(self, '_pref_scope_expanded', False)
            with open(self._SETTINGS_PATH, "w", encoding="utf-8") as fp:
                json.dump(s, fp, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Settings] 선호도 저장 실패: {e}")

    def _get_pref_filter_ids(self):
        """활성화된 선호도 필터에 해당하는 problem_id 집합 반환.
        필터 비활성 → None (=적용 안 함).
        활성이지만 선택된 게 없음 → 빈 set (=0건).

        핵심: 미설정 문항은 'Soso'로 취급.
        'Soso'가 선택된 경우 candidate_ids(전체 ID)를 넘겨
        get_problem_ids_by_preference의 "미설정=Soso" 분기가 실행되도록 한다.
        """
        if not getattr(self, 'var_pref_filter', None) or not self.var_pref_filter.get():
            return None
        selected_prefs = [p for p, v in self.vars_pref.items() if v.get()]
        if not selected_prefs:
            return set()
        scope = self.var_pref_scope.get()
        if scope == "mine":
            user_ids = [self.current_user_id]
        else:   # "all"
            user_ids = self.db_engine.get_all_preference_user_ids()
            if self.current_user_id not in user_ids:
                user_ids.append(self.current_user_id)
        # 'Soso'가 선택된 경우: 미설정 문항도 Soso로 포함해야 하므로
        # 전체 problem ID를 candidate_ids로 전달
        if 'Soso' in selected_prefs:
            candidate_ids = self.db_engine.get_all_problem_ids()
        else:
            candidate_ids = None  # 명시적으로 등록된 것만 (Good/Bad 전용)
        return self.db_engine.get_problem_ids_by_preference(
            user_ids, selected_prefs, candidate_ids=candidate_ids
        )

    def _on_source_filter_change(self):
        """소스 체크박스 변경 시 → 중앙 핸들러 위임"""
        self._on_any_filter_change()

    def _on_any_filter_change(self):
        """모든 필터 변경의 단일 진입점 — 트리와 리스트를 항상 함께 갱신."""
        self._refresh_unit_tree()
        self._refresh_step_2_list()

    def _build_global_filters(self) -> dict:
        """소스·년도·학교·정답률 등 전역 필터를 하나의 dict로 반환.
        트리 쿼리와 리스트 쿼리가 동일한 필터를 공유하기 위한 단일 출처."""
        filters = {}

        # 소스 필터
        # None = 소스 필터 OFF(전체), [] = ON이지만 아무것도 선택 안 됨(결과 없음)
        src_filter = self._get_active_sources()
        if src_filter is None:
            pass  # 필터 없음 → 전체
        elif len(src_filter) == 0:
            filters["source"] = "___NO_SOURCE___"  # DB에 존재하지 않는 값 → 결과 0건
        else:
            filters["source"] = {"in": src_filter}

        # 학교 필터
        if hasattr(self, 'selected_schools') and self.selected_schools:
            filters["school"] = {"in": self.selected_schools}

        # 년도 필터
        if getattr(self, 'var_year_filter_on', None) and self.var_year_filter_on.get():
            if hasattr(self, 'selected_years') and self.selected_years:
                mode = self.var_year_mode.get()
                if mode == "include":
                    filters["year"] = {"in": self.selected_years}
                else:
                    filters["year"] = {"not_in": self.selected_years}

        # 정답률 필터
        rate_ids = getattr(self, 'rate_filter_ids', None)
        if rate_ids is not None:
            filters["_rate_ids"] = rate_ids  # _query_count_for_row에서 처리

        # 모의고사 브랜드 필터
        if hasattr(self, 'selected_brands') and self.selected_brands:
            brand_ids = self.db_engine.get_ids_by_mock_brands(self.selected_brands)
            filters["_brand_ids"] = brand_ids  # 빈 리스트도 유효 (결과 0건)

        # 문항번호 필터
        if getattr(self, 'var_pnum_on', None) and self.var_pnum_on.get():
            entry = getattr(self, 'entry_pnum', None)
            try:
                alive = entry is not None and entry.winfo_exists()
            except Exception:
                alive = False
            if alive:
                text = entry.get().strip()
                nums = []
                for part in text.replace(',', ' ').split():
                    try:
                        n = int(part)
                        if 1 <= n <= 9999:
                            nums.append(n)
                    except ValueError:
                        pass
                if nums:
                    filters["problem_number"] = {"in": nums}
                else:
                    # 필터 ON + 입력 없음 → silent ignore 대신 0 매칭 강제
                    # 사용자가 "필터 켰는데 왜 다 나오지?" 헷갈리지 않도록
                    filters["problem_number"] = {"in": [-1]}

        return filters

    def _get_active_sources(self):
        """소스 필터 ON + 개별 선택된 소스 목록 반환. OFF면 None(전체).
        체크된 소스가 없으면 [] 반환 → 아무것도 안 뜸."""
        if not hasattr(self, 'var_source_filter_on') or not self.var_source_filter_on.get():
            return None  # 소스 필터 사용 안 함 → 전체
        if not hasattr(self, 'var_sources'):
            return None
        checked = [k for k, v in self.var_sources.items() if v.get()]
        return checked  # 빈 리스트도 그대로 반환 → 아무 소스도 선택 안 됨 = 결과 없음

    def _compute_unit_counts(self):
        """unit_code 별 문제 수를 단 1회 GROUP BY 쿼리로 일괄 계산.
        _refresh_unit_tree 의 N+1 query_counts 호출을 단일 쿼리로 대체.
        Firestore engine 등 GROUP BY 미지원 백엔드는 None 반환하여 fallback 유도.
        """
        import sqlite3
        db_path = getattr(self.db_engine, "db_path", None)
        if not db_path:
            return None  # SQLite 백엔드 아님 → fallback to per-unit query

        q = self._build_global_filters() or {}
        q.pop("_rate_ids", None)
        q.pop("unit_code", None)  # 우리는 unit_code 별로 GROUP BY 할 거라 제거
        brand_ids = q.pop("_brand_ids", None)

        conds, params = [], []
        for k, v in q.items():
            if v is None or v == "":
                continue
            if isinstance(v, list):
                if not v:
                    continue
                conds.append(f"{k} IN ({','.join(['?'] * len(v))})")
                params.extend(v)
            elif isinstance(v, dict):
                op_handlers = {
                    "eq": "=", "ne": "!=", "gt": ">", "gte": ">=",
                    "lt": "<", "lte": "<=", "like": "LIKE",
                }
                for op, val in v.items():
                    if op in op_handlers:
                        conds.append(f"{k} {op_handlers[op]} ?")
                        params.append(val)
                    elif op == "in":
                        if not val: continue
                        conds.append(f"{k} IN ({','.join(['?'] * len(val))})")
                        params.extend(val)
                    elif op == "not_in":
                        if not val: continue
                        conds.append(f"{k} NOT IN ({','.join(['?'] * len(val))})")
                        params.extend(val)
            else:
                conds.append(f"{k} = ?")
                params.append(v)

        if brand_ids is not None:
            if not brand_ids:
                return {}  # 명시적으로 비었으면 전부 0
            conds.append(f"id IN ({','.join(['?'] * len(brand_ids))})")
            params.extend(brand_ids)

        conds.append("is_excluded = 0")

        sql = "SELECT unit_code, COUNT(*) FROM problems WHERE " + " AND ".join(conds) + " GROUP BY unit_code"
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(sql, params)
            counts = {row[0] or "": row[1] for row in cur.fetchall()}
            conn.close()
            return counts
        except Exception as e:
            print(f"[TreeRefresh] _compute_unit_counts 실패: {e}")
            return None

    def _refresh_unit_tree(self):
        """Populates the tree based on current data and hierarchy - Surian Style"""
        # 위젯이 아직 생성되지 않았거나 이미 파괴된 경우 무시
        if not hasattr(self, 'unit_tree') or not self.unit_tree.winfo_exists():
            return
        # Clear existing
        for item in self.unit_tree.get_children():
            self.unit_tree.delete(item)
        # ── unit_code 별 카운트를 1회 GROUP BY 로 미리 계산 (N+1 제거) ──
        unit_counts = self._compute_unit_counts()
        
        # Fixed Category Node (High School Only) - Open by default
        cat_node = self.unit_tree.insert("", "end", text="고등수학", open=True, tags=("category",))

        # 2022개정교육과정 과목만 표시
        for version in ["2022"]:
            if version not in self.unit_hierarchy: continue
            
            for subj_data in self.unit_hierarchy[version]:
                subj_name = subj_data["subject"]
                
                # 과목 레벨 (2단계) - 과목명 뒤에 개정 버전 표시
                display_subj = f"{subj_name} ({version}개정)"
                # Start collapsed (open=False) - No checkbox for subject level (just dropdown)
                subj_node = self.unit_tree.insert(cat_node, "end", text=f" {display_subj}", open=False, tags=("subject",))
                
                total_subj_count = 0
                for large in subj_data.get("large_units", []):
                    # 대단원 레벨 (3단계)
                    large_name = large["name"]
                    large_code = large["code"]
                    large_node = self.unit_tree.insert(subj_node, "end", text=f"☐ {large_name}", open=False, tags=("large", large_code, version, "unchecked"))
                    
                    total_large_count = 0
                    for medium in large.get("medium_units", []):
                        # 중단원 레벨 (4단계)
                        m_name = medium["name"]
                        m_code = medium["code"]

                        # 2026-05-23: 2015/2022 코드 체계 통합 → 변환 불필요
                        target_code = m_code
                        if unit_counts is not None:
                            count = unit_counts.get(target_code, 0)
                        else:
                            # fallback: per-unit query (Firestore 등 GROUP BY 미지원 백엔드)
                            try:
                                q = self._build_global_filters()
                                q["unit_code"] = target_code
                                q.pop("_rate_ids", None)
                                brand_ids = q.pop("_brand_ids", None)
                                if brand_ids is not None:
                                    q["id"] = {"in": brand_ids} if brand_ids else "NONE"
                                count = self.db_engine.query_counts(q)
                            except Exception as e:
                                print(f"[TreeRefresh] {m_code} 카운트 오류: {e}")
                                count = 0
                        self.unit_tree.insert(large_node, "end", text=f"☐ {m_name}", values=(f"{count:,}",), tags=("medium", m_code, version, "unchecked"))
                        total_large_count += count
                    
                    self.unit_tree.item(large_node, values=(f"{total_large_count:,}",))
                    total_subj_count += total_large_count
                
                self.unit_tree.item(subj_node, values=(f"{total_subj_count:,}",))

        # ── 중등수학 카테고리 ─────────────────────────────────────
        if "middle" in self.unit_hierarchy:
            mid_cat_node = self.unit_tree.insert("", "end", text="중등수학", open=True, tags=("category",))
            for subj_data in self.unit_hierarchy["middle"]:
                subj_name = subj_data["subject"]
                subj_node = self.unit_tree.insert(mid_cat_node, "end", text=f" {subj_name}", open=False, tags=("subject",))
                total_subj_count = 0
                for large in subj_data.get("large_units", []):
                    large_name = large["name"]
                    large_code = large["code"]
                    large_node = self.unit_tree.insert(subj_node, "end", text=f"☐ {large_name}", open=False, tags=("large", large_code, "middle", "unchecked"))
                    total_large_count = 0
                    for medium in large.get("medium_units", []):
                        m_name = medium["name"]
                        m_code = medium["code"]
                        if unit_counts is not None:
                            count = unit_counts.get(m_code, 0)
                        else:
                            try:
                                q = self._build_global_filters()
                                q["unit_code"] = m_code
                                q.pop("_rate_ids", None)
                                brand_ids = q.pop("_brand_ids", None)
                                if brand_ids is not None:
                                    q["id"] = {"in": brand_ids} if brand_ids else "NONE"
                                count = self.db_engine.query_counts(q)
                            except Exception as e:
                                print(f"[TreeRefresh] {m_code} 카운트 오류: {e}")
                                count = 0
                        self.unit_tree.insert(large_node, "end", text=f"☐ {m_name}", values=(f"{count:,}",), tags=("medium", m_code, "middle", "unchecked"))
                        total_large_count += count
                    self.unit_tree.item(large_node, values=(f"{total_large_count:,}",))
                    total_subj_count += total_large_count
                self.unit_tree.item(subj_node, values=(f"{total_subj_count:,}",))

        # Tag Styles - Matching Surian Style
        self.unit_tree.tag_configure("category", foreground="#1976d2", font=FONT_BOLD)
        self.unit_tree.tag_configure("subject", foreground="#333333")
        self.unit_tree.tag_configure("large", foreground="#333333")
        self.unit_tree.tag_configure("medium", foreground="#555555")

        # Color Change on selection (Blue style)
        self.unit_tree.tag_configure("checked", foreground="#1976d2", font=FONT_BOLD) # Blue + Bold when checked
        self.unit_tree.tag_configure("unchecked", foreground="#333333")

    def _on_tree_click(self, event):
        """Handle single click: Separate Checkbox vs Text logic"""
        region = self.unit_tree.identify("region", event.x, event.y)
        if region == "tree":
            item_id = self.unit_tree.identify_row(event.y)
            if not item_id:
                return

            tags = self.unit_tree.item(item_id, "tags")
            
            # 1. Category/Subject: Always toggle expand/collapse (No checkbox)
            if "category" in tags or "subject" in tags:
                is_open = self.unit_tree.item(item_id, "open")
                self.unit_tree.item(item_id, open=not is_open)
                return "break"

            # 2. Checkable Items (Large/Medium):
            # Calculate indentation to find checkbox position approximation
            # Treeview indent is usually 20px per level
            # Level 0 (Root/Category): 20px
            # Level 1 (Subject): 40px
            # Level 2 (Large): 60px
            # Level 3 (Medium): 80px
            
            # Simple heuristic: Checkbox is at the start of the text
            # We can't get exact text bounding box easily in Tkinter Treeview
            # So we use a rough X coordinate check relative to the item's column start?
            # Actually, identify_row gives us the item. 
            # Let's try a simpler approach: 
            # If x is within a certain range relative to indentation, it's a checkbox.
            
            # However, simpler UX requested: "Click Box -> Check", "Click Text -> Expand"
            # Since we can't easily detect "Box" vs "Text" by pixel without complex math,
            # Let's use the column detection. But tree column #0 contains everything.
            
            # Implementation Strategy:
            # - Since we added a space or symbol "☐ " at the start.
            # - Tkinter doesn't give char index on click for Treeview.
            
            # ALTERNATIVE: Use the request literal interpretation.
            # "Box needs to be clicked": Implicitly means left-most part.
            # "Text click -> Expand": The rest.
            
            # Let's use a widely working heuristic for "Checkbox Area"
            # Base indent = 20 (root) + 20 per nesting
            # We can count parents to find nesting level.
            parent = self.unit_tree.parent(item_id)
            level = 0
            while parent:
                level += 1
                parent = self.unit_tree.parent(parent)
            
            # Approx X start of content (Indent)
            indent_width = 20
            content_start_x = level * indent_width
            
            # Checkbox width approx 20px
            checkbox_end_x = content_start_x + 25 # Allow some margin
            
            # If click is within the checkbox area
            if event.x <= checkbox_end_x + 15: # slightly wider hit area for box
                 self._toggle_check(item_id)
                 return "break"
            else:
                # Text area -> Toggle Expand/Collapse
                # For Large units (Level 2), user wants "Click text -> Open submenu"
                if "large" in tags:
                     is_open = self.unit_tree.item(item_id, "open")
                     self.unit_tree.item(item_id, open=not is_open)
                     return "break"
                
                # For Medium units (Level 3), text click does nothing (or maybe selects row?)
                # User said "Click box to check", implying strict separation.
                # So we do nothing for text click on medium units.
                if "medium" in tags:
                     pass 
                
                return "break"

    def _toggle_check(self, item_id):
        """Toggles the checkbox state of an item and its children using Unicode symbols"""
        tags = list(self.unit_tree.item(item_id, "tags"))
        current_text = self.unit_tree.item(item_id, "text")
        
        # Determine new state
        if "unchecked" in tags:
            new_state = "checked"
            new_text = current_text.replace("☐", "☑", 1)
            if "unchecked" in tags: tags.remove("unchecked")
            if "checked" not in tags: tags.append("checked")
            
            # 대단원 체크 → 자식 중단원 모두 해제
            if "large" in tags:
                for child in self.unit_tree.get_children(item_id):
                    self._set_check_state(child, "unchecked")
            # 중단원 체크 → 부모 대단원 해제
            elif "medium" in tags:
                parent_id = self.unit_tree.parent(item_id)
                if parent_id:
                    self._set_check_state(parent_id, "unchecked")
                    
        else:
            new_state = "unchecked"
            new_text = current_text.replace("☑", "☐", 1)
            if "checked" in tags: tags.remove("checked")
            if "unchecked" not in tags: tags.append("unchecked")
            
        # Update current item
        self.unit_tree.item(item_id, text=new_text, tags=tuple(tags))
        
        # Note: Recursive update removed to treat Large Units as single entities as per user request.

    def _set_check_state(self, item_id, state):
        """Force sets the check state for recursion using Unicode symbols"""
        tags = list(self.unit_tree.item(item_id, "tags"))
        current_text = self.unit_tree.item(item_id, "text")
        
        changed = False
        if state == "checked":
            if "unchecked" in tags:
                new_text = current_text.replace("☐", "☑", 1)
                tags.remove("unchecked")
                tags.append("checked")
                self.unit_tree.item(item_id, text=new_text, tags=tuple(tags))
                changed = True
        else:
            if "checked" in tags:
                new_text = current_text.replace("☑", "☐", 1)
                tags.remove("checked")
                tags.append("unchecked")
                self.unit_tree.item(item_id, text=new_text, tags=tuple(tags))
                changed = True
        
        return changed

    def _go_to_step_2(self):
        """Transitions to Step 2: Quantity Input & Advanced Filters"""
        try:
            print("Debug: _go_to_step_2 called")
            self.next_step3_mode = "new"

            selected_items = []
            for item in self.unit_tree.get_children():
                self._collect_selected_units(item, selected_items)
            
            if not selected_items:
                messagebox.showwarning("단원 선택", "출제할 단원을 최소 하나 이상 선택해주세요.")
                return

            print(f"Debug: Selected items count: {len(selected_items)}")

            # Store selected units as dictionaries with code and version
            self.selected_units_data = []
            for i in selected_items:
                tags = self.unit_tree.item(i, "tags")
                print(f"Debug: Item {i} tags: {tags}")
                
                # Expected tags: (type, code, version, status)
                
                if "large" in tags:
                    # Tags: ("large", code, version, status)
                    if len(tags) >= 4:
                        self.selected_units_data.append({"code": tags[1], "version": tags[2], "type": "large"})
                    else:
                        print(f"Warning: Large unit tags incomplete: {tags}")
                        
                elif "medium" in tags:
                    if len(tags) >= 4:
                         self.selected_units_data.append({"code": tags[1], "version": tags[2], "type": "medium"})
                    else:
                        print(f"Warning: Medium unit tags incomplete: {tags}")

            print(f"Debug: selected_units_data populated: {len(self.selected_units_data)}")
            
            # Clear container and build Step 2
            for widget in self.random_container.winfo_children():
                widget.destroy()
            
            self._build_step_2_ui()
            
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            print(f"Error in _go_to_step_2: {err_msg}")
            messagebox.showerror("오류 발생", f"Step 2 이동 중 오류가 발생했습니다:\n{e}\n\n{err_msg}")

    def _close_random_tab(self):
        """Closes the random tab/returns to home screen"""
        if self.notebook:
            self.notebook.select(self.tab_home)

    def _reset_detail_filters(self):
        """상세 필터 상태 초기화 (출제 화면 진입/이탈 시 호출)"""
        if hasattr(self, 'selected_schools'):
            self.selected_schools.clear()
        if hasattr(self, 'selected_brands'):
            self.selected_brands.clear()
        if hasattr(self, 'var_school_option_on'):
            self.var_school_option_on.set(False)
        if hasattr(self, 'var_brand_option_on'):
            self.var_brand_option_on.set(False)
        if hasattr(self, 'var_pnum_on'):
            self.var_pnum_on.set(False)

    def _save_step2_filter_state(self):
        """Step 2 필터 전체 상태 백업 (랜덤추가 버튼 클릭 전 호출)"""
        backup = {}
        # 소스 필터
        if hasattr(self, 'var_source_filter_on'):
            backup['source_filter_on'] = self.var_source_filter_on.get()
        if hasattr(self, 'var_sources'):
            backup['sources'] = {k: v.get() for k, v in self.var_sources.items()}
        # 수준별 보기
        if hasattr(self, 'var_view_level'):
            backup['view_level'] = self.var_view_level.get()
        if hasattr(self, 'vars_diff'):
            backup['diffs'] = {k: v.get() for k, v in self.vars_diff.items()}
        # 정답률
        if hasattr(self, 'var_use_rate'):
            backup['use_rate'] = self.var_use_rate.get()
        try: backup['rate_min'] = self.entry_rate_min.get()
        except: backup['rate_min'] = '0'
        try: backup['rate_max'] = self.entry_rate_max.get()
        except: backup['rate_max'] = '100'
        if hasattr(self, 'rate_filter_ids'):
            backup['rate_filter_ids'] = self.rate_filter_ids
        # 형식별 보기
        if hasattr(self, 'var_view_type'):
            backup['view_type'] = self.var_view_type.get()
        if hasattr(self, 'vars_type'):
            backup['types'] = {k: v.get() for k, v in self.vars_type.items()}
        # 년도 필터
        if hasattr(self, 'var_year_filter_on'):
            backup['year_filter_on'] = self.var_year_filter_on.get()
        if hasattr(self, 'var_year_mode'):
            backup['year_mode'] = self.var_year_mode.get()
        backup['selected_years'] = list(getattr(self, 'selected_years', []))
        # 출제 제외 옵션
        if hasattr(self, 'var_include_excluded'):
            backup['include_excluded'] = self.var_include_excluded.get()
        # 총 문항 수
        try: backup['total_qty'] = self.entry_total_qty.get()
        except: backup['total_qty'] = '30'
        # 문항 배분 (alloc_entries)
        if hasattr(self, 'alloc_entries'):
            backup['alloc'] = {}
            for k, entry in self.alloc_entries.items():
                try: backup['alloc'][k] = entry.get()
                except: pass
        self._step2_filter_backup = backup

    def _restore_step2_filter_state(self):
        """Step 2 필터 전체 상태 복원 (랜덤추가 후 _build_step_2_ui 완료 뒤 호출)"""
        backup = getattr(self, '_step2_filter_backup', None)
        if not backup:
            return

        # ── 1. 변수값 직접 설정 (콜백 트리거 없이) ──────────────────
        if 'source_filter_on' in backup and hasattr(self, 'var_source_filter_on'):
            self.var_source_filter_on.set(backup['source_filter_on'])
        if 'sources' in backup and hasattr(self, 'var_sources'):
            for k, v in backup['sources'].items():
                if k in self.var_sources:
                    self.var_sources[k].set(v)
        if 'view_level' in backup and hasattr(self, 'var_view_level'):
            self.var_view_level.set(backup['view_level'])
        if 'diffs' in backup and hasattr(self, 'vars_diff'):
            for k, v in backup['diffs'].items():
                if k in self.vars_diff:
                    self.vars_diff[k].set(v)
        if 'use_rate' in backup and hasattr(self, 'var_use_rate'):
            self.var_use_rate.set(backup['use_rate'])
        if 'rate_filter_ids' in backup:
            self.rate_filter_ids = backup['rate_filter_ids']
        if 'view_type' in backup and hasattr(self, 'var_view_type'):
            self.var_view_type.set(backup['view_type'])
        if 'types' in backup and hasattr(self, 'vars_type'):
            for k, v in backup['types'].items():
                if k in self.vars_type:
                    self.vars_type[k].set(v)
        if 'year_filter_on' in backup and hasattr(self, 'var_year_filter_on'):
            self.var_year_filter_on.set(backup['year_filter_on'])
        if 'year_mode' in backup and hasattr(self, 'var_year_mode'):
            self.var_year_mode.set(backup['year_mode'])
        # selected_years 복원 (year_filter_on 상태 무관하게 보존)
        self.selected_years = list(backup.get('selected_years', []))
        if hasattr(self, '_refresh_year_tags'):
            self._refresh_year_tags()
        if 'include_excluded' in backup and hasattr(self, 'var_include_excluded'):
            self.var_include_excluded.set(backup['include_excluded'])

        # ── 2. 총 문항 수 복원 ───────────────────────────────────────
        if 'total_qty' in backup and hasattr(self, 'entry_total_qty'):
            try:
                self.entry_total_qty.delete(0, 'end')
                self.entry_total_qty.insert(0, backup['total_qty'])
            except: pass

        # ── 3. 복원된 필터로 목록 1회 재렌더링 (alloc_entries 재생성) ─
        self._refresh_step_2_list()

        # ── 4. alloc_entries 값 복원 (재렌더링 후 매칭 키에만 적용) ──
        if 'alloc' in backup and hasattr(self, 'alloc_entries'):
            for k, val in backup['alloc'].items():
                if k in self.alloc_entries:
                    try:
                        entry = self.alloc_entries[k]
                        entry.delete(0, 'end')
                        entry.insert(0, val)
                    except: pass

        # ── 5. 위젯 enable/disable 상태 갱신 (재렌더링 없이) ────────
        # 소스 필터 체크박스
        if hasattr(self, 'source_chk_widgets') and hasattr(self, 'var_source_filter_on'):
            state = "normal" if self.var_source_filter_on.get() else "disabled"
            for chk in self.source_chk_widgets:
                try: chk.config(state=state)
                except: pass
        # 수준별 보기 diff 체크박스
        if hasattr(self, 'diff_chk_widgets') and hasattr(self, 'var_view_level'):
            state = "normal" if self.var_view_level.get() else "disabled"
            for chk in self.diff_chk_widgets:
                try: chk.config(state=state)
                except: pass
        # 정답률 위젯
        if hasattr(self, 'var_use_rate') and hasattr(self, 'entry_rate_min'):
            use = self.var_use_rate.get()
            s = "normal" if use else "disabled"
            try:
                self.entry_rate_min.config(state=s)
                self.entry_rate_max.config(state=s)
                self.btn_rate_apply.config(state=s)
                if use:
                    self.entry_rate_min.delete(0, 'end')
                    self.entry_rate_min.insert(0, backup.get('rate_min', '0'))
                    self.entry_rate_max.delete(0, 'end')
                    self.entry_rate_max.insert(0, backup.get('rate_max', '100'))
            except: pass
        # 년도 필터 위젯
        if hasattr(self, 'var_year_filter_on') and hasattr(self, 'rb_year_exclude'):
            on = self.var_year_filter_on.get()
            s_rb  = "normal"   if on else "disabled"
            s_cb  = "readonly" if on else "disabled"
            s_btn = "normal"   if on else "disabled"
            try:
                self.rb_year_exclude.config(state=s_rb)
                self.rb_year_include.config(state=s_rb)
                self.cbo_year.config(state=s_cb)
                self.btn_year_add.config(state=s_btn)
            except: pass

    def _build_step_2_ui(self):
        """Builds Step 2: Detailed Options & Question Distribution (Surian Style High-Fidelity)"""
        # 상세 필터 초기화 (append 모드가 아닐 때만 — 랜덤추가 시 필터 보존)
        if getattr(self, 'next_step3_mode', 'new') != 'append':
            self._reset_detail_filters()

        # Clear container
        for widget in self.random_container.winfo_children():
            widget.destroy()

        # --- 1. Top Navigation Bar ---
        nav_bar = tk.Frame(self.random_container, bg="white", pady=10, padx=20)
        nav_bar.pack(fill="x")
        
        tk.Label(nav_bar, text="출제조건 지정 및 문항수 입력", font=("Segoe UI", 16, "bold"), bg="white", fg="#333333").pack(side="left")
        
        btn_frame = tk.Frame(nav_bar, bg="white")
        btn_frame.pack(side="right")

        tk.Button(btn_frame, text="닫기", command=self._close_random_tab,
                  bg="#f5f5f5", fg="#333333", font=FONT_MAIN, relief="flat", padx=15).pack(side="right", padx=(5, 0))
        
        tk.Button(btn_frame, text="이전", command=self._back_to_step_1,
                   bg="#f5f5f5", fg="#333333", font=FONT_MAIN, relief="flat", padx=15).pack(side="right", padx=(5, 0))
                   
        tk.Button(btn_frame, text="다음", command=self._go_to_step_3,
                  bg="#1976d2", fg="white", font=FONT_BOLD, relief="flat", padx=20).pack(side="right")

        # --- 2. Main Content (Paned) ---
        content_paned = tk.PanedWindow(self.random_container, orient="horizontal", bg="#dddddd", sashwidth=2)
        content_paned.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Left Panel (Table)
        self.left_panel = tk.Frame(content_paned, bg="white")
        content_paned.add(self.left_panel, minsize=600, stretch="always")
        
        # Right Panel (Options)
        self.right_panel = tk.Frame(content_paned, bg="#f9f9f9", width=380)
        content_paned.add(self.right_panel, stretch="never")
        
        self._build_right_panel_options()
        self._build_left_panel_table()

        # Initial Render (append 모드면 _restore_step2_filter_state에서 처리)
        if getattr(self, 'next_step3_mode', 'new') != 'append':
            self._refresh_step_2_list()

    def _build_right_panel_options(self):
        """Builds the control panel on the right"""
        # ── 스크롤 가능한 캔버스 래퍼 ──────────────────────────────
        rp_canvas = tk.Canvas(self.right_panel, bg="#f9f9f9", highlightthickness=0)
        rp_scrollbar = tk.Scrollbar(self.right_panel, orient="vertical", command=rp_canvas.yview)
        rp_canvas.configure(yscrollcommand=rp_scrollbar.set)
        rp_scrollbar.pack(side="right", fill="y")
        rp_canvas.pack(side="left", fill="both", expand=True)

        container = tk.Frame(rp_canvas, bg="#f9f9f9", padx=15, pady=15)
        container_id = rp_canvas.create_window((0, 0), window=container, anchor="nw")

        def _on_container_configure(event):
            rp_canvas.configure(scrollregion=rp_canvas.bbox("all"))
        container.bind("<Configure>", _on_container_configure)

        def _on_rp_canvas_configure(event):
            rp_canvas.itemconfig(container_id, width=event.width)
        rp_canvas.bind("<Configure>", _on_rp_canvas_configure)

        def _on_rp_mousewheel(event):
            rp_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        rp_canvas.bind("<Enter>", lambda e: rp_canvas.bind_all("<MouseWheel>", _on_rp_mousewheel))
        rp_canvas.bind("<Leave>", lambda e: rp_canvas.unbind_all("<MouseWheel>"))

        tk.Label(container, text="보기 및 필터 옵션", font=FONT_BOLD,
                 bg="#f9f9f9", fg="#1976d2", anchor="w").pack(fill="x", pady=(0, 8))

        def divider():
            tk.Frame(container, bg="#dddddd", height=1).pack(fill="x", pady=(0, 8))

        # ── 1. 소스 필터 ──────────────────────────────────────────────
        self.var_source_filter_on = tk.BooleanVar(value=True)
        src_header_row = tk.Frame(container, bg="#f9f9f9")
        src_header_row.pack(fill="x", pady=(0, 3))
        tk.Checkbutton(src_header_row, text="소스 필터", variable=self.var_source_filter_on,
                       font=("Segoe UI", 10, "bold"), bg="#f9f9f9",
                       command=self._on_source_filter_toggle).pack(side="left")
        tk.Button(src_header_row, text="전체해제", font=("Segoe UI", 8),
                  bg="#e0e0e0", relief="flat", padx=5, pady=1,
                  command=self._on_source_deselect_all).pack(side="left", padx=(8, 0))

        self.source_filter_body = tk.Frame(container, bg="#f9f9f9", padx=20)
        self.source_filter_body.pack(fill="x", pady=(0, 5))

        SOURCES_ROW1 = [
            ("내신기출A", "NAESIN_A"),
            ("내신기출B", "NAESIN_N"),
            ("수특",      "SUNEUNG_SPECIAL"),
            ("수완",      "SUNEUNG_COMPLETE"),
        ]
        SOURCES_ROW2 = [
            ("모의고사",  "MOCK_EXAM"),
        ]
        if not hasattr(self, 'var_sources'):
            self.var_sources = {}
        self.source_chk_widgets = []
        for row_sources in (SOURCES_ROW1, SOURCES_ROW2):
            src_row = tk.Frame(self.source_filter_body, bg="#f9f9f9")
            src_row.pack(anchor="w")
            for label, key in row_sources:
                if key not in self.var_sources:
                    self.var_sources[key] = tk.BooleanVar(value=True)
                chk = tk.Checkbutton(src_row, text=label, variable=self.var_sources[key],
                                      bg="#f9f9f9", fg="#333", font=("Segoe UI", 9),
                                      activebackground="#f9f9f9", state="normal",
                                      command=self._on_source_filter_change)
                chk.pack(side="left", padx=(0, 8))
                self.source_chk_widgets.append(chk)

        divider()

        # ── 2. 수준별 보기 (한 줄) ──────────────────────────────────────
        level_row = tk.Frame(container, bg="#f9f9f9")
        level_row.pack(fill="x", pady=(0, 3))
        self.var_view_level = tk.BooleanVar(value=False)
        tk.Checkbutton(level_row, text="수준별 보기", variable=self.var_view_level,
                       font=("Segoe UI", 10, "bold"), bg="#f9f9f9",
                       command=self._on_level_toggle).pack(side="left")
        self.vars_diff = {}
        self.diff_chk_widgets = []
        for d_code, d_name in [("A", "최상"), ("B", "상"), ("C", "중"), ("D", "하")]:
            var = tk.BooleanVar(value=True)
            self.vars_diff[d_code] = var
            chk = tk.Checkbutton(level_row, text=d_name, variable=var, bg="#f9f9f9",
                                 state="disabled",
                                 command=self._on_any_filter_change)
            chk.pack(side="left", padx=(6, 0))
            self.diff_chk_widgets.append(chk)

        # 정답률 (한 줄)
        self.var_use_rate = tk.BooleanVar(value=False)
        rate_row = tk.Frame(container, bg="#f9f9f9")
        rate_row.pack(fill="x", pady=(3, 5))
        tk.Checkbutton(rate_row, text="정답률 사용", variable=self.var_use_rate,
                       font=("Segoe UI", 10, "bold"), bg="#f9f9f9",
                       command=self._on_rate_toggle).pack(side="left")
        self.entry_rate_min = tk.Spinbox(rate_row, from_=0, to=100, increment=5,
                                         width=4, justify="center", state="disabled")
        self.entry_rate_min.pack(side="left", padx=(8, 0))
        self.entry_rate_min.delete(0, "end"); self.entry_rate_min.insert(0, "0")
        tk.Label(rate_row, text="% ~", bg="#f9f9f9").pack(side="left")
        self.entry_rate_max = tk.Spinbox(rate_row, from_=0, to=100, increment=5,
                                         width=4, justify="center", state="disabled")
        self.entry_rate_max.pack(side="left")
        self.entry_rate_max.delete(0, "end"); self.entry_rate_max.insert(0, "100")
        tk.Label(rate_row, text="%", bg="#f9f9f9").pack(side="left", padx=(0, 4))
        self.btn_rate_apply = tk.Button(rate_row, text="적용", command=self._apply_rate_filter,
                                        bg="#e0e0e0", relief="raised", padx=5, state="disabled")
        self.btn_rate_apply.pack(side="left")
        if not hasattr(self, 'rate_filter_ids'):
            self.rate_filter_ids = None
        # rate_body를 rate_row 자체로 대체했으므로 self.rate_body 참조용 alias
        self.rate_body = rate_row

        divider()

        # ── 3. 형식별 보기 (한 줄) ──────────────────────────────────────
        type_row = tk.Frame(container, bg="#f9f9f9")
        type_row.pack(fill="x", pady=(0, 5))
        self.var_view_type = tk.BooleanVar(value=False)
        tk.Checkbutton(type_row, text="형식별 보기", variable=self.var_view_type,
                       font=("Segoe UI", 10, "bold"), bg="#f9f9f9",
                       command=self._on_any_filter_change).pack(side="left")
        self.vars_type = {}
        for t_code, t_name in [("0", "객관식"), ("1", "주관식")]:
            var = tk.BooleanVar(value=True)
            self.vars_type[t_code] = var
            tk.Checkbutton(type_row, text=t_name, variable=var, bg="#f9f9f9",
                           command=self._on_any_filter_change).pack(side="left", padx=(10, 0))

        divider()

        # ── 3.5 문항선호도 필터 (1줄 + 인라인 펼침) ─────────────────
        # pref_wrapper: pref_row와 pref_scope_frame을 하나로 묶어
        #               scope_frame이 항상 pref_row 바로 아래에 위치하도록 함
        pref_wrapper = tk.Frame(container, bg="#f9f9f9")
        pref_wrapper.pack(fill="x", pady=(0, 2))

        # 메인 1줄 행
        pref_row = tk.Frame(pref_wrapper, bg="#f9f9f9")
        pref_row.pack(fill="x")

        self.var_pref_filter = tk.BooleanVar(value=self._saved_pref_filter_enabled)
        tk.Checkbutton(pref_row, text="문항선호도", variable=self.var_pref_filter,
                       font=("Segoe UI", 10, "bold"), bg="#f9f9f9",
                       command=self._on_pref_filter_toggle).pack(side="left")

        # Good / Soso / Bad 체크박스 — 같은 줄
        PREF_COLORS_RP = [("Good", "#2e7d32"), ("Soso", "#e65100"), ("Bad", "#c62828")]
        self.vars_pref = {}
        self._pref_cb_widgets = {}
        for pref_name, color in PREF_COLORS_RP:
            init_val = getattr(self, f"_saved_pref_{pref_name}", True)
            var = tk.BooleanVar(value=init_val)
            self.vars_pref[pref_name] = var
            cb = tk.Checkbutton(pref_row, text=pref_name, variable=var,
                                bg="#f9f9f9", fg=color,
                                font=("Segoe UI", 9, "bold"),
                                command=self._on_pref_cb_change)
            cb.pack(side="left", padx=(5, 0))
            self._pref_cb_widgets[pref_name] = cb

        # ▼ 펼치기 버튼
        self._pref_scope_expanded = getattr(self, '_saved_pref_scope_expanded', False)
        self._btn_pref_expand = tk.Button(
            pref_row, text="▼" if not self._pref_scope_expanded else "▲",
            font=("Segoe UI", 7), bg="#f9f9f9", fg="#777",
            relief="flat", bd=0, cursor="hand2",
            command=self._toggle_pref_scope
        )
        self._btn_pref_expand.pack(side="left", padx=(8, 0))

        # 내 것만 / 남의 것도 — pref_wrapper 자식 → pref_row 바로 아래에 위치
        self.pref_scope_frame = tk.Frame(pref_wrapper, bg="#efefef", padx=18, pady=3)
        self.var_pref_scope = tk.StringVar(value=self._saved_pref_scope)
        self._rb_mine = tk.Radiobutton(self.pref_scope_frame, text="내 것만",
                                       variable=self.var_pref_scope, value="mine",
                                       bg="#efefef", command=self._on_pref_cb_change)
        self._rb_mine.pack(side="left")
        self._rb_all  = tk.Radiobutton(self.pref_scope_frame, text="남의 것도",
                                       variable=self.var_pref_scope, value="all",
                                       bg="#efefef", command=self._on_pref_cb_change)
        self._rb_all.pack(side="left", padx=(10, 0))
        self._pref_scope_widgets = [self._rb_mine, self._rb_all]

        # 저장된 펼침 상태 복원
        if self._pref_scope_expanded:
            self.pref_scope_frame.pack(fill="x", pady=(0, 2))

        self._on_pref_filter_toggle()   # 초기 활성/비활성 상태 적용

        divider()

        # ── 4. 년도 필터 (한 줄) ────────────────────────────────────────
        year_top_row = tk.Frame(container, bg="#f9f9f9")
        year_top_row.pack(fill="x", pady=(0, 3))
        self.var_year_filter_on = tk.BooleanVar(value=False)
        tk.Checkbutton(year_top_row, text="년도 필터", variable=self.var_year_filter_on,
                       font=("Segoe UI", 10, "bold"), bg="#f9f9f9",
                       command=self._on_year_filter_toggle).pack(side="left")
        self.var_year_mode = tk.StringVar(value="exclude")
        self.rb_year_exclude = tk.Radiobutton(year_top_row, text="제외", variable=self.var_year_mode,
                                               value="exclude", bg="#f9f9f9", command=self._on_year_mode_change)
        self.rb_year_exclude.pack(side="left", padx=(10, 0))
        self.rb_year_include = tk.Radiobutton(year_top_row, text="포함", variable=self.var_year_mode,
                                               value="include", bg="#f9f9f9", command=self._on_year_mode_change)
        self.rb_year_include.pack(side="left")
        self.year_filter_body = tk.Frame(container, bg="#f9f9f9", padx=20)
        self.year_filter_body.pack(fill="x", pady=(0, 5))
        year_input_frame = tk.Frame(self.year_filter_body, bg="#f9f9f9")
        year_input_frame.pack(fill="x")
        available_years = self.db_engine.get_unique_years()
        self.cbo_year = ttk.Combobox(year_input_frame, values=available_years, width=10, state="disabled")
        self.cbo_year.pack(side="left")
        if available_years: self.cbo_year.current(0)
        self.btn_year_add = tk.Button(year_input_frame, text="추가", command=self._on_add_year,
                                      bg="#e0e0e0", relief="raised", padx=5, state="disabled")
        self.btn_year_add.pack(side="left", padx=5)
        self.frame_year_tags = tk.Frame(self.year_filter_body, bg="#f9f9f9")
        self.frame_year_tags.pack(fill="x", pady=(5, 5))
        if not hasattr(self, 'selected_years'):
            self.selected_years = []
        self._refresh_year_tags()
        self._on_year_filter_toggle()

        divider()

        # ── 5. 출제 제외 옵션 ───────────────────────────────────────────
        tk.Label(container, text="출제 제외 옵션", font=FONT_BOLD,
                 bg="#f9f9f9", fg="#1976d2", anchor="w").pack(fill="x", pady=(0, 5))
        excl_frame = tk.Frame(container, bg="#fff8e1", bd=1, relief="solid", padx=10, pady=8)
        excl_frame.pack(fill="x", pady=(0, 10))
        self.var_include_excluded = tk.BooleanVar(value=False)
        tk.Checkbutton(excl_frame, text="제외설정된 문제도 출제하기",
                       variable=self.var_include_excluded, bg="#fff8e1",
                       font=("Segoe UI", 9, "bold"), fg="#e65100",
                       command=self._refresh_step_2_list).pack(anchor="w")
        tk.Button(excl_frame, text="제외설정 보기", command=self._open_exclusion_dialog,
                  bg="#ffe082", relief="raised", font=("Segoe UI", 9), padx=6).pack(anchor="w", pady=(5, 0))

        # ── 7. 문항 배분 ────────────────────────────────────────────────
        tk.Label(container, text="문항 배분", font=FONT_BOLD,
                 bg="#f9f9f9", fg="#1976d2", anchor="w").pack(fill="x", pady=(10, 5))
        dist_frame = tk.Frame(container, bg="#f0f0f0", bd=1, relief="solid", padx=10, pady=10)
        dist_frame.pack(fill="x")
        tk.Label(dist_frame, text="총 문항:", bg="#f0f0f0").pack(side="left")
        self.entry_total_qty = tk.Spinbox(dist_frame, from_=1, to=200, width=5,
                                          justify="center", font=("Segoe UI", 10))
        self.entry_total_qty.pack(side="left", padx=5)
        self.entry_total_qty.delete(0, "end"); self.entry_total_qty.insert(0, "30")
        tk.Button(dist_frame, text="균등 배분", command=self._distribute_evenly,
                  bg="white", relief="raised").pack(side="left", padx=2, fill="x", expand=True)
        tk.Button(dist_frame, text="비율 배분", command=self._distribute_ratio,
                  bg="white", relief="raised").pack(side="left", padx=2, fill="x", expand=True)
        self.lbl_step2_total = tk.Label(dist_frame, text="0",
                                         font=("Segoe UI", 12, "bold"), fg="#d32f2f", bg="#f0f0f0")
        self.lbl_step2_total.pack(side="right", padx=5)
        tk.Label(dist_frame, text="현재 합계:", font=("Segoe UI", 9), bg="#f0f0f0").pack(side="right")

        # ── 8. 상세 필터 (토글) ─────────────────────────────────────────
        self.btn_detail_toggle = tk.Button(
            container, text="▶  상세 필터",
            font=("Segoe UI", 10, "bold"), bg="#e8eaf6", fg="#3949ab",
            relief="flat", anchor="w", padx=8, pady=5,
            command=self._toggle_detail_filter
        )
        self.btn_detail_toggle.pack(fill="x", pady=(10, 0))

        # 상세 필터 내용 프레임 (기본 숨김)
        self.detail_filter_frame = tk.Frame(container, bg="#eef0fb", bd=1, relief="solid", padx=10, pady=8)
        # 기본 숨김 → pack 하지 않음

        # ── 학교 옵션 (상세 필터 안) ──
        self.var_school_option_on = tk.BooleanVar(value=False)
        tk.Checkbutton(self.detail_filter_frame, text="학교 옵션",
                       variable=self.var_school_option_on,
                       font=("Segoe UI", 9, "bold"), bg="#eef0fb",
                       command=self._on_school_option_toggle).pack(anchor="w")

        self.school_option_body = tk.Frame(self.detail_filter_frame, bg="#eef0fb", padx=15)
        # 기본 숨김 → pack 하지 않음

        tk.Label(self.school_option_body, text="학교명 검색:", bg="#eef0fb",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        sch_row = tk.Frame(self.school_option_body, bg="#eef0fb")
        sch_row.pack(fill="x", pady=(2, 5))
        self.entry_school_search = tk.Entry(sch_row)
        self.entry_school_search.pack(side="left", fill="x", expand=True)
        self.entry_school_search.bind("<Return>", self._on_school_search)
        tk.Button(sch_row, text="검색", command=self._on_school_search,
                  bg="#e0e0e0", relief="raised", padx=5).pack(side="right", padx=(5, 0))
        tk.Label(self.school_option_body, text="▼ 검색 결과를 클릭하면 추가됩니다",
                 bg="#eef0fb", fg="#888", font=("Segoe UI", 8)).pack(anchor="w")
        self.list_school_results = tk.Listbox(self.school_option_body, height=3,
                                               selectmode="single", exportselection=False)
        self.list_school_results.pack(fill="x", pady=(0, 5))
        self.list_school_results.bind("<<ListboxSelect>>", self._on_school_select)
        self.list_school_results.bind("<Double-Button-1>", self._on_school_select)
        self.frame_selected_schools = tk.Frame(self.school_option_body, bg="#eef0fb")
        self.frame_selected_schools.pack(fill="x", pady=(0, 5))
        if not hasattr(self, 'selected_schools'):
            self.selected_schools = []
        self._refresh_selected_school_tags()

        # ── 모의고사 검색 (상세 필터 안) ──
        self.var_brand_option_on = tk.BooleanVar(value=False)
        tk.Checkbutton(self.detail_filter_frame, text="모의고사 검색",
                       variable=self.var_brand_option_on,
                       font=("Segoe UI", 9, "bold"), bg="#eef0fb",
                       command=self._on_brand_option_toggle).pack(anchor="w", pady=(6, 0))

        self.brand_option_body = tk.Frame(self.detail_filter_frame, bg="#eef0fb", padx=15)
        # 기본 숨김 → pack 하지 않음

        tk.Label(self.brand_option_body, text="키워드 입력 (예: 한석원, 시대인재):",
                 bg="#eef0fb", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        brand_row = tk.Frame(self.brand_option_body, bg="#eef0fb")
        brand_row.pack(fill="x", pady=(2, 5))
        self.entry_brand_search = tk.Entry(brand_row)
        self.entry_brand_search.pack(side="left", fill="x", expand=True)
        self.entry_brand_search.bind("<Return>", self._on_brand_add)
        tk.Button(brand_row, text="추가", command=self._on_brand_add,
                  bg="#e0e0e0", relief="raised", padx=5).pack(side="right", padx=(5, 0))
        self.frame_selected_brands = tk.Frame(self.brand_option_body, bg="#eef0fb")
        self.frame_selected_brands.pack(fill="x", pady=(0, 5))
        if not hasattr(self, 'selected_brands'):
            self.selected_brands = []
        self._refresh_selected_brand_tags()

        # ── 문항번호 필터 (상세 필터 안) ──
        pnum_row = tk.Frame(self.detail_filter_frame, bg="#eef0fb")
        pnum_row.pack(fill="x", pady=(8, 2))
        self.var_pnum_on = tk.BooleanVar(value=False)
        tk.Checkbutton(pnum_row, text="문항번호 필터", variable=self.var_pnum_on,
                       font=("Segoe UI", 9, "bold"), bg="#eef0fb",
                       command=self._on_pnum_toggle).pack(side="left")
        self.entry_pnum = tk.Entry(pnum_row, width=18, state="disabled",
                                   fg="#888", relief="solid")
        self.entry_pnum.insert(0, "예: 30, 45, 46")
        self.entry_pnum.pack(side="left", padx=(8, 0))
        self.entry_pnum.bind("<Return>", lambda e: self._on_any_filter_change())
        self.btn_pnum_apply = tk.Button(pnum_row, text="적용",
                                        command=self._on_any_filter_change,
                                        bg="#e0e0e0", relief="raised", padx=5, state="disabled")
        self.btn_pnum_apply.pack(side="left", padx=(4, 0))


    def _toggle_detail_filter(self):
        """상세 필터 섹션 펼치기/접기 토글"""
        if self.detail_filter_frame.winfo_ismapped():
            self.detail_filter_frame.pack_forget()
            self.btn_detail_toggle.config(text="▶  상세 필터")
        else:
            self.detail_filter_frame.pack(fill="x", pady=(4, 0))
            self.btn_detail_toggle.config(text="▼  상세 필터")

    def _on_source_filter_toggle(self):
        """소스 필터 체크박스 ON/OFF → 개별 소스 체크박스 활성/비활성"""
        state = "normal" if self.var_source_filter_on.get() else "disabled"
        for chk in getattr(self, 'source_chk_widgets', []):
            chk.config(state=state)
        self._refresh_unit_tree()
        self._refresh_step_2_list()

    def _on_source_deselect_all(self):
        """소스 전체해제 버튼 → 모든 소스 체크 해제 후 필터 갱신"""
        for var in getattr(self, 'var_sources', {}).values():
            var.set(False)
        self._on_source_filter_change()

    def _on_level_toggle(self):
        """수준별 보기 ON/OFF → 하위 체크박스 활성/비활성 + 필터 갱신"""
        state = "normal" if self.var_view_level.get() else "disabled"
        for chk in getattr(self, 'diff_chk_widgets', []):
            chk.config(state=state)
        self._refresh_unit_tree()
        self._refresh_step_2_list()

    def _on_school_option_toggle(self):
        """학교 옵션 체크박스 ON → school_option_body 표시/숨김"""
        if self.var_school_option_on.get():
            self.school_option_body.pack(fill="x", pady=(5, 0))
        else:
            self.school_option_body.pack_forget()
            # 학교 선택 초기화
            if hasattr(self, 'selected_schools'):
                self.selected_schools.clear()
                self._refresh_selected_school_tags()
            self._on_any_filter_change()

    def _on_rate_toggle(self):
        """정답률 사용 체크박스 토글 → 하위 위젯 활성/비활성 + 즉시 필터 적용"""
        use = self.var_use_rate.get()
        new_state = "normal" if use else "disabled"
        self.entry_rate_min.config(state=new_state)
        self.entry_rate_max.config(state=new_state)
        self.btn_rate_apply.config(state=new_state)
        if use:
            # 체크 시 현재 범위로 즉시 적용
            self._apply_rate_filter()
        else:
            # 체크 해제 시 필터 초기화
            self.rate_filter_ids = None
            self._on_any_filter_change()

    def _apply_rate_filter(self):
        """정답률 범위 입력 파싱 → DB 조회 → 테이블 갱신"""
        try:
            min_pct = float(self.entry_rate_min.get().strip())
            max_pct = float(self.entry_rate_max.get().strip())
        except ValueError:
            from tkinter import messagebox
            messagebox.showwarning("입력 오류", "정답률 범위에 숫자를 입력하세요. (예: 0 ~ 100)")
            return

        if not (0 <= min_pct <= 100 and 0 <= max_pct <= 100 and min_pct <= max_pct):
            from tkinter import messagebox
            messagebox.showwarning("입력 오류", "0 ≤ 최솟값 ≤ 최댓값 ≤ 100 이어야 합니다.")
            return

        min_rate = min_pct / 100.0
        max_rate = max_pct / 100.0

        ids = self.db_engine.get_problem_ids_by_rate(min_rate, max_rate)
        self.rate_filter_ids = ids  # 빈 리스트도 유효 (결과 0건)
        self._on_any_filter_change()

    def _open_exclusion_dialog(self):
        """일회성 출제 제외 설정 다이얼로그 열기. 닫힌 후 Step2 가능 문제 수 갱신."""

        dlg = ExclusionSettingDialog(self.root, self.db_engine, gui=self)
        self.root.wait_window(dlg.top)
        # 다이얼로그 닫히면 트리 + 목록 모두 갱신 (제외 set 변동 반영)
        self._on_any_filter_change()

    def _on_school_search(self, event=None):
        """Searches schools and updates listbox"""
        keyword = self.entry_school_search.get().strip()
        if not keyword: return

        results = self.db_engine.search_schools(keyword)
        self.list_school_results.delete(0, "end")
        for res in results:
            self.list_school_results.insert("end", res)
            
    def _on_school_select(self, event):
        """Adds selected school to tags (Max 5)"""
        selection = self.list_school_results.curselection()
        if not selection: return
        
        school = self.list_school_results.get(selection[0])
        
        if school not in self.selected_schools:
            if len(self.selected_schools) >= 5:
                messagebox.showwarning("학교 선택 제한", "학교는 최대 5개까지만 선택할 수 있습니다.")
            else:
                self.selected_schools.append(school)
                self._refresh_selected_school_tags()
                self._on_any_filter_change()
            
        # Clear selection
        self.list_school_results.selection_clear(0, "end")
        
    def _remove_school_tag(self, school):
        """Removes school from selection"""
        if school in self.selected_schools:
            self.selected_schools.remove(school)
            self._refresh_selected_school_tags()
            self._on_any_filter_change()

    def _refresh_selected_school_tags(self):
        """Renders tags for selected schools (Grid Layout)"""
        for w in self.frame_selected_schools.winfo_children():
            w.destroy()
            
        for i, sch in enumerate(self.selected_schools):
            row = i // 2
            col = i % 2
            
            tag_frame = tk.Frame(self.frame_selected_schools, bg="#e3f2fd", padx=5, pady=2, relief="solid", bd=1)
            tag_frame.grid(row=row, column=col, sticky="ew", padx=2, pady=2)
            
            tk.Label(tag_frame, text=sch, bg="#e3f2fd", font=("Segoe UI", 9)).pack(side="left")
            tk.Button(tag_frame, text="x", command=lambda s=sch: self._remove_school_tag(s), 
                      bg="#e3f2fd", fg="red", relief="flat", font=("Segoe UI", 9, "bold"), padx=2).pack(side="right", padx=(2,0))


    def _on_brand_option_toggle(self):
        """모의고사 브랜드 옵션 체크박스 ON → brand_option_body 표시/숨김"""
        if self.var_brand_option_on.get():
            self.brand_option_body.pack(fill="x", pady=(5, 0))
        else:
            self.brand_option_body.pack_forget()
            if hasattr(self, 'selected_brands'):
                self.selected_brands.clear()
                self._refresh_selected_brand_tags()
            self._on_any_filter_change()

    def _on_pnum_toggle(self):
        """문항번호 필터 체크박스 토글"""
        on = self.var_pnum_on.get()
        state = "normal" if on else "disabled"
        self.entry_pnum.config(state=state)
        self.btn_pnum_apply.config(state=state)
        if not on:
            # 끄면 entry 초기화
            self.entry_pnum.config(state="normal")
            self.entry_pnum.delete(0, "end")
            self.entry_pnum.insert(0, "예: 30, 45, 46")
            self.entry_pnum.config(state="disabled", fg="#888")
        else:
            self.entry_pnum.config(fg="black")
            self.entry_pnum.delete(0, "end")
        self._on_any_filter_change()

    def _on_brand_add(self, event=None):
        """키워드 입력 → 태그 직접 추가 (A안)"""
        keyword = self.entry_brand_search.get().strip()
        if not keyword:
            return
        if keyword not in self.selected_brands:
            self.selected_brands.append(keyword)
            self._refresh_selected_brand_tags()
            self._on_any_filter_change()
        self.entry_brand_search.delete(0, "end")

    def _remove_brand_tag(self, brand):
        """태그 X 클릭 → 브랜드 제거"""
        if brand in self.selected_brands:
            self.selected_brands.remove(brand)
            self._refresh_selected_brand_tags()
            self._on_any_filter_change()

    def _refresh_selected_brand_tags(self):
        """선택된 브랜드 태그 렌더링"""
        for w in self.frame_selected_brands.winfo_children():
            w.destroy()
        for i, brand in enumerate(self.selected_brands):
            row = i // 2
            col = i % 2
            tag_frame = tk.Frame(self.frame_selected_brands, bg="#fff3e0", padx=5, pady=2, relief="solid", bd=1)
            tag_frame.grid(row=row, column=col, sticky="ew", padx=2, pady=2)
            tk.Label(tag_frame, text=brand, bg="#fff3e0", font=("Segoe UI", 9)).pack(side="left")
            tk.Button(tag_frame, text="x", command=lambda b=brand: self._remove_brand_tag(b),
                      bg="#fff3e0", fg="red", relief="flat", font=("Segoe UI", 9, "bold"), padx=2).pack(side="right", padx=(2, 0))

    def _on_year_filter_toggle(self):
        """년도 필터 체크박스 토글 → 하위 위젯 활성/비활성"""
        on = self.var_year_filter_on.get()
        state_rb  = "normal"   if on else "disabled"
        state_cb  = "readonly" if on else "disabled"
        state_btn = "normal"   if on else "disabled"

        self.rb_year_exclude.config(state=state_rb)
        self.rb_year_include.config(state=state_rb)
        self.cbo_year.config(state=state_cb)
        self.btn_year_add.config(state=state_btn)

        if not on:
            # 필터 끄면 선택 년도 초기화
            if hasattr(self, 'selected_years'):
                self.selected_years.clear()
                self._refresh_year_tags()

        self._on_any_filter_change()

    def _on_year_mode_change(self):
        """ Clears selected years when switching mode (include <-> exclude) """
        if hasattr(self, 'selected_years'):
            self.selected_years.clear()
            self._refresh_year_tags()
            self._on_any_filter_change()

    def _on_add_year(self):
        """Adds selected year to tags"""
        val = self.cbo_year.get()
        if not val: return
        
        if val not in self.selected_years:
            if len(self.selected_years) >= 3:
                messagebox.showwarning("년도 선택 제한", "년도는 최대 3개까지만 선택할 수 있습니다.")
                return
            self.selected_years.append(val)
            self._refresh_year_tags()
            self._on_any_filter_change()

    def _remove_year_tag(self, year):
        if year in self.selected_years:
            self.selected_years.remove(year)
            self._refresh_year_tags()
            self._on_any_filter_change()

    def _refresh_year_tags(self):
        for w in self.frame_year_tags.winfo_children():
            w.destroy()
        
        for y in self.selected_years:
            tag_frame = tk.Frame(self.frame_year_tags, bg="#fff3e0", padx=5, pady=2, relief="solid", bd=1)
            tag_frame.pack(side="left", padx=2)
            
            lbl_text = f"{y}"
            tk.Label(tag_frame, text=lbl_text, bg="#fff3e0", font=("Segoe UI", 9)).pack(side="left")
            tk.Button(tag_frame, text="x", command=lambda s=y: self._remove_year_tag(s),
                      bg="#fff3e0", fg="red", relief="flat", font=("Segoe UI", 9, "bold"), padx=2).pack(side="right")

    def _build_left_panel_table(self):
        """Builds the scrollable table area for Left Panel"""
        # Header
        header_frame = tk.Frame(self.left_panel, bg="#eaeaea", pady=5, bd=1, relief="solid")
        header_frame.pack(fill="x")
        
        # Col widths: Unit(200), Level(50), Type(60), Avail(60), Input(60)
        self.cols_cfg = [("단원명", 200), ("수준", 60), ("형식", 60), ("가능", 60), ("출제", 60)]
        
        for idx, (col, w) in enumerate(self.cols_cfg):
            lbl_width = 10 if w < 100 else 20
            if idx == 0: lbl_width = 0 # Ignored if packed with fill
            
            lbl = tk.Label(header_frame, text=col, bg="#eaeaea", font=("Segoe UI", 9, "bold"), anchor="center", width=lbl_width)
            if idx == 0: # Unit name expands
                lbl.pack(side="left", fill="x", expand=True)
            else:
                lbl.pack(side="left") # Approx char width
                
        # Scrollable Area
        self.unit_list_canvas = tk.Canvas(self.left_panel, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.left_panel, orient="vertical", command=self.unit_list_canvas.yview)
        
        self.unit_list_frame = tk.Frame(self.unit_list_canvas, bg="white")
        
        self.unit_list_frame.bind(
            "<Configure>",
            lambda e: self.unit_list_canvas.configure(scrollregion=self.unit_list_canvas.bbox("all"))
        )
        
        self.unit_list_window = self.unit_list_canvas.create_window((0, 0), window=self.unit_list_frame, anchor="nw")
        
        self.unit_list_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.unit_list_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind resize
        self.unit_list_canvas.bind('<Configure>', self._on_canvas_configure)

    def _on_canvas_configure(self, event):
        self.unit_list_canvas.itemconfig(self.unit_list_window, width=event.width)

    def _refresh_step_2_list(self):
        """Refreshes the Left Panel Table based on View Options & Filters"""
        if not hasattr(self, 'selected_units_data'): return
        if not hasattr(self, 'unit_list_frame'): return
        try:
            if not self.unit_list_frame.winfo_exists(): return
        except Exception:
            return

        # Clear existing rows
        for widget in self.unit_list_frame.winfo_children():
            widget.destroy()
            
        self.alloc_entries = {} # Key: (u_code, u_ver, level, type) -> Entry Widget
        self.avail_counts = {}  # Key: (u_code, u_ver, level, type) -> int count
        
        # Helper lists
        levels = [("A", "최상"), ("B", "상"), ("C", "중"), ("D", "하")]
        types = [("0", "객관식"), ("1", "주관식")]
        
        # Determine active rows per unit
        show_levels = self.var_view_level.get()
        show_types = self.var_view_type.get()
        
        row_idx = 0
        
        for unit in self.selected_units_data:
            u_code = unit['code']
            u_ver = unit.get('version', '')
            u_name = self._find_unit_name(u_code, u_ver)
            u_type = unit.get('type', 'medium')
            
            # Decide iteration targets
            # If show_levels is True, iterate activated levels. Else use None (Aggregate).
            target_levels = []
            if show_levels:
                for code, name in levels:
                    if self.vars_diff[code].get(): target_levels.append((code, name))
            else:
                target_levels = [(None, "전체")]
                
            # If show_types is True, iterate activated types. Else use None.
            target_types = []
            if show_types:
                for code, name in types:
                    if self.vars_type[code].get(): target_types.append((code, name))
            else:
                target_types = [(None, "전체")]
            
            # Generate Rows
            first_row_of_unit = True
            for lvl_code, lvl_name in target_levels:
                for type_code, type_name in target_types:
                    
                    # Frame for Row
                    row_frame = tk.Frame(self.unit_list_frame, bg="white", pady=2)
                    row_frame.pack(fill="x", padx=5)
                    
                    # 1. Unit Name (Show only on first row of unit block)
                    txt_name = f"{'[대] ' if u_type=='large' else ''}{u_name}" if first_row_of_unit else ""
                    lbl_name = tk.Label(row_frame, text=txt_name, bg="white", anchor="w")
                    # Set fixed width behavior via pack/expand
                    lbl_name.pack(side="left", fill="x", expand=True) # Takes remaining space (approx 200px equivalent)
                    
                    # 2. Level
                    tk.Label(row_frame, text=lvl_name, bg="white", width=8, fg="#555").pack(side="left")
                    
                    # 3. Type
                    tk.Label(row_frame, text=type_name, bg="white", width=8, fg="#555").pack(side="left")
                    
                    # 4. Available Count (Query DB)
                    cnt = self._query_count_for_row(u_code, u_ver, u_type, lvl_code, type_code)
                    key = (u_code, u_ver, lvl_code, type_code) # Key struct
                    self.avail_counts[key] = cnt
                    
                    tk.Label(row_frame, text=str(cnt), bg="white", width=8, fg="#1976d2", font=FONT_BOLD).pack(side="left")
                    
                    # 5. Input Entry
                    entry = tk.Spinbox(row_frame, from_=0, to=200, width=5, justify="center", 
                                       command=self._update_total_label, font=("Segoe UI", 10))
                    entry.pack(side="left", padx=5)
                    entry.delete(0, "end")
                    entry.insert(0, "0")
                    # Bind KeyRelease to update total when typing manually
                    entry.bind("<KeyRelease>", self._update_total_label)
                    # Bind Arrow keys to update total (delayed to allow value change first)
                    entry.bind("<Up>", lambda e: self.root.after(10, self._update_total_label))
                    entry.bind("<Down>", lambda e: self.root.after(10, self._update_total_label))
                    
                    self.alloc_entries[key] = entry
                    
                    # Divider (faint)
                    tk.Frame(self.unit_list_frame, bg="#eeeeee", height=1).pack(fill="x")

                    first_row_of_unit = False
                    row_idx += 1
                    
            # Stronger Separator between units
            tk.Frame(self.unit_list_frame, bg="#dddddd", height=2).pack(fill="x", pady=0)
            
        # Update Total based on currently visible entries
        self._update_total_label()

    def _query_count_for_row(self, u_code, u_ver, u_type, lvl_code, type_code):
        """
        Queries DB for available count based on row criteria + global filters.
        Adapts to LocalDBEngine.query_counts(filters: Dict) interface.
        """
        filters = {}

        # 1. Unit Filter — 2026-05-23: 2015/2022 코드 통합 → 변환 없이 직접 사용
        if u_type == 'large':
            kids = self._get_medium_codes_for_large(u_code, u_ver)
            if kids:
                filters["unit_code"] = {"in": kids}
            else:
                filters["unit_code"] = "NONE"
        else:
            filters["unit_code"] = u_code

        # 2. Level Filter
        if lvl_code:
            filters["difficulty"] = lvl_code
        else:
            # 수준별 보기 ON일 때만 difficulty 필터 적용
            view_level_on = getattr(self, 'var_view_level', None) and self.var_view_level.get()
            if view_level_on:
                active_levels = [k for k, v in self.vars_diff.items() if v.get()]
                if not active_levels:
                    filters["difficulty"] = "___NO_LEVEL___"  # 아무것도 선택 안 됨 → 0건
                elif len(active_levels) < 4:
                    filters["difficulty"] = {"in": active_levels}
            # OFF면 difficulty 필터 없음 → 전체 수준 포함

        # 3. Type Filter
        if type_code:
            if type_code == '0':
                filters["problem_type"] = "객관식"
            elif type_code == '1':
                filters["problem_type"] = {"in": ["주관식", "서술형", "단답형"]}
        else:
            active_types = []
            if self.vars_type['0'].get(): active_types.append("객관식")
            if self.vars_type['1'].get(): active_types.extend(["주관식", "서술형", "단답형"])

            if not active_types: return 0
            filters["problem_type"] = {"in": active_types}

        # 4. Global Filters (단일 출처 _build_global_filters 사용)
        global_f = self._build_global_filters()
        rate_ids = global_f.pop("_rate_ids", None)
        brand_ids = global_f.pop("_brand_ids", None)
        filters.update(global_f)

        # 제외설정된 문제도 출제하기 체크 시 → 제외 문제도 카운트에 포함
        include_excl = getattr(self, 'var_include_excluded', None)
        include_excluded_val = include_excl.get() if include_excl else False

        # 5. ID 필터 통합 (rate_ids, brand_ids 교집합)
        combined = None
        if brand_ids is not None:
            combined = set(brand_ids)
        if rate_ids is not None:
            combined = (combined & set(rate_ids)) if combined is not None else set(rate_ids)

        # 6. 선호도 필터 (pref_ids) 통합
        pref_ids = self._get_pref_filter_ids()   # None → 비활성, set → 활성
        if pref_ids is not None:
            combined = (combined & pref_ids) if combined is not None else pref_ids

        # 7. 일회성 제외 (ExclusionSettingDialog) — UI 카운트에 반영
        oneshot_excluded = getattr(self, '_oneshot_excluded_problem_ids', None) or set()

        if combined is not None:
            combined = combined - oneshot_excluded if oneshot_excluded else combined
            if not combined:
                return 0
            filters["id"] = {"in": list(combined)}

        base_count = self.db_engine.query_counts(filters, include_excluded=include_excluded_val)

        # oneshot_excluded가 있으면, 그 중 현재 필터 범위의 개수를 빼기
        if oneshot_excluded and not combined:  # combined이 None인 경우만 (combined이 있으면 이미 제외됨)
            # 필터 범위 내에서 실제로 제외될 문제 개수 계산
            import sqlite3
            try:
                conn = sqlite3.connect(self.db_engine.db_path)
                cur = conn.cursor()
                where_parts = ["id IN ({})".format(','.join(['?']*len(oneshot_excluded)))]
                params = list(oneshot_excluded)

                for key, val in filters.items():
                    if isinstance(val, dict) and "in" in val:
                        placeholders = ','.join(['?'] * len(val["in"]))
                        where_parts.append(f"{key} IN ({placeholders})")
                        params.extend(val["in"])
                    elif isinstance(val, dict):
                        continue
                    else:
                        where_parts.append(f"{key} = ?")
                        params.append(val)

                if not include_excluded_val:
                    where_parts.append("is_excluded = 0")

                where_clause = " AND ".join(where_parts)
                sql = f"SELECT COUNT(*) FROM problems WHERE {where_clause}"
                cur.execute(sql, params)
                excluded_in_filter_cnt = cur.fetchone()[0]
                conn.close()
                base_count = max(0, base_count - excluded_in_filter_cnt)
            except Exception as e:
                print(f"[일회성제외] 카운트 오류: {e}")

        return base_count

    def _find_unit_name(self, code, version):
        """Helper to find unit name by code"""
        # Search in hierarchy
        # Note: self.unit_hierarchy structure: {version: [ {subject:..., large_units:[...]} ] }
        if version not in self.unit_hierarchy: return code
        
        for subj in self.unit_hierarchy[version]:
            for large in subj.get("large_units", []):
                if large["code"] == code: return large["name"]
                for medium in large.get("medium_units", []):
                    if medium["code"] == code: return medium["name"]
        return code

    def _get_medium_codes_for_large(self, large_code, version):
        """Helper to get list of medium codes for a large unit"""
        codes = []
        for subj in self.unit_hierarchy.get(version, []):
            for large in subj.get("large_units", []):
                if large["code"] == large_code:
                    for medium in large.get("medium_units", []):
                        codes.append(medium["code"])
                    return codes
        return codes



    def _back_to_step_1(self):
        """Returns to Step 1: Unit Selection (Preserving selection)"""
        # Step 2 위젯 참조 초기화 (파괴된 위젯 참조로 인한 TclError 방지)
        for attr in ('entry_pnum', 'btn_pnum_apply', 'entry_school_search',
                     'entry_brand_search', 'list_school_results',
                     'cbo_year', 'btn_year_add', 'entry_rate_min',
                     'entry_rate_max', 'btn_rate_apply', 'rate_body'):
            if hasattr(self, attr):
                delattr(self, attr)
        if hasattr(self, 'var_pnum_on'):
            self.var_pnum_on.set(False)

        # Clear container
        for widget in self.random_container.winfo_children():
            widget.destroy()

        # Rebuild Step 1 UI
        self._build_random_tab()
        
        # Restore selections if any
        if hasattr(self, 'selected_units_data') and self.selected_units_data:
            self._restore_selection()

    def _restore_selection(self):
        """Restores checkbox states based on selected_units_data"""
        to_check = set()
        for u in self.selected_units_data:
            key = (u['code'], u.get('version', ''))
            to_check.add(key)
        
        def _traverse_and_check(item):
            tags = list(self.unit_tree.item(item, "tags"))
            
            # Robust parsing
            code = None
            version = None
            
            if "large" in tags:
                idx = tags.index("large")
                if len(tags) > idx + 2:
                    code = tags[idx+1]
                    version = tags[idx+2]
            elif "medium" in tags:
                idx = tags.index("medium")
                if len(tags) > idx + 2:
                    code = tags[idx+1]
                    version = tags[idx+2]
                    
            if code and (code, version) in to_check:
                # Only check the item itself
                self._set_check_state(item, "checked")
            
            # Recurse to find other selected items, but do NOT force check them
            for child in self.unit_tree.get_children(item):
                _traverse_and_check(child)
        
        for child in self.unit_tree.get_children():
            _traverse_and_check(child)

    def _close_random_tab(self):
        """Closes the random tab and resets state"""
        # User Feedback: "닫기 눌러도 문항들이 안 없어지고 그대로 있어요..."
        # We need to completely nuke the state when closing the tab.

        if hasattr(self, 'selected_units_data'):
            del self.selected_units_data
        if hasattr(self, 'selected_unit_codes'):
            del self.selected_unit_codes

        # 상세 필터 초기화
        self._reset_detail_filters()

        # [FIX] Reset the generated problems and navigation mode
        self.problem_batches = []
        self.next_step3_mode = "new"
        # 탭 닫기 → 일회성 제외 리셋
        self._oneshot_excluded_problem_ids = set()
        self._oneshot_excluded_test_ids = set()

        if self.notebook:
            self.notebook.select(self.tab_home)

        for widget in self.random_container.winfo_children():
            widget.destroy()
        self._build_random_tab()

    def _go_to_step_3(self, mode=None):
        """
        Step 3: Question Confirmation
        mode: "new" (Reset & Create) or "append" (Add to existing)
        If mode is None, use self.next_step3_mode (default "new")
        """
        if mode is None:
            mode = getattr(self, "next_step3_mode", "new")
            
        print(f"DEBUG: _go_to_step_3 called with mode={mode}")

        # Validate total count
        current_total = 0
        try:
            current_total_text = self.lbl_step2_total.cget("text")
            import re
            nums = re.findall(r'\d+', current_total_text)
            if nums: current_total = int(nums[0])
        except: pass

        if current_total == 0:
            messagebox.showwarning("문항 선택", "선택된 문항이 없습니다.")
            return

        # Check total limit (existing + new)
        existing_count = 0
        if mode == "append" and hasattr(self, 'problem_batches'):
             existing_count = sum(len(b) for b in self.problem_batches)
             
        if existing_count + current_total > 200:
             messagebox.showwarning("문항 수 제한", f"총 문항 수가 200문항을 초과합니다.\n(현재: {existing_count} + 추가: {current_total})")
             return

        # Prepare Criteria
        criteria_list = []
        
        for key, entry in self.alloc_entries.items():
            try:
                qty = int(entry.get())
                if qty <= 0: continue
            except: continue
            
            u_code, u_ver, lvl_code, type_code = key
            
            filters = {}
            # 1. Unit (Handle Large Unit expansion if needed)
            u_type = 'medium'
            for u in self.selected_units_data:
                if u['code'] == u_code and u.get('version') == u_ver:
                    u_type = u.get('type', 'medium')
                    break
            
            # 2026-05-23: 2015/2022 코드 통합 → 변환 불필요
            if u_type == 'large':
                kids = self._get_medium_codes_for_large(u_code, u_ver)
                if kids: filters["unit_code"] = {"in": kids}
                else: filters["unit_code"] = "NONE"
            else:
                filters["unit_code"] = u_code
                 
            # 2. Level
            if lvl_code: filters["difficulty"] = lvl_code
            
            # 3. Type
            if type_code:
                if type_code == '0': filters["problem_type"] = "객관식"
                elif type_code == '1': filters["problem_type"] = {"in": ["주관식", "서술형", "단답형"]}
            
            # 4. Global Filters (소스·학교·년도·정답률·브랜드 — 단일 출처 사용)
            global_f = self._build_global_filters()
            rate_ids = global_f.pop("_rate_ids", None)
            brand_ids = global_f.pop("_brand_ids", None)
            filters.update(global_f)

            # 5. ID 필터 통합 (rate_ids, brand_ids 교집합)
            if brand_ids is not None or rate_ids is not None:
                combined = None
                if brand_ids is not None:
                    combined = set(brand_ids)
                if rate_ids is not None:
                    combined = (combined & set(rate_ids)) if combined is not None else set(rate_ids)
                if not combined:
                    continue  # 이 criteria는 대상 문제 없음 → 건너뜀
                filters["id"] = {"in": list(combined)}
            
            criteria_list.append({"filters": filters, "qty": qty})
            
        # Flatten hierarchy for sorting (unit_code -> index)
        self.unit_order_map = {}
        idx_counter = 0
        
        for subj in self.unit_hierarchy.get("2022", []):
            for large in subj.get("large_units", []):
                for medium in large.get("medium_units", []):
                    self.unit_order_map[medium["code"]] = idx_counter
                    idx_counter += 1
                        
        print(f"DEBUG: Loaded {len(self.unit_order_map)} units into sort map.")
        if not hasattr(self, 'problem_batches'):
            self.problem_batches = [] # List of Lists
            
        # Fetch Data
        if mode == "new":
            self.problem_batches = []
            exclude_ids = []
        else: # append
            # Flatten current batches to get exclude_ids
            current_flat = [p for batch in self.problem_batches for p in batch]
            exclude_ids = [p['id'] for p in current_flat]

        # ★ 일회성 제외 (ExclusionSettingDialog에서 사용자가 체크한 시험지의 문제들) 합산
        oneshot = getattr(self, '_oneshot_excluded_problem_ids', None) or set()
        if oneshot:
            exclude_ids = list(set(exclude_ids) | oneshot)

        include_excluded = getattr(self, 'var_include_excluded', None)
        include_excluded_val = include_excluded.get() if include_excluded else False
        new_problems = self.db_engine.fetch_random_problems(
            criteria_list, exclude_ids, include_excluded=include_excluded_val
        )

        if not new_problems and mode == "new":
            messagebox.showwarning("결과 없음", "조건에 맞는 문항을 찾을 수 없습니다.")
            return
            
        if not new_problems and mode == "append":
             messagebox.showinfo("결과 없음", "추가할 수 있는 조건에 맞는 문항이 없습니다.")
             return

        # Add as a new batch
        if new_problems:
            self.problem_batches.append(new_problems)
        
        # Build UI
        self._build_step_3_ui()

    def _build_step_3_ui(self):
        """Builds Step 3: Question List & Confirmation"""
        for widget in self.random_container.winfo_children():
            widget.destroy()
            
        # Calculate Total
        total_count = sum(len(batch) for batch in self.problem_batches)
        
        # --- 1. Top Navigation Bar ---
        nav_bar = tk.Frame(self.random_container, bg="white", pady=10, padx=20)
        nav_bar.pack(fill="x")
        
        tk.Label(nav_bar, text=f"출제 문항 확인 (총 {total_count}문항)", font=("Segoe UI", 16, "bold"), bg="white", fg="#333333").pack(side="left")
        
        btn_frame = tk.Frame(nav_bar, bg="white")
        btn_frame.pack(side="right")
        
        tk.Button(btn_frame, text="닫기", command=self._close_random_tab,
                  bg="#f5f5f5", fg="#333333", font=FONT_MAIN, relief="flat", padx=10).pack(side="right", padx=5)
                  
        tk.Button(btn_frame, text="이전", command=self._on_prev_click,
                  bg="#f5f5f5", fg="#333333", font=FONT_MAIN, relief="flat", padx=10).pack(side="right", padx=5)

        tk.Button(btn_frame, text="랜덤추가", command=self._on_random_add_click,
                  bg="#e3f2fd", fg="#1976d2", font=FONT_MAIN, relief="flat", padx=10).pack(side="right", padx=5)
                  
        tk.Button(btn_frame, text="순서정렬", command=self._open_sort_dialog,
                   bg="#f5f5f5", fg="#333333", font=FONT_MAIN, relief="flat", padx=10).pack(side="right", padx=5)

        self._sort_undo_btn = tk.Button(btn_frame, text="↺ 정렬 취소", command=self._undo_sort,
                                        bg="#fff3e0", fg="#e65100", font=FONT_MAIN,
                                        relief="flat", padx=10, state="disabled")
        self._sort_undo_btn.pack(side="right", padx=5)
                   
        tk.Button(btn_frame, text="다음", command=self._go_to_step_4,
                  bg="#1976d2", fg="white", font=FONT_BOLD, relief="flat", padx=15).pack(side="right", padx=5)

        # --- 1.5 Folder Selection (Surian Style) ---
        folder_frame = tk.Frame(self.random_container, bg="white", padx=20, pady=5)
        folder_frame.pack(fill="x")
        
        tk.Label(folder_frame, text="원본 HWP 폴더:", font=("Segoe UI", 10, "bold"), bg="white", fg="#333").pack(side="left", padx=(0, 10))
        tk.Entry(folder_frame, textvariable=self.source_hwp_dir, bg="#f5f5f5", fg="#333", 
                 insertbackground="black", bd=1, relief="solid", font=FONT_MAIN, width=60).pack(side="left", padx=5)
        tk.Button(folder_frame, text="찾아보기", command=self._browse_source_dir,
                  bg="#e0e0e0", fg="#333", font=FONT_MAIN, relief="flat", padx=10).pack(side="left", padx=5)

        # --- 2. Main List (Treeview) ---
        list_frame = tk.Frame(self.random_container, bg="white", padx=20, pady=10)
        list_frame.pack(fill="both", expand=True)
        
        # Columns: No, Source, Unit, Level, Type, Delete
        cols = ("no", "source", "unit", "level", "type", "delete")
        self.p_tree = ttk.Treeview(list_frame, columns=cols, show="headings", style="Surian.Treeview", selectmode="none")
        
        self.p_tree.heading("no", text="순번")
        self.p_tree.heading("source", text="출처")
        self.p_tree.heading("unit", text="단원")
        self.p_tree.heading("level", text="수준")
        self.p_tree.heading("type", text="형식")
        self.p_tree.heading("delete", text="관리")
        
        self.p_tree.column("no", width=50, anchor="center")
        self.p_tree.column("source", width=400, anchor="w")
        self.p_tree.column("unit", width=150, anchor="center")
        self.p_tree.column("level", width=60, anchor="center")
        self.p_tree.column("type", width=80, anchor="center")
        self.p_tree.column("delete", width=60, anchor="center")
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.p_tree.yview)
        self.p_tree.configure(yscrollcommand=scrollbar.set)
        
        self.p_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Populate
        self._refresh_step_3_list()
        
        # Bind Click for Delete
        self.p_tree.bind("<Button-1>", self._on_ptree_click)

    def _open_sort_dialog(self):
        """Opens a dialog to sort the problems in Step 3"""
        if not hasattr(self, 'problem_batches') or not self.problem_batches:
             messagebox.showinfo("안내", "정렬할 문항이 없습니다.")
             return

        # Create Dialog
        self.sort_dialog = tk.Toplevel(self.root)
        self.sort_dialog.title("문항순서정렬")
        self.sort_dialog.geometry("350x250")
        self.sort_dialog.resizable(False, False)
        
        # Center the dialog
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 125
        self.sort_dialog.geometry(f"+{x}+{y}")

        # Container
        frame = tk.Frame(self.sort_dialog, padx=20, pady=20)
        frame.pack(fill="both", expand=True)

        # Options
        sort_options = ["단원순", "수준순", "형식순", "무작위", "(없음)"]
        
        self.sort_vars = []   # List of (c_var, chk_var)
        self.sort_combos = [] # combo 위젯 참조 (비활성 제어용)
        self.sort_chks = []   # chk 위젯 참조

        for i in range(3):
            row_frame = tk.Frame(frame, pady=5)
            row_frame.pack(fill="x")

            tk.Label(row_frame, text=f"{i+1}순위:", width=6, anchor="w").pack(side="left")

            c_var = tk.StringVar()
            combo = ttk.Combobox(row_frame, textvariable=c_var, values=sort_options, state="readonly", width=12)
            combo.pack(side="left", padx=5)

            chk_var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(row_frame, text="역순", variable=chk_var)
            chk.pack(side="left", padx=5)

            # Defaults
            if i == 0: c_var.set("단원순")
            elif i == 1: c_var.set("수준순")
            elif i == 2: c_var.set("형식순")

            self.sort_vars.append((c_var, chk_var))
            self.sort_combos.append(combo)
            self.sort_chks.append(chk)

        def _update_sort_states(event=None):
            """선택 변경 시: 무작위/(없음) 이후 순위 비활성"""
            for idx, (cv, chkv) in enumerate(self.sort_vars):
                val = cv.get()
                # 이 행 자체: 무작위/(없음)이면 역순 비활성
                if val in ["무작위", "(없음)"]:
                    self.sort_chks[idx].configure(state="disabled")
                    chkv.set(False)
                    # 이후 순위 전부 비활성
                    for j in range(idx + 1, len(self.sort_vars)):
                        self.sort_combos[j].configure(state="disabled")
                        self.sort_chks[j].configure(state="disabled")
                        self.sort_vars[j][1].set(False)
                    return  # 이후는 볼 필요 없음
                else:
                    self.sort_chks[idx].configure(state="normal")
                    # 이 행이 정상이면 다음 행 활성 복구
                    if idx + 1 < len(self.sort_combos):
                        self.sort_combos[idx + 1].configure(state="readonly")

        for combo in self.sort_combos:
            combo.bind("<<ComboboxSelected>>", _update_sort_states)

        # Bottom Buttons
        btn_frame = tk.Frame(frame, pady=15)
        btn_frame.pack(fill="x", side="bottom")
        
        tk.Button(btn_frame, text="취소", command=self.sort_dialog.destroy, width=8).pack(side="right", padx=5)
        tk.Button(btn_frame, text="확인", command=self._apply_sort, bg="#1976d2", fg="white", width=8, relief="flat").pack(side="right", padx=5)

    def _apply_sort(self):
        """Applies sorting based on dialog selection"""
        # Collect criteria
        criteria = []
        for c_var, chk_var in self.sort_vars:
            criteria.append((c_var.get(), chk_var.get()))
            
        self.sort_dialog.destroy()

        # 정렬 전 batch 구조 스냅샷 (1-step undo)
        self._pre_sort_batches = [list(b) for b in self.problem_batches]

        # Flatten Batches
        all_problems = [p for batch in self.problem_batches for p in batch]
        if not all_problems:
            self._pre_sort_batches = None
            return
        
        # Pre-calculate Random keys if needed (for stability)
        import random
        for p in all_problems:
            p['_rand_key'] = random.random()
            
        # Apply sorts in Reverse Priority Order (P3 -> P2 -> P1)
        # Using Python's stable sort
        for key_type, is_reverse in reversed(criteria):
            if key_type == "(없음)": continue
            
            if key_type == "무작위":
                # Sort by random key
                all_problems.sort(key=lambda p: p['_rand_key'])
                
            elif key_type == "단원순":
                # Map unit_code to index
                def unit_key(p):
                    u_code = p.get('unit_code', '')
                    # If unit_map not ready, try to build or fallback
                    return self.unit_order_map.get(u_code, 999999)
                all_problems.sort(key=unit_key, reverse=is_reverse)
                
            elif key_type == "수준순":
                # D(0) -> C(1) -> B(2) -> A(3), 한글 폴백 포함
                l_map = {'D': 0, '하': 0, 'C': 1, '중': 1, 'B': 2, '상': 2, 'A': 3, '최상': 3}
                def level_key(p):
                    return l_map.get(p.get('difficulty'), 1) # Default C
                all_problems.sort(key=level_key, reverse=is_reverse)
                
            elif key_type == "형식순":
                # Obj(0) -> Short(1) -> Essay/Subj(2)
                t_map = {"객관식": 0, "단답형": 1, "서답형": 2, "주관식": 2, "서술형": 2}
                def type_key(p):
                    return t_map.get(p.get('problem_type'), 3)
                all_problems.sort(key=type_key, reverse=is_reverse)
                
        # Clean up temp keys
        for p in all_problems:
            if '_rand_key' in p: del p['_rand_key']
            
        # Update Batches -> Single Batch
        self.problem_batches = [all_problems]
        
        # Refresh UI
        self._refresh_step_3_list()
        try:
            if hasattr(self, "_sort_undo_btn") and self._sort_undo_btn.winfo_exists():
                self._sort_undo_btn.config(state="normal")
        except Exception:
            pass
        messagebox.showinfo(
            "정렬 완료",
            "문항 정렬이 완료되었습니다.\n"
            "(전체 문항이 하나의 그룹으로 합쳐졌습니다.)\n\n"
            "필요 시 [↺ 정렬 취소] 버튼으로 이전 그룹 구조를 복원할 수 있습니다."
        )

    def _undo_sort(self):
        """직전 _apply_sort 1회분만 되돌림 — batch 구조 + 순서 복원."""
        snapshot = getattr(self, "_pre_sort_batches", None)
        if not snapshot:
            messagebox.showinfo("안내", "되돌릴 정렬 작업이 없습니다.")
            return
        self.problem_batches = [list(b) for b in snapshot]
        self._pre_sort_batches = None
        self._refresh_step_3_list()
        try:
            if hasattr(self, "_sort_undo_btn") and self._sort_undo_btn.winfo_exists():
                self._sort_undo_btn.config(state="disabled")
        except Exception:
            pass
        messagebox.showinfo("복원 완료", "정렬 이전 그룹 구조로 복원했습니다.")

    def _refresh_step_3_list(self):
        # Level mapping
        level_map = {"A": "최상", "B": "상", "C": "중", "D": "하"}
        
        for item in self.p_tree.get_children():
            self.p_tree.delete(item)
            
        # Flatten batches for display
        all_problems = [p for batch in self.problem_batches for p in batch]
            
        for idx, p in enumerate(all_problems):
            # 출처: 파일명(확장자 제거) + 번호
            fname = (p.get('file_name') or "").replace(".hwp", "").replace(".HWP", "")
            num = p.get('endnote_index') or "?"
            source_str = f"{fname}  {num}번"
            
            # Unit Name
            # Priority: middle_unit (if name) > lookup by unit_code
            unit_val = p.get('middle_unit') or ""
            unit_code = p.get('unit_code') or ""
            
            # Try to get version for lookup
            # 2015→2022 매핑된 문제는 unit_code가 이미 2022코드이므로 "2022"로 조회
            curr = p.get('curriculum', '')
            mapped = p.get('mapped_unit_code') or ""
            if mapped:
                version = "2022"  # 매핑된 2015 문제: unit_code는 2022 코드
            else:
                version = "2015" if "2015" in curr else "2022" if "2022" in curr else ""

            if not unit_val or unit_val == unit_code:
                # Try lookup if name is missing or looks like code
                if unit_code:
                     found_name = self._find_unit_name(unit_code, version)
                     if found_name: unit_val = found_name

            # Level
            lvl_code = p.get('difficulty') or ""
            lvl = level_map.get(lvl_code, lvl_code) # Fallback to code if not in map
            
            # Type
            typ = p.get('problem_type') or ""
            
            self.p_tree.insert("", "end", values=(idx+1, source_str, unit_val, lvl, typ, "[삭제]"), tags=(p['id'],))

    def _on_ptree_click(self, event):
        """Handle Delete button click"""
        region = self.p_tree.identify("region", event.x, event.y)
        if region == "cell":
            col = self.p_tree.identify_column(event.x)
            if col == "#6": # Delete column
                item = self.p_tree.identify_row(event.y)
                if not item: return
                tags = self.p_tree.item(item, "tags")
                if not tags: return
                p_id = tags[0]

                # Remove from batches (id 타입 정규화: tkinter tags는 str, p['id']는 int|str 가능)
                for batch in self.problem_batches:
                    for p in batch:
                        if str(p.get('id')) == str(p_id):
                            batch.remove(p)
                            break
                
                # Cleanup empty batches
                self.problem_batches = [b for b in self.problem_batches if b]
                
                self._refresh_step_3_list()

    def _on_prev_click(self):
        """Undo last addition or Reset"""
        if not self.problem_batches:
            self._back_to_step_2_reset()
            return

        # If we have multiple batches, we just want to undo the last one
        if len(self.problem_batches) > 1:
            # Removed the annoying popup for smooth UX, or keep it optional
            # User feedback: "이전 누르면 초기화할 거냐고 물어 본다." -> They probably dislike the full reset fear.
            if messagebox.askyesno("확인", "직전에 추가한 문항들을 취소하고 다시 문제 설정을 하시겠습니까?"):
                self.problem_batches.pop() # Remove the last added batch
                self.next_step3_mode = "append" # We are still in append mode relative to the remaining batches
                self._build_step_2_ui()
        else:
            # Only 1 batch exists (Initial state)
            # Going back means re-doing the first batch.
            # We can skip the question if it's just 1 batch, or make it softer.
            if messagebox.askyesno("확인", "현재 생성된 문항을 초기화하고 다시 설정하시겠습니까?"):
                self.problem_batches = []
                self.next_step3_mode = "new"
                self._build_step_2_ui()

    def _on_random_add_click(self):
        """Go to Step 2 to Append — 이전 필터 세팅 전체 유지"""
        self.next_step3_mode = "append"
        self._save_step2_filter_state()   # ① 현재 필터 상태 백업
        self._build_step_2_ui()           # ② Step 2 UI 재구성 (기본값으로)
        self._restore_step2_filter_state() # ③ 백업된 필터 복원 + 렌더링

    def _back_to_step_2_reset(self):
        """Discard current list and go back to Step 2"""
        if messagebox.askyesno("확인", "현재 생성된 문항 목록이 초기화됩니다.\n돌아가시겠습니까?"):
            self.problem_batches = []
            self.next_step3_mode = "new"
            # 새 시험지 시작 → 일회성 제외 리셋
            self._oneshot_excluded_problem_ids = set()
            self._oneshot_excluded_test_ids = set()
            self._build_step_2_ui()

    def _back_to_step_2_append(self):
        """Keep current list and go back to Step 2 to add more"""
        self.next_step3_mode = "append"
        self._build_step_2_ui()

    def _collect_selected_units(self, item, selected_list):
        """Recursively collects checked units"""
        tags = self.unit_tree.item(item, "tags")
        if "checked" in tags:
             if "large" in tags or "medium" in tags:
                 selected_list.append(item)
        
        for child in self.unit_tree.get_children(item):
            self._collect_selected_units(child, selected_list)

    # Filter Group 2: School Name
    def _distribute_evenly(self):
        """Distributes total quantity evenly across VISIBLE rows"""
        try:
            val = self.entry_total_qty.get().strip()
            if not val: return
            total_qty = int(val)
        except ValueError:
            messagebox.showwarning("입력 오류", "숫자만 입력해주세요.")
            return

        if total_qty > 200:
            messagebox.showwarning("문항 수 제한", "최대 200문제까지만 출제 가능합니다.")
            self.entry_total_qty.delete(0, "end")
            self.entry_total_qty.insert(0, "200")
            total_qty = 200

        visible_entries = list(self.alloc_entries.items()) # List of (key, entry)
        if not visible_entries: return
        
        count = len(visible_entries)
        if count == 0: return

        base_qty = total_qty // count
        remainder = total_qty % count
        
        for idx, (key, entry) in enumerate(visible_entries):
            qty = base_qty + (1 if idx < remainder else 0)
            entry.delete(0, "end")
            entry.insert(0, str(qty))
            
        self._update_total_label()

    def _distribute_ratio(self):
        """Distributes total quantity based on available counts ratio"""
        try:
            val = self.entry_total_qty.get().strip()
            if not val: return
            total_qty = int(val)
        except ValueError:
            messagebox.showwarning("입력 오류", "숫자만 입력해주세요.")
            return

        if total_qty > 200:
            messagebox.showwarning("문항 수 제한", "최대 200문제까지만 출제 가능합니다.")
            self.entry_total_qty.delete(0, "end")
            self.entry_total_qty.insert(0, "200")
            total_qty = 200

        visible_keys = list(self.alloc_entries.keys())
        if not visible_keys: return
        
        total_avail = sum(self.avail_counts.get(k, 0) for k in visible_keys)
        if total_avail == 0: return # Avoid division by zero
        
        current_sum = 0
        allocations = {}
        
        # 1. Calculate ratios
        sorted_keys = sorted(visible_keys, key=lambda k: self.avail_counts.get(k, 0), reverse=True)
        
        for key in sorted_keys:
            avail = self.avail_counts.get(key, 0)
            ratio = avail / total_avail
            qty = int(total_qty * ratio)
            allocations[key] = qty
            current_sum += qty
            
        # 2. Distribute remainder
        remainder = total_qty - current_sum
        for i in range(remainder):
             if i < len(sorted_keys):
                k = sorted_keys[i]
                allocations[k] += 1
            
        # 3. Apply
        for key, qty in allocations.items():
            entry = self.alloc_entries[key]
            entry.delete(0, "end")
            entry.insert(0, str(qty))
            
        self._update_total_label()

    def _update_total_label(self, event=None):
        """Updates the total label by summing all visible entries"""
        total = 0
        for entry in self.alloc_entries.values():
            try:
                # Handle empty string as 0
                val = entry.get().strip()
                if not val: val = "0"
                total += int(val)
            except ValueError:
                pass
        if total > 200:
            self.lbl_step2_total.config(text=f"{total} (초과!)", fg="red")
        else:
            self.lbl_step2_total.config(text=str(total), fg="#1976d2")

    def _start_random_generation(self):
        """
        [Legacy/Placeholder] 
        Final Action: Collect all constraints, sample problems, and start the solver.
        This logic will be migrated to Step 3.
        """
        self.log("Step 3(시험지 생성) 단계에서 구현될 예정입니다.")
        pass

    # def _save_and_start_solver(self, selected_problems):
    #     ... (Legacy logic removed/commented for cleanup) ...

    # --- Step 4: Test Storage & Finalize ---

    def _go_to_step_4(self):
        """Transitions to Step 4: Test Storage & Finalize"""
        if not hasattr(self, 'problem_batches') or not self.problem_batches:
            messagebox.showwarning("안내", "출제할 문항이 없습니다.")
            return

        # Flatten problems for final view
        self.final_problems = [p for batch in self.problem_batches for p in batch]
        self.is_step4_saved = False # Reset save flag
        
        # Clear container
        for widget in self.random_container.winfo_children():
            widget.destroy()
            
        self._build_step_4_ui()

    def _build_step_4_ui(self):
        """Builds Step 4 UI: Explorer(Left) + Preview/Actions(Right)"""
        # 1. Top Navbar
        nav_bar = tk.Frame(self.random_container, bg="white", pady=10, padx=20)
        nav_bar.pack(fill="x")
        
        tk.Label(nav_bar, text="시험지 저장 및 출제", font=("Segoe UI", 16, "bold"), bg="white", fg="#333333").pack(side="left")

        # Buttons (Right aligned)
        btn_frame = tk.Frame(nav_bar, bg="white")
        btn_frame.pack(side="right")
        
        tk.Button(btn_frame, text="마침", command=self._on_step4_finish, bg="#555", fg="white", font=FONT_MAIN, width=8).pack(side="right", padx=5)
        tk.Button(btn_frame, text="이전", command=self._back_to_step_3, bg="#f5f5f5", fg="#333333", font=FONT_MAIN, width=8).pack(side="right", padx=5)
        
        tk.Frame(btn_frame, width=20, bg="white").pack(side="right")
        
        tk.Button(btn_frame, text="테스트출제", command=self._generate_hwp_step4, 
                  bg="#1976d2", fg="white", font=("Segoe UI", 10, "bold"), padx=10).pack(side="right", padx=5)
                  
        tk.Button(btn_frame, text="테스트저장", command=self._open_save_dialog_step4, 
                  bg="white", fg="#1976d2", font=("Segoe UI", 10, "bold"), padx=10).pack(side="right", padx=5)
        
        # 1.5 Folder Selection (Surian Style) - Persistent in Step 4
        folder_frame = tk.Frame(self.random_container, bg="white", padx=20, pady=5)
        folder_frame.pack(fill="x")
        
        tk.Label(folder_frame, text="원본 HWP 폴더:", font=("Segoe UI", 10, "bold"), bg="white", fg="#333").pack(side="left", padx=(0, 10))
        tk.Entry(folder_frame, textvariable=self.source_hwp_dir, bg="#f5f5f5", fg="#333", 
                 insertbackground="black", bd=1, relief="solid", font=FONT_MAIN, width=60).pack(side="left", padx=5)
        tk.Button(folder_frame, text="찾아보기", command=self._browse_source_dir,
                  bg="#e0e0e0", fg="#333", font=FONT_MAIN, relief="flat", padx=10).pack(side="left", padx=5)
        
        # 2. Main Content (Paned)
        content_paned = tk.PanedWindow(self.random_container, orient="horizontal", bg="#dddddd", sashwidth=2)
        content_paned.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Left Panel (Explorer)
        self.step4_left = tk.Frame(content_paned, bg="white")
        content_paned.add(self.step4_left, minsize=300, width=350)
        
        # Right Panel (Preview)
        self.step4_right = tk.Frame(content_paned, bg="white")
        content_paned.add(self.step4_right, minsize=600, stretch="always")
        
        self._build_step_4_explorer()
        self._build_step_4_preview()
        
    def _build_step_4_explorer(self):
        """Builds the Folder/Test Explorer on the left"""
        # Header
        tk.Label(self.step4_left, text="내 시험지 보관함", font=FONT_BOLD, bg="#f5f5f5", pady=5).pack(fill="x")
        
        # Tool Bar (New Folder, key Delete)
        tools = tk.Frame(self.step4_left, bg="white", pady=2)
        tools.pack(fill="x")
        tk.Button(tools, text="+ 새 폴더", command=self._create_new_folder, bg="#f0f0f0", relief="flat", font=FONT_MAIN).pack(side="right", padx=5)
        
        # Treeview
        # Columns: #0 is Name.
        self.ex_tree = ttk.Treeview(self.step4_left, show="tree", selectmode="browse", style="Surian.Treeview")
        
        scrollbar = ttk.Scrollbar(self.step4_left, orient="vertical", command=self.ex_tree.yview)
        self.ex_tree.configure(yscrollcommand=scrollbar.set)
        
        self.ex_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind select
        self.ex_tree.bind("<<TreeviewSelect>>", self._on_step4_folder_select)
        
        # Load Data
        self._refresh_step_4_explorer()
        
    def _refresh_step_4_explorer(self):
        """Loads folders and tests from DB (계층 구조 표시)"""
        for item in self.ex_tree.get_children():
            self.ex_tree.delete(item)

        ICON_FOLDER = "📁"
        ICON_TEST = "📄"

        # Root Node
        root_node = self.ex_tree.insert("", "end", text=" 내 저장소 (Root)", open=True, tags=("root",))

        folders = self.db_engine.get_folders(self.current_user_id)
        folder_map = {}  # id -> tree node iid

        # 계층 삽입 (재귀)
        def _insert_folder_children(parent_id, tree_parent):
            children = [f for f in folders if f.get("parent_id") == parent_id]
            children.sort(key=lambda x: x.get("name", ""))
            for f in children:
                icon = "🔒" if f.get("is_protected") else ICON_FOLDER
                f_node = self.ex_tree.insert(
                    tree_parent, "end",
                    text=f" {icon} {f['name']}",
                    open=True,
                    tags=("folder", f['id'])
                )
                folder_map[f['id']] = f_node
                _insert_folder_children(f['id'], f_node)

        _insert_folder_children(None, root_node)

        # Root Tests
        root_tests = self.db_engine.get_tests(None, self.current_user_id)
        for t in root_tests:
            self.ex_tree.insert(root_node, "end", text=f" {ICON_TEST} {t['title']}", tags=("test", t['id']))

        # Folder Tests
        for f_id, f_node in folder_map.items():
            f_tests = self.db_engine.get_tests(f_id, self.current_user_id)
            for t in f_tests:
                self.ex_tree.insert(f_node, "end", text=f" {ICON_TEST} {t['title']}", tags=("test", t['id']))

    def _create_new_folder(self):
        """Dialog to create new folder"""
        name = tk.simpledialog.askstring("새 폴더", "폴더 이름을 입력하세요:")
        if name:
            res = self.db_engine.create_folder(name, self.current_user_id)
            if res['success']:
                self._refresh_step_4_explorer()
            else:
                messagebox.showerror("오류", res['message'])

    def _on_step4_folder_select(self, event):
        """Handle selection in Explorer"""
        sel = self.ex_tree.selection()
        if not sel: return
        item = sel[0]
        tags = self.ex_tree.item(item, "tags")
        
        if "test" in tags and len(tags) > 1:
            test_id = tags[1]
            # Load the selected saved test into the preview panel
            try:
                test_data = self.db_engine.get_test_detail(test_id, self.current_user_id)
                if test_data and test_data.get('problems'):
                    if messagebox.askyesno(
                        "저장된 시험지 불러오기",
                        f"\'{test_data.get('title', '시험지')}\'를 불러오시겠습니까?\n"
                        "현재 작업 중인 문항 목록이 교체됩니다."
                    ):
                        self.final_problems = test_data['problems']
                        self._refresh_step_4_preview_list()
                        self.lbl_s4_title.config(text=test_data.get('title', '불러온 시험지'))
                        self.lbl_s4_summary.config(
                            text=f"총 {len(self.final_problems)}문항 | {test_data.get('unit_summary', '')}"
                        )
            except Exception as ex:
                messagebox.showerror("오류", f"시험지를 불러오는 중 오류가 발생했습니다:\n{ex}")

    def _build_step_4_preview(self):
        """Right Panel: Preview & Actions"""
        # 1. Info Header
        info_frame = tk.Frame(self.step4_right, bg="white", pady=10, padx=10, bd=1, relief="solid")
        info_frame.pack(fill="x", padx=10, pady=10)
        
        self.lbl_s4_title = tk.Label(info_frame, text="현재 작업 중인 시험지", font=("Segoe UI", 12, "bold"), bg="white")
        self.lbl_s4_title.pack(anchor="w")
        
        count = len(self.final_problems)
        self.lbl_s4_summary = tk.Label(info_frame, text=f"총 {count}문항 | 단원: (자동요약)", font=("Segoe UI", 10), bg="white", fg="#555")
        self.lbl_s4_summary.pack(anchor="w")
        
        # 2. Problem List
        list_frame = tk.Frame(self.step4_right, bg="white", padx=10)
        list_frame.pack(fill="both", expand=True)
        
        cols = ("no", "info", "unit", "type")
        self.s4_tree = ttk.Treeview(list_frame, columns=cols, show="headings", style="Surian.Treeview")
        
        self.s4_tree.heading("no", text="No")
        self.s4_tree.heading("info", text="문항 정보")
        self.s4_tree.heading("unit", text="단원")
        self.s4_tree.heading("type", text="형식")
        
        self.s4_tree.column("no", width=40, anchor="center")
        self.s4_tree.column("info", width=300, anchor="w")
        self.s4_tree.column("unit", width=100, anchor="center")
        self.s4_tree.column("type", width=60, anchor="center")
        
        sc = ttk.Scrollbar(list_frame, orient="vertical", command=self.s4_tree.yview)
        self.s4_tree.configure(yscrollcommand=sc.set)
        
        self.s4_tree.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")
        
        # Populate preview list
        self._refresh_step_4_preview_list()

    def _refresh_step_4_preview_list(self):
        for item in self.s4_tree.get_children():
            self.s4_tree.delete(item)
            
        for idx, p in enumerate(self.final_problems):
            # 출처: 파일명(확장자 제거) + 번호
            _fname = (p.get('file_name','') or "").replace(".hwp","").replace(".HWP","")
            _num   = p.get('endnote_index','')
            info = f"{_fname}  {_num}번"
            unit = p.get('middle_unit') or p.get('unit_code') or ""
            typ = p.get('problem_type') or ""
            self.s4_tree.insert("", "end", values=(idx+1, info, unit, typ))

    def _open_save_dialog_step4(self):
        """Save Dialog"""
        if not self.final_problems: return
        
        dlg = tk.Toplevel(self.root)
        dlg.title("테스트 저장")
        dlg.geometry("400x350")
        dlg.resizable(False, False)
        
        # Center
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 175
        dlg.geometry(f"+{x}+{y}")
        
        container = tk.Frame(dlg, padx=20, pady=20)
        container.pack(fill="both", expand=True)
        
        # 1. Test Name
        tk.Label(container, text="테스트 이름", font=FONT_BOLD).pack(anchor="w")
        from datetime import datetime
        default_title = f"새 테스트 {datetime.now().strftime('%Y-%m-%d')}"
        entry_title = tk.Entry(container, font=FONT_MAIN)
        entry_title.pack(fill="x", pady=(0, 10))
        entry_title.insert(0, default_title)
        
        # 2. Units Summary
        tk.Label(container, text="출제 단원 (요약)", font=FONT_BOLD).pack(anchor="w")
        # Auto-summarize
        units = set([p.get('middle_unit', '') for p in self.final_problems if p.get('middle_unit')])
        if not units: units = set([p.get('large_unit', 'Unknown') for p in self.final_problems])
        unit_summary = f"{list(units)[0]} 외 {len(units)-1}개" if len(units) > 1 else (list(units)[0] if units else "미지정")
        
        entry_unit = tk.Entry(container, font=FONT_MAIN)
        entry_unit.pack(fill="x", pady=(0, 10))
        entry_unit.insert(0, unit_summary)
        
        # 3. Folder Select
        tk.Label(container, text="저장 폴더", font=FONT_BOLD).pack(anchor="w")

        folder_opts, folder_ids = self._build_folder_options()

        cbo_folder = ttk.Combobox(container, values=folder_opts, state="readonly")
        cbo_folder.pack(fill="x", pady=(0, 5))
        cbo_folder.current(0)

        def _add_folder_local():
            name = tk.simpledialog.askstring("새 폴더", "폴더 이름:")
            if name:
                try:
                    res = self.db_engine.create_folder(name, self.current_user_id)
                except Exception as e:
                    messagebox.showerror("오류", f"폴더 생성 실패:\n{e}")
                    return
                if res and res.get('success'):
                    f_opts, f_ids = self._build_folder_options()
                    cbo_folder['values'] = f_opts
                    new_idx = next((i for i, fid in enumerate(f_ids) if fid == res.get('id')), -1)
                    if new_idx != -1:
                        cbo_folder.current(new_idx)
                    nonlocal folder_ids
                    folder_ids = f_ids
                else:
                    messagebox.showerror("오류", (res or {}).get('message', '알 수 없는 오류'))

        tk.Button(container, text="+ 새 폴더 만들기", command=_add_folder_local, bg="#f0f0f0").pack(anchor="e", pady=(0, 15))
        
        # Save Action
        def _do_save():
            title = entry_title.get().strip()
            summary = entry_unit.get().strip()
            if not title:
                messagebox.showwarning("필수", "테스트 이름을 입력하세요.")
                return
                
            idx = cbo_folder.current()
            if idx < 0: idx = 0
            dir_id = folder_ids[idx]
            
            p_ids = [p['id'] for p in self.final_problems]
            
            data = {
                "title": title,
                "unit_summary": summary,
                "directory_id": dir_id,
                "problem_ids": p_ids,
                "metadata": {} # Add options like paper layout later
            }
            
            res = self.db_engine.save_test(data, self.current_user_id)
            if res['success']:
                messagebox.showinfo("저장 완료", "시험지가 안전하게 저장되었습니다.")
                self.is_step4_saved = True # Flag
                # ★ 제목/단원 저장 (출제 시 HWP 치환에 사용)
                self.saved_exam_title = title
                self.saved_exam_unit = summary
                dlg.destroy()
                self._refresh_step_4_explorer() # Update Left Panel
            else:
                messagebox.showerror("저장 실패", res['message'])

        # Buttons
        btn_area = tk.Frame(dlg, pady=10)
        btn_area.pack(fill="x", side="bottom")
        tk.Button(btn_area, text="저장", command=_do_save, bg="#1976d2", fg="white", width=10).pack(side="right", padx=10)
        tk.Button(btn_area, text="취소", command=dlg.destroy, width=8).pack(side="right")

    def _generate_hwp_step4(self):
        """Open Generate Dialog"""
        if not self.final_problems:
            messagebox.showwarning("안내", "출제할 문항이 없습니다.")
            return

        # ★ 저장하지 않은 경우에만 제목/단원 초기화
        if not getattr(self, 'is_step4_saved', False):
            self.saved_exam_title = ''
            self.saved_exam_unit  = ''

        # ★ 값을 명시적으로 파라미터로 전달 (전역속성 오염 방지)
        self._open_generate_dialog(
            exam_title=getattr(self, 'saved_exam_title', ''),
            exam_unit=getattr(self, 'saved_exam_unit',  '')
        )

    def _open_generate_dialog(self, exam_title='', exam_unit=''):
        """
        Dialog for HWP Generation options.
        - 제목/단원 입력 Entry 포함 (사용자가 확인·수정 가능)
        - exam_title/exam_unit: 파라미터로 직접 전달 (전역속성 의존 제거)
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("테스트 출제")
        dlg.geometry("420x320")
        dlg.resizable(False, False)

        # Center
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 210
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 160
        dlg.geometry(f"+{x}+{y}")

        container = tk.Frame(dlg, padx=20, pady=15)
        container.pack(fill="both", expand=True)

        # ── 제목 입력 ──────────────────────────────────────────────
        tk.Label(container, text="시험지 제목 (HWP 내 표시)", font=FONT_BOLD).pack(anchor="w")
        entry_title = tk.Entry(container, font=FONT_MAIN)
        entry_title.pack(fill="x", pady=(2, 8))
        entry_title.insert(0, exam_title or '')

        # ── 단원 입력 ──────────────────────────────────────────────
        tk.Label(container, text="단원 (HWP 내 표시)", font=FONT_BOLD).pack(anchor="w")
        entry_unit = tk.Entry(container, font=FONT_MAIN)
        entry_unit.pack(fill="x", pady=(2, 12))
        entry_unit.insert(0, exam_unit or '')

        # ── 태그 제외 옵션 (내신기출 전용) ────────────────────────
        has_naesin = any(
            p.get('source', '') in ('NAESIN_A', 'NAESIN_N')
            for p in (getattr(self, 'final_problems', None) or [])
        )
        var_exclude_tags = tk.BooleanVar(value=False)  # 기본: 태그 포함
        if has_naesin:
            chk_exclude = tk.Checkbutton(
                container, text="출제정보 태그 미포함 (내신기출 전용)",
                variable=var_exclude_tags, font=FONT_MAIN
            )
            chk_exclude.pack(anchor="w", pady=2)

        # Action
        def _do_generate():
            _final_title = entry_title.get().strip()
            _final_unit  = entry_unit.get().strip()
            exclude_tags = var_exclude_tags.get() if has_naesin else False
            dlg.destroy()
            self._start_hwp_generation_process(
                exclude_tags, fast_answer_key=False,
                _exam_title=_final_title, _exam_unit=_final_unit
            )

        # Buttons
        btn_area = tk.Frame(dlg, pady=10)
        btn_area.pack(fill="x", side="bottom")

        tk.Button(btn_area, text="출제하기", command=_do_generate, bg="#1976d2", fg="white", width=12, font=("Segoe UI", 10, "bold")).pack(side="right", padx=20)
        tk.Button(btn_area, text="취소", command=dlg.destroy, width=8).pack(side="right")

    def _start_hwp_generation_process(self, exclude_tags=False, fast_answer_key=True, _exam_title=None, _exam_unit=None):
        """
        Actual HWP Generation Logic (Threaded)
        _exam_title/_exam_unit: 클로저에서 직접 전달된 값 (없으면 saved_exam_* 속성에서 읽음)
        """
        # 기본 파일명 자동 생성: 시험지이름[단원].hwp
        # _exam_title/unit 우선, 없으면 saved_exam_* 속성 fallback
        _title = (_exam_title if _exam_title is not None else (getattr(self, 'saved_exam_title', '') or '')).strip()
        _unit  = (_exam_unit  if _exam_unit  is not None else (getattr(self, 'saved_exam_unit',  '') or '')).strip()
        print(f"[GEN] _start_hwp_gen → title={_title!r}, unit={_unit!r}")
        if not _title and hasattr(self, 'final_problems') and self.final_problems:
            # 저장 안 했을 경우 즉석 생성
            from datetime import datetime
            _title = f"시험지_{datetime.now().strftime('%Y%m%d')}"
        if not _unit and hasattr(self, 'final_problems') and self.final_problems:
            _units = set(p.get('middle_unit', '') or p.get('large_unit', '') for p in self.final_problems)
            _units.discard('')
            if _units:
                _u = sorted(_units)
                _unit = f"{_u[0]} 외 {len(_u)-1}개" if len(_u) > 1 else _u[0]
        if _title and _unit:
            _default_name = f"{_title}[{_unit}]"
        elif _title:
            _default_name = _title
        else:
            _default_name = "시험지"
        # 파일명에 사용 불가 문자 제거
        import re as _re
        _default_name = _re.sub(r'[\\/:*?"<>|]', '_', _default_name)

        # Select Save Path
        file_path = filedialog.asksaveasfilename(
            defaultextension=".hwp",
            filetypes=[("HWP Files", "*.hwp")],
            title="시험지 저장 위치 선택",
            initialfile=_default_name
        )
        if not file_path: return
        
        # [FIX] Capture source_dir in MAIN THREAD (Tkinter Safety)
        source_dir = self.source_hwp_dir.get()
        
        # Show Progress
        self.progress_win = tk.Toplevel(self.root)
        self.progress_win.title("출제 진행 중")
        self.progress_win.geometry("400x150")
        self.progress_win.resizable(False, False)
        
        # Center Progress
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
        self.progress_win.geometry(f"+{x}+{y}")
        
        self.progress_var = tk.DoubleVar()
        self.progress_label = tk.StringVar(value="엔진 준비 중...")
        
        tk.Label(self.progress_win, textvariable=self.progress_label, pady=20, font=FONT_MAIN).pack()
        ttk.Progressbar(self.progress_win, variable=self.progress_var, maximum=100, length=300).pack()
        
        # Run in Thread
        # [BUG FIX] self.final_problems를 직접 넘기지 않고 스냅샷을 만들어 전달
        # → 스레드 실행 중 self.final_problems가 바뀌어도 엉뚱한 문제 출제 방지
        _problems_snapshot = list(self.final_problems)
        import threading
        t = threading.Thread(target=self._run_hwp_thread, args=(file_path, exclude_tags, fast_answer_key, source_dir, _title, _unit, _problems_snapshot))
        t.daemon = True
        t.start()

    def _run_hwp_thread(self, target_path, exclude_tags, fast_answer_key, source_dir, exam_title="", exam_unit="", problems_snapshot=None):
        # [DEBUG LOGGER]
        def dlog(msg):
            with open(r"g:\문제은행\문제은행2\gui_debug.log", "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

        dlog("STARTED: _run_hwp_thread")
        dlog(f"Target: {target_path}")
        dlog(f"Source Dir: {source_dir}")
        dlog(f"exam_title={exam_title!r}, exam_unit={exam_unit!r}")

        # [BUG FIX] 스냅샷 우선 사용 (전달된 경우), 없으면 self.final_problems 복사
        _problems = problems_snapshot if problems_snapshot is not None else list(self.final_problems)
        dlog(f"problems source: {'snapshot' if problems_snapshot is not None else 'self.final_problems fallback'}")

        try:
            from backend.hwp_generator import HWPGenerator

            import re as _re
            _progress_re = _re.compile(r'(\d+)\s*/\s*(\d+)')

            def update_progress(msg):
                # 메시지에서 "X/Y" 패턴 추출 → 진행률 바 갱신
                m = _progress_re.search(msg or "")
                if m:
                    try:
                        cur = int(m.group(1))
                        tot = int(m.group(2))
                        if tot > 0:
                            pct = max(0.0, min(100.0, cur * 100.0 / tot))
                            self.root.after(0, lambda p=pct: self.progress_var.set(p))
                    except Exception:
                        pass
                self.root.after(0, lambda: self.progress_label.set(msg))

            generator = HWPGenerator()

            # [FIX] Ensure file paths are absolute (Like in Tab 2)
            validated_problems = []
            missing_files = set()
            _validate_skipped = []  # validate에서 걸러진 문제 (request_index 1-base)

            dlog(f"Total Problems to process: {len(_problems)}")

            for i, p in enumerate(_problems):
                # Try to use existing path if valid
                fpath = p.get('file_path')
                fname = p.get('file_name')
                pid = p.get('id')

                dlog(f"[Prob {i}] ID: {pid}, File: {fname}, Path: {fpath}")

                # First check if explicit path works
                if fpath and os.path.exists(fpath):
                    validated_problems.append(p)
                    dlog(f"  -> Valid path found: {fpath}")
                    continue

                # Not valid, try to resolve using source_dir
                if fname:
                    found = self._find_source_hwp(fname, user_dir=source_dir)
                    if found:
                        p['file_path'] = found
                        validated_problems.append(p)
                        dlog(f"  -> Resolved path via search: {found}")
                    else:
                        print(f"[Warning] Source file not found: {fname}")
                        missing_files.add(fname)
                        _validate_skipped.append({
                            'id': pid or '?',
                            'file_name': fname,
                            'request_index': i + 1,
                            'reason': f'파일 없음: {fname}',
                        })
                        dlog(f"  -> FAILED to find file: {fname}")
                else:
                    print(f"[Warning] No file name for problem {p.get('id')}")
                    _validate_skipped.append({
                        'id': pid or '?',
                        'file_name': '(없음)',
                        'request_index': i + 1,
                        'reason': '파일명 없음',
                    })
                    dlog(f"  -> No filename for problem")
            
            dlog(f"Validated Problems: {len(validated_problems)}")
            
            if not validated_problems:
                msg = "유효한 원본 파일을 찾을 수 없습니다.\n"
                if missing_files:
                    msg += f"\n[찾지 못한 파일 예시]\n" + "\n".join(list(missing_files)[:3])
                    if len(missing_files) > 3: msg += f"\n...외 {len(missing_files)-3}개"
                
                msg += "\n\n원본 HWP 폴더 설정을 확인해주세요."
                
                dlog("ERROR: No validated problems. Aborting.")
                self.root.after(0, lambda: messagebox.showerror("오류", msg))
                self.root.after(0, self.progress_win.destroy)
                return

            # Pass params to generate_exam
            dlog("Calling generator.generate_exam...")
            gen_result = generator.generate_exam(
                target_path,
                validated_problems,
                progress_callback=update_progress,
                exclude_tags=exclude_tags,
                stealth_mode=self.stealth_var.get(),
                fast_answer_key=fast_answer_key,
                db=self.db_engine,
                exam_title=exam_title,
                exam_unit=exam_unit
            )
            dlog("Generator finished successfully.")
            if gen_result:
                dlog(f"출제 결과: 목표={gen_result.get('total')}, 성공={gen_result.get('success')}, "
                     f"누락문제={len(gen_result.get('skipped_problems',[]))}, "
                     f"실패파일={len(gen_result.get('skipped_files',[]))}")

            # 실제 파일 생성 여부 확인 (generate_exam 내부 예외는 흡수되므로 파일로 판단)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 0:

                # ── 출제 불일치 경고 ─────────────────────────────────────
                # 비교 기준: 원본 요청 수(_problems) vs 최종 출제 수
                # - validate 단계에서 걸러진 문제 + generate_exam 중 스킵된 문제 합산
                _original_total = len(_problems)
                _gen_skipped = gen_result.get('skipped_problems', []) if gen_result else []
                _all_skipped = list(_validate_skipped) + list(_gen_skipped)
                _success_final = gen_result.get('success', 0) if gen_result else 0

                if _original_total > 0 and _success_final < _original_total:
                    _missed = _original_total - _success_final
                    _missed_nums = sorted(
                        sp.get('request_index') for sp in _all_skipped
                        if sp.get('request_index')
                    )
                    _nums_str = ", ".join(str(n) for n in _missed_nums) or "(번호 추적 실패)"
                    dlog(f"[WARN] 출제 불일치: 누락 {_missed}문제 — 번호: {_nums_str}")

                    _msg = (
                        f"목표 {_original_total}문제 → 실제 {_success_final}문제 출제됨\n\n"
                        f"누락된 문제 번호: {_nums_str}\n\n"
                        f"정답지 작업 전 문제 번호를 확인해 주세요."
                    )
                    self.root.after(
                        0,
                        lambda m=_msg: messagebox.showwarning("⚠  출제 불일치", m)
                    )

                self.root.after(0, lambda: messagebox.showinfo("완료", "시험지 생성이 완료되었습니다."))
                self.root.after(0, self.progress_win.destroy)
                def ask_open():
                    if messagebox.askyesno("확인", "생성된 파일을 여시겠습니까?"):
                        os.startfile(target_path)
                self.root.after(0, ask_open)
            else:
                dlog("ERROR: Output file not found or empty after generate_exam.")
                self.root.after(0, lambda: messagebox.showerror("오류", "시험지 생성에 실패했습니다.\n출력 파일이 생성되지 않았습니다.\ngui_debug.log를 확인해 주세요."))
                self.root.after(0, self.progress_win.destroy)
                
        except Exception as e:
            err = str(e)
            import traceback
            traceback.print_exc()
            dlog(f"EXCEPTION: {err}")
            dlog(traceback.format_exc())
            self.root.after(0, lambda: messagebox.showerror("오류", f"출제 중 오류 발생:\n{err}"))
            self.root.after(0, self.progress_win.destroy)


        
    def _on_step4_finish(self):
        """Finish button"""
        if not getattr(self, 'is_step4_saved', False):
            if not messagebox.askyesno("종료 확인", "저장되지 않은 시험지입니다.\n저장하지 않고 종료하시겠습니까?"):
                return
        
        # Reset and Close
        self._close_random_tab()

    def _back_to_step_3(self):
        """Transitions back to Step 3"""
        # Step 4 relies on broken-down batches? No, it uses final_problems.
        # Step 3 uses problem_batches.
        # We assume problem_batches is still intact.
        
        if not hasattr(self, 'problem_batches') or not self.problem_batches:
            # Fallback if batches lost?
            # Reconstruct batches from final_problems?
            # If final_problems exist, make it 1 batch.
            if hasattr(self, 'final_problems') and self.final_problems:
                self.problem_batches = [self.final_problems]
            else:
                 messagebox.showerror("오류", "이전 단계로 돌아갈 데이터가 없습니다.")
                 return

        # Clear container
        for widget in self.random_container.winfo_children():
            widget.destroy()
            
        self._build_step_3_ui()

    # --- Tab 4: Management (Enhanced v2) ---
    def _build_management_tab(self):
        """Builds the Enhanced Problem Management Interface with Exclusion Support"""
        # Layout: 
        # Top: Filters (including Curriculum & Excluded Checkbox)
        # Body: PanedWindow (Split View)
        #   Left: Files Tree (Grouped by School)
        #   Right: Problem List (List of problems in selected file)
        # Bottom: Action Bar
        
        # 1. Filter Bar
        filter_frame = tk.Frame(self.tab_manage, bg="white", pady=15, padx=15)
        filter_frame.pack(fill="x")

        tk.Label(filter_frame, text="문제 관리 (시험지별 통합 관리)", font=("Segoe UI", 14, "bold"), bg="white", fg="#333").pack(anchor="w", pady=(0, 10))

        # 소스 선택
        src_row = tk.Frame(filter_frame, bg="white")
        src_row.pack(fill="x", pady=(0, 6))
        tk.Label(src_row, text="소스:", font=FONT_BOLD, bg="white", fg="#333").pack(side="left", padx=(0, 8))
        MGR_SOURCES = [
            ("NAESIN_A",         "내신기출A"),
            ("NAESIN_N",         "내신기출B"),
            ("SUNEUNG_SPECIAL",  "수능특강"),
            ("SUNEUNG_COMPLETE", "수능완성"),
            ("MOCK_EXAM",        "모의고사"),
        ]
        self.mgr_source_var = tk.StringVar(value="NAESIN_A")
        for code, label in MGR_SOURCES:
            tk.Radiobutton(src_row, text=label, variable=self.mgr_source_var, value=code,
                           bg="white", font=FONT_MAIN, command=self._mgr_on_source_change,
                           indicatoron=False, padx=10, pady=3, relief="groove",
                           selectcolor="#1976d2", fg="#333",
                           activebackground="#e3f0ff").pack(side="left", padx=3)

        # Grid layout for filters
        f_grid = tk.Frame(filter_frame, bg="white")
        f_grid.pack(fill="x")
        self.m_filters = {}
        self.m_filter_rows = {}

        # Row 1: 연도 + (내신기출만) 학년·학기·시험
        row1 = tk.Frame(f_grid, bg="white")
        row1.pack(fill="x", pady=2)

        tk.Label(row1, text="연도:", bg="white").pack(side="left", padx=(0, 5))
        self.m_filters['year'] = tk.Entry(row1, width=6, bg="#f0f0f0")
        self.m_filters['year'].pack(side="left", padx=(0, 15))

        # 내신기출 전용 — 생성만, pack은 _mgr_on_source_change()에서
        curr_keys = list(self.curr_config.get("curriculums", {}).keys())
        self.m_filters['grade']      = ttk.Combobox(row1, values=["", "고1", "고2", "고3", "중1", "중2", "중3"], width=5, state="readonly")
        self.m_filters['semester']   = ttk.Combobox(row1, values=["", "1학기", "2학기"], width=6, state="readonly")
        self.m_filters['exam']       = ttk.Combobox(row1, values=["", "중간고사", "기말고사"], width=8, state="readonly")
        self.m_filters['curriculum'] = ttk.Combobox(row1, values=[""] + curr_keys, width=13, state="readonly")
        self.m_filters['curriculum'].bind("<<ComboboxSelected>>", self._mgr_on_curriculum_change)
        self.m_filters['school']     = tk.Entry(row1, width=10, bg="#f0f0f0")
        subjs = [""] + self.curr_config.get("curriculums", {}).get("2015개정교육과정", {}).get("subjects", [])
        self.m_filters['subject']    = ttk.Combobox(row1, values=subjs, width=13)

        self.m_filter_rows['row1_naesin'] = [
            (tk.Label(row1, text="학년:", bg="white"),      (0, 5)),
            (self.m_filters['grade'],                        (0, 10)),
            (tk.Label(row1, text="학기:", bg="white"),      (0, 5)),
            (self.m_filters['semester'],                     (0, 10)),
            (tk.Label(row1, text="시험:", bg="white"),      (0, 5)),
            (self.m_filters['exam'],                         (0, 10)),
            (tk.Label(row1, text="교육과정:", bg="white"),  (0, 5)),
            (self.m_filters['curriculum'],                   (0, 10)),
            (tk.Label(row1, text="학교:", bg="white"),      (0, 5)),
            (self.m_filters['school'],                       (0, 10)),
            (tk.Label(row1, text="과목:", bg="white"),      (0, 5)),
            (self.m_filters['subject'],                      (0, 5)),
        ]

        # Row 2: 검색 입력창 + 검색 버튼 (모든 소스 공통)
        row2 = tk.Frame(f_grid, bg="white")
        row2.pack(fill="x", pady=(0, 4))

        tk.Label(row2, text="검색:", bg="white").pack(side="left", padx=(0, 5))
        self.m_filters['search'] = tk.Entry(row2, width=35, bg="#f0f0f0")
        self.m_filters['search'].pack(side="left", padx=(0, 8))
        self.m_filters['search'].bind("<Return>", self._mgr_search)
        tk.Button(row2, text="검색 (Search)", command=self._mgr_search,
                  bg=CLR_ACCENT, fg="white", font=FONT_BOLD, relief="flat", padx=20).pack(side="left")

        # Row 3: 보기 모드 토글
        row3 = tk.Frame(f_grid, bg="white")
        row3.pack(fill="x", pady=5)

        self.var_show_excluded = tk.BooleanVar(value=False)  # 하위 호환용 유지
        self.mgr_view_mode = tk.StringVar(value="all")  # "all" or "excluded_only"

        tk.Label(row3, text="보기 모드:", bg="white", font=FONT_BOLD).pack(side="left", padx=(0, 8))

        self.btn_view_all = tk.Button(
            row3, text="전체 보기",
            command=lambda: self._mgr_set_view_mode("all"),
            bg=CLR_ACCENT, fg="white", font=FONT_BOLD,
            relief="flat", padx=12, pady=3
        )
        self.btn_view_all.pack(side="left", padx=(0, 4))

        self.btn_view_excl = tk.Button(
            row3, text="⚠ 제외목록만",
            command=lambda: self._mgr_set_view_mode("excluded_only"),
            bg="#e0e0e0", fg="#555", font=FONT_BOLD,
            relief="flat", padx=12, pady=3
        )
        self.btn_view_excl.pack(side="left")

        # 2. Split View (PanedWindow)
        paned = tk.PanedWindow(self.tab_manage, orient="horizontal", sashwidth=4, bg="#ddd")
        paned.pack(fill="both", expand=True, padx=15, pady=5)
        
        # 2-Left: Files Tree
        left_frame = tk.Frame(paned, bg="white")
        paned.add(left_frame, minsize=400)
        
        tk.Label(left_frame, text="검색된 시험지 목록 (학교별)", font=FONT_BOLD, bg="white", fg="#555").pack(anchor="w", pady=5)
        
        cols = ("file", "info", "count", "id") # id is hidden, used for file_name
        self.m_tree = ttk.Treeview(left_frame, columns=cols, show="tree headings", selectmode="extended", style="Surian.Treeview")
        
        self.m_tree.heading("#0", text="학교 / 시험지명")
        self.m_tree.heading("file", text="파일 정보")
        self.m_tree.heading("info", text="세부 정보")
        self.m_tree.heading("count", text="문항 수")
        
        self.m_tree.column("#0", width=200)
        self.m_tree.column("file", width=0, stretch=False)
        self.m_tree.column("info", width=150)
        self.m_tree.column("count", width=60, anchor="center")
        self.m_tree.column("id", width=0, stretch=False) 
        
        sc_l = ttk.Scrollbar(left_frame, orient="vertical", command=self.m_tree.yview)
        self.m_tree.configure(yscrollcommand=sc_l.set)
        
        self.m_tree.pack(side="left", fill="both", expand=True)
        sc_l.pack(side="right", fill="y")
        
        # Bind Selection
        self.m_tree.bind("<<TreeviewSelect>>", self._on_mgr_select)
        
        # 2-Right: Problem List (List View)
        right_frame = tk.Frame(paned, bg="white", padx=10)
        paned.add(right_frame, minsize=400)
        
        # 문항 목록 헤더 + 편집 힌트
        hdr_row = tk.Frame(right_frame, bg="white")
        hdr_row.pack(fill="x", pady=(5, 0))
        tk.Label(hdr_row, text="문항 목록 (선택 문항 관리)",
                 font=FONT_BOLD, bg="white", fg="#555").pack(side="left")
        tk.Label(hdr_row,
                 text="  ✎ 단원·난이도 클릭=수정  |  선호도 클릭=순환  |  상태 클릭=토글",
                 font=("Segoe UI", 8), bg="white", fg="#e65100").pack(side="left")

        p_cols = ("sys_id", "no", "unit", "type", "diff", "status", "pref")
        self.m_prob_tree = ttk.Treeview(right_frame, columns=p_cols, show="headings", selectmode="extended", height=15)

        self.m_prob_tree.heading("sys_id", text="SysID")
        self.m_prob_tree.heading("no",     text="번호")
        self.m_prob_tree.heading("unit",   text="단원 ✎")
        self.m_prob_tree.heading("type",   text="유형")
        self.m_prob_tree.heading("diff",   text="난이도 ✎")
        self.m_prob_tree.heading("status", text="상태 ↕")
        self.m_prob_tree.heading("pref",   text="선호도 ↺")

        self.m_prob_tree.column("sys_id", width=0,   stretch=False)
        self.m_prob_tree.column("no",     width=50,  anchor="center")
        self.m_prob_tree.column("unit",   width=190)
        self.m_prob_tree.column("type",   width=70,  anchor="center")
        self.m_prob_tree.column("diff",   width=65,  anchor="center")
        self.m_prob_tree.column("status", width=85,  anchor="center")
        self.m_prob_tree.column("pref",   width=75,  anchor="center")
        
        sc_r = ttk.Scrollbar(right_frame, orient="vertical", command=self.m_prob_tree.yview)
        self.m_prob_tree.configure(yscrollcommand=sc_r.set)
        
        self.m_prob_tree.pack(side="left", fill="both", expand=True)
        sc_r.pack(side="right", fill="y")

        # 행 클릭 → 제외 토글
        self.m_prob_tree.bind("<ButtonRelease-1>", self._on_prob_tree_click)

        # 3. Action Bar
        action_frame = tk.Frame(self.tab_manage, bg="#f5f5f5", pady=10, padx=15)
        action_frame.pack(fill="x")
        
        self.lbl_mgr_status = tk.Label(action_frame, text="준비됨", bg="#f5f5f5", fg="#555")
        self.lbl_mgr_status.pack(side="left")
        
        # Buttons
        btn_box = tk.Frame(action_frame, bg="#f5f5f5")
        btn_box.pack(side="right")
        
        # Left Side: File Ops
        tk.Button(btn_box, text="좌측: 전체 선택", command=self._mgr_select_all_files,
                  bg="#ddd", fg="#333", font=FONT_MAIN, relief="flat", padx=10).pack(side="left", padx=5)
        tk.Button(btn_box, text="좌측: 선택 파일 삭제", command=self._mgr_delete_files, 
                  bg="#ff4d4d", fg="white", font=FONT_BOLD, relief="flat", padx=10).pack(side="left", padx=5)
        
        tk.Frame(btn_box, width=20, bg="#f5f5f5").pack(side="left") # Spacer

        # Left Side: File-level Exclusion
        tk.Button(btn_box, text="좌측: 파일 전체 제외", command=self._mgr_exclude_by_file,
                  bg="#e65100", fg="white", font=FONT_BOLD, relief="flat", padx=10).pack(side="left", padx=5)
        tk.Button(btn_box, text="좌측: 파일 전체 해제", command=self._mgr_restore_by_file,
                  bg="#2e7d32", fg="white", font=FONT_BOLD, relief="flat", padx=10).pack(side="left", padx=5)

        tk.Frame(btn_box, width=20, bg="#f5f5f5").pack(side="left")  # Spacer

        # 제외목록 전체 해제 원클릭 버튼
        tk.Button(btn_box, text="⚡ 제외목록 전체 해제",
                  command=self._mgr_restore_all_excluded,
                  bg="#1565c0", fg="white", font=FONT_BOLD, relief="flat", padx=10).pack(side="left", padx=5)

        tk.Frame(btn_box, width=20, bg="#f5f5f5").pack(side="left")  # Spacer

        # 파일 진단 버튼 — 선택한 문제가 속한 HWP 파일 단위로 진단 리포트 출력
        tk.Button(btn_box, text="🔎 파일 진단",
                  command=self._mgr_diagnose_selected,
                  bg="#00838f", fg="white", font=FONT_BOLD, relief="flat", padx=10).pack(side="left", padx=5)

        # 초기 소스 설정 (NAESIN_A 기본값으로 필터 show)
        self._mgr_on_source_change()

    def _mgr_diagnose_selected(self):
        """선택한 문제가 속한 파일(들)에 대해 얕은 진단 수행.
        - 파일 존재 확인 (_find_source_hwp)
        - 좌표 유효성 확인 (pos_start/pos_end 빈값 여부)
        - 파일별 리포트 + 해결책 안내
        """
        sel = self.m_prob_tree.selection()
        if not sel:
            messagebox.showwarning("진단", "진단할 문제를 우측 문항 트리에서 선택하세요.")
            return

        pids = []
        for item in sel:
            vals = self.m_prob_tree.item(item, "values")
            if vals and vals[0]:
                pids.append(str(vals[0]))

        if not pids:
            messagebox.showwarning("진단", "선택 항목에서 문제 ID를 읽지 못했습니다.")
            return

        import sqlite3
        conn = sqlite3.connect(self.db_engine.db_path)
        try:
            cur = conn.cursor()
            ph = ",".join("?" * len(pids))
            cur.execute(
                f"SELECT DISTINCT file_name FROM problems WHERE id IN ({ph})",
                pids
            )
            file_names = [r[0] for r in cur.fetchall() if r[0]]

            if not file_names:
                messagebox.showwarning("진단", "선택 문제의 파일명 정보가 없습니다.")
                return

            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            fph = ",".join("?" * len(file_names))
            cur.execute(
                f"""SELECT id, file_name, endnote_index, pos_start, pos_end,
                           source, is_excluded
                    FROM problems
                    WHERE file_name IN ({fph})
                    ORDER BY file_name, endnote_index""",
                file_names
            )
            rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

        from collections import defaultdict
        by_file = defaultdict(list)
        for r in rows:
            by_file[r['file_name']].append(r)

        lines = []
        lines.append(f"▶ 진단 대상: {len(by_file)}개 파일 / {len(rows)}개 문제")
        lines.append("")

        def _is_empty_coord(v):
            if v is None:
                return True
            s = str(v).strip()
            return s in ('', '[]', 'null', 'None')

        for fname in sorted(by_file.keys()):
            flist = by_file[fname]

            found_path = None
            try:
                found_path = self._find_source_hwp(fname)
            except Exception:
                pass
            exists = bool(found_path)

            no_coord = []
            for r in flist:
                if _is_empty_coord(r.get('pos_start')) or _is_empty_coord(r.get('pos_end')):
                    no_coord.append(r.get('endnote_index') or '?')

            excl_count = sum(1 for r in flist if r.get('is_excluded'))

            lines.append(f"━━━ {fname} ━━━")
            lines.append(f"  파일 존재 : {'✅ 있음' if exists else '❌ 없음 (원본 사라짐)'}")
            if found_path:
                lines.append(f"  경로      : {found_path}")
            lines.append(f"  DB 등록   : {len(flist)}문제 (제외 {excl_count}건)")

            if no_coord:
                nums = ", ".join(str(n) for n in no_coord[:15])
                if len(no_coord) > 15:
                    nums += f" ... 외 {len(no_coord) - 15}건"
                lines.append(f"  ⚠ 좌표 없음 : {len(no_coord)}문제 (미주번호: {nums})")
            else:
                lines.append(f"  좌표 상태 : 모두 정상")

            lines.append("")
            lines.append("  💡 해결책")
            if not exists:
                lines.append("     • 원본 HWP 파일이 이동·삭제·이름변경되었을 가능성")
                lines.append("     • 원본 폴더에서 파일 위치 확인 후 복구")
                lines.append("     • 복구 후 해당 파일 재인덱싱 권장")
            elif no_coord:
                lines.append("     • 좌표 정보가 없어 출제 시 해당 문제 스킵됨")
                lines.append("     • 이 파일만 재인덱싱하면 복구 가능")
            else:
                lines.append("     • DB 상태는 정상. 일시적 출제 오류 가능성")
                lines.append("     • 재출제 시도 권장")
            lines.append("")

        self._mgr_show_diag_dialog("\n".join(lines))

    def _mgr_show_diag_dialog(self, text):
        """진단 결과 텍스트를 스크롤 가능한 다이얼로그로 표시."""
        dlg = tk.Toplevel(self.root)
        dlg.title("🔎 파일 진단 결과")
        dlg.geometry("760x540")
        dlg.configure(bg="white")
        dlg.transient(self.root)

        fr = tk.Frame(dlg, bg="white", padx=10, pady=10)
        fr.pack(fill="both", expand=True)

        txt = tk.Text(fr, wrap="none", font=("Consolas", 10),
                      bg="#fafafa", relief="flat", padx=6, pady=6)
        vsb = ttk.Scrollbar(fr, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(fr, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)

        txt.insert("1.0", text)
        txt.configure(state="disabled")

        tk.Button(dlg, text="닫기", command=dlg.destroy,
                  bg="#555", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=20, pady=5).pack(pady=(0, 10))

    def _mgr_set_view_mode(self, mode):
        """보기 모드 전환: 'all' or 'excluded_only'"""
        self.mgr_view_mode.set(mode)

        if mode == "all":
            self.btn_view_all.config(bg=CLR_ACCENT, fg="white")
            self.btn_view_excl.config(bg="#e0e0e0", fg="#555")
            self.var_show_excluded.set(False)
            # 현재 검색 결과 그대로 유지 (트리 재로드 불필요)
            self._mgr_refresh_right_panel()
        else:  # excluded_only
            self.btn_view_all.config(bg="#e0e0e0", fg="#555")
            self.btn_view_excl.config(bg="#c62828", fg="white")
            self.var_show_excluded.set(True)
            self._mgr_load_excluded_only()

    def _mgr_load_excluded_only(self):
        """제외목록만 모드: 제외 문제가 있는 시험지만 좌측 트리에 표시"""
        import sqlite3

        # 좌측 트리 초기화
        for item in self.m_tree.get_children():
            self.m_tree.delete(item)
        for item in self.m_prob_tree.get_children():
            self.m_prob_tree.delete(item)

        # 제외된 문제가 있는 파일명 + 학교 조회
        conn = sqlite3.connect(self.db_engine.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT MIN(school)    AS school,
                       file_name,
                       MIN(year)      AS year,
                       MIN(semester)  AS semester,
                       MIN(exam_type) AS exam_type,
                       MIN(subject)   AS subject,
                       COUNT(*)       AS excl_count
                FROM problems
                WHERE is_excluded = 1
                GROUP BY file_name
                ORDER BY MIN(school), file_name
            """)
            rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

        if not rows:
            self.lbl_mgr_status.config(text="제외된 문제가 없습니다.")
            return

        school_nodes = {}
        for r in rows:
            sch = r['school'] or "미분류"
            if sch not in school_nodes:
                node_id = self.m_tree.insert("", "end", text=f"🏫 {sch}", open=True,
                                             values=("", "", "", ""))
                school_nodes[sch] = node_id

            info_str = f"{r['year']} {r['semester']} {r['exam_type']} ({r['subject']})"
            self.m_tree.insert(school_nodes[sch], "end",
                               text=r['file_name'],
                               values=("", info_str, f"제외 {r['excl_count']}문항", r['file_name']),
                               tags=("excl_file",))

        self.m_tree.tag_configure("excl_file", foreground="#c62828")
        self.lbl_mgr_status.config(
            text=f"⚠ 제외목록: 학교 {len(school_nodes)}개, 시험지 {len(rows)}개"
        )

        # 첫 번째 시험지 자동 선택
        first_school = self.m_tree.get_children()
        if first_school:
            first_file = self.m_tree.get_children(first_school[0])
            if first_file:
                self.m_tree.selection_set(first_file[0])
                self.m_tree.see(first_file[0])
                self._mgr_refresh_right_panel()

    def _mgr_restore_all_excluded(self):
        """제외된 문제 전체 해제 원클릭 (admin 전용)"""
        if self.current_user_role != "admin":
            messagebox.showwarning("권한", "관리자(admin)만 사용할 수 있습니다.")
            return
        import sqlite3
        conn = sqlite3.connect(self.db_engine.db_path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM problems WHERE is_excluded = 1")
            ids = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

        if not ids:
            messagebox.showinfo("알림", "제외된 문제가 없습니다.")
            return

        if not messagebox.askyesno("전체 해제 확인",
                                   f"제외된 문제 {len(ids)}개를 전부 복원하시겠습니까?"):
            return

        cnt = self.db_engine.set_exclusion_status(ids, excluded=False)
        messagebox.showinfo("완료", f"{cnt}개 문제의 제외가 해제되었습니다.")

        # 현재 모드에 맞게 화면 갱신
        if self.mgr_view_mode.get() == "excluded_only":
            self._mgr_load_excluded_only()
        else:
            self._mgr_refresh_right_panel()

    def _mgr_on_source_change(self):
        """소스 버튼 변경 시 → 내신기출 전용 필터 위젯 show/hide 후 검색 갱신"""
        source = self.mgr_source_var.get() if hasattr(self, 'mgr_source_var') else 'NAESIN_A'
        is_naesin = source in ('NAESIN_A', 'NAESIN_N')

        for widget, padx in self.m_filter_rows['row1_naesin']:
            if is_naesin:
                widget.pack(side="left", padx=padx)
            else:
                widget.pack_forget()

        self._mgr_search()

    def _mgr_on_curriculum_change(self, event=None):
        """교육과정 선택 시 과목 목록 갱신"""
        curr = self.m_filters['curriculum'].get()
        subjects = self.curr_config.get("curriculums", {}).get(curr, {}).get("subjects", [])
        self.m_filters['subject']['values'] = [""] + subjects
        self.m_filters['subject'].set("")

    def _mgr_search(self, event=None):
        source = self.mgr_source_var.get() if hasattr(self, 'mgr_source_var') else ''
        is_naesin = source in ('NAESIN_A', 'NAESIN_N')

        filters = {
            "source": source,
            "year":   self.m_filters['year'].get().strip(),
        }
        if is_naesin:
            filters["grade"]      = self.m_filters['grade'].get()
            filters["semester"]   = self.m_filters['semester'].get()
            filters["exam_type"]  = self.m_filters['exam'].get()
            filters["curriculum"] = self.m_filters['curriculum'].get()
            filters["school"]     = self.m_filters['school'].get().strip()
            filters["subject"]    = self.m_filters['subject'].get()

        kw = self.m_filters['search'].get().strip()
        if kw:
            filters['file_name_like'] = kw

        # Clear Trees
        for item in self.m_tree.get_children():
            self.m_tree.delete(item)
        for item in self.m_prob_tree.get_children():
            self.m_prob_tree.delete(item)

        # 무필터 NAESIN_A 같은 큰 쿼리에 대해 즉시 피드백 표시 후 idle 시점에 실행
        # (사용자 입장에서 "정지" 처럼 보이지 않게)
        no_filters = is_naesin and not any([
            filters.get("year"), filters.get("school"), filters.get("subject"),
            filters.get("grade"), filters.get("semester"), filters.get("exam_type"),
            filters.get("curriculum"), filters.get("file_name_like"),
        ])
        if no_filters:
            self.lbl_mgr_status.config(text="검색 중... (대량 데이터)", fg="#e65100")
            self.root.update_idletasks()

        # Grouped Search
        results = self.db_engine.search_exams_grouped(filters)
        
        # Organize by School
        school_nodes = {}
        count_exams = 0
        
        for r in results:
            sch = r['school'] or "미분류"
            if sch not in school_nodes:
                # Create School Node
                node_id = self.m_tree.insert("", "end", text=sch, open=True, values=("", "", "", ""))
                school_nodes[sch] = node_id
            
            # Create File Node under School
            info_str = f"{r['year']} {r['semester']} {r['exam_type']} ({r['subject']})"
            self.m_tree.insert(school_nodes[sch], "end", text=r['file_name'], values=(
                "",
                info_str,
                f"{r['problem_count']}문항",
                r['file_name'] # Hidden ID column stores filename
            ))
            count_exams += 1
            
        self.lbl_mgr_status.config(
            text=f"검색 결과: 학교 {len(school_nodes)}개, 시험지 {count_exams}개",
            fg="#555"
        )

    def _on_mgr_select(self, event):
        """Update problem list based on selection"""
        self._mgr_refresh_right_panel()

    def _mgr_refresh_right_panel(self):
        selected_items = self.m_tree.selection()
        file_names = []
        
        for item in selected_items:
            vals = self.m_tree.item(item, "values")
            if vals and len(vals) >= 4 and vals[3]: 
                file_names.append(vals[3])
                
        # Clear Right Panel
        for item in self.m_prob_tree.get_children():
            self.m_prob_tree.delete(item)
            
        if not file_names:
            return

        # Fetch Problems (Already sorted by file, No)
        problems = self.db_engine.get_problems_by_files(file_names)

        # 선호도 일괄 조회
        prob_ids = [p['id'] for p in problems if p.get('id') is not None]
        pref_map = self.db_engine.get_preferences_bulk(self.current_user_id, prob_ids)

        PREF_TEXT = {None: "─", "Good": "👍 Good", "Soso": "😐 Soso", "Bad": "💔 Bad"}

        view_mode = getattr(self, 'mgr_view_mode', tk.StringVar(value="all")).get()
        count = 0

        for p in problems:
            is_exc = p['is_excluded']

            # 모드별 필터
            if view_mode == "excluded_only" and not is_exc:
                continue

            status   = "⛔ 제외됨" if is_exc else "✅ 정상"
            u_name   = f"{p['large_unit']} > {p['middle_unit']}" if p['middle_unit'] else p['large_unit']
            p_no     = p.get('endnote_index', '?')
            pref_val = pref_map.get(str(p['id']))
            pref_txt = PREF_TEXT.get(pref_val, "─")
            tags     = ("excluded",) if is_exc else ("normal",)

            self.m_prob_tree.insert("", "end", values=(
                p['id'], p_no, u_name,
                p['problem_type'], p['difficulty'], status, pref_txt
            ), tags=tags)
            count += 1

        # 태그 스타일
        self.m_prob_tree.tag_configure("excluded", foreground="#c62828", background="#fff5f5")
        self.m_prob_tree.tag_configure("normal",   foreground="#1b5e20")

        mode_label = "제외목록" if view_mode == "excluded_only" else "문항 목록"
        self.lbl_mgr_status.config(text=f"{mode_label}: {count}개 표시 중")

    def _mgr_select_all_files(self):
        """Selects all items in left tree"""
        def recursive_select(item):
            self.m_tree.selection_add(item)
            for child in self.m_tree.get_children(item):
                recursive_select(child)
        
        for item in self.m_tree.get_children():
            recursive_select(item)

    def _mgr_delete_files(self):
        """파일 단위 영구 삭제 (admin 전용)"""
        if self.current_user_role != "admin":
            messagebox.showwarning("권한", "관리자(admin)만 사용할 수 있습니다.")
            return
        selected_items = self.m_tree.selection()
        file_names = []
        for item in selected_items:
            vals = self.m_tree.item(item, "values")
            if vals and len(vals) >= 4 and vals[3]:
                file_names.append(vals[3])

        file_names = list(set(file_names))

        if not file_names:
            messagebox.showwarning("삭제", "선택된 '시험지 파일'이 없습니다.")
            return

        if not messagebox.askyesno("삭제 확인", f"선택한 {len(file_names)}개의 시험지를 영구 삭제하시겠습니까?"):
            return

        count = self.db_engine.delete_exams_by_filenames(file_names)
        messagebox.showinfo("완료", f"{len(file_names)}개 파일, 총 {count}개 문항이 삭제되었습니다.")
        self._mgr_search()

    def _mgr_get_selected_file_problem_ids(self):
        """좌측에서 선택된 파일의 모든 문제 ID 반환"""
        selected_items = self.m_tree.selection()
        if not selected_items:
            return []
        file_names = []
        for item in selected_items:
            vals = self.m_tree.item(item, "values")
            if vals and len(vals) >= 4 and vals[3]:
                file_names.append(vals[3])
        if not file_names:
            return []
        problems = self.db_engine.get_problems_by_files(file_names)
        return [p['id'] for p in problems]

    def _mgr_exclude_by_file(self):
        """파일 단위 일괄 제외 (admin 전용)"""
        if self.current_user_role != "admin":
            messagebox.showwarning("권한", "관리자(admin)만 사용할 수 있습니다.")
            return
        ids = self._mgr_get_selected_file_problem_ids()
        if not ids:
            messagebox.showwarning("제외", "좌측에서 시험지를 선택해주세요.")
            return
        if not messagebox.askyesno("확인", f"선택한 파일의 문항 {len(ids)}개를 모두 출제 제외 처리할까요?"):
            return
        self.db_engine.set_exclusion_status(ids, True)
        self._mgr_refresh_right_panel()
        self.lbl_mgr_status.config(text=f"{len(ids)}개 문항 출제 제외 처리 완료")

    def _mgr_restore_by_file(self):
        """파일 단위 일괄 제외 해제 (admin 전용)"""
        if self.current_user_role != "admin":
            messagebox.showwarning("권한", "관리자(admin)만 사용할 수 있습니다.")
            return
        ids = self._mgr_get_selected_file_problem_ids()
        if not ids:
            messagebox.showwarning("해제", "좌측에서 시험지를 선택해주세요.")
            return
        if not messagebox.askyesno("확인", f"선택한 파일의 문항 {len(ids)}개를 모두 제외 해제 처리할까요?"):
            return
        self.db_engine.set_exclusion_status(ids, False)
        self._mgr_refresh_right_panel()
        self.lbl_mgr_status.config(text=f"{len(ids)}개 문항 제외 해제 처리 완료")

    def _on_prob_tree_click(self, event):
        """컬럼별 클릭 처리:
          #3 단원   → 인라인 Combobox 편집
          #5 난이도 → 인라인 Combobox 편집
          #6 상태   → 제외 ↔ 정상 즉시 토글
        """
        col  = self.m_prob_tree.identify_column(event.x)
        item = self.m_prob_tree.identify_row(event.y)
        if not item:
            return

        vals = self.m_prob_tree.item(item, "values")
        if not vals or len(vals) < 6:
            return

        prob_id = vals[0]

        if col == "#3":   # 단원 편집
            self._mgr_edit_cell(item, col, "unit_code", vals[2], prob_id)

        elif col == "#5":  # 난이도 편집
            self._mgr_edit_cell(item, col, "difficulty", vals[4], prob_id)

        elif col == "#7":  # 선호도 → 팝업 버튼
            # Button-1 이 팝업을 닫은 직후 ButtonRelease-1 가 같은 클릭으로
            # 팝업을 즉시 재개방하는 것을 방지 (200ms 이내 재오픈 차단)
            if time.time() - getattr(self, '_pref_popup_closed_ms', 0) < 0.2:
                return
            _txt_to_val  = {"─": None, "👍 Good": "Good", "😐 Soso": "Soso", "💔 Bad": "Bad"}
            cur_pref_val = _txt_to_val.get(vals[6] if len(vals) > 6 else "─")
            bbox = self.m_prob_tree.bbox(item, col)
            if bbox:
                self._mgr_show_pref_popup(item, bbox, cur_pref_val, prob_id)

        elif col == "#6":  # 상태 토글 (다중 선택 지원)
            # 선호도 팝업 또는 콤보박스를 닫은 직후 ButtonRelease-1이 동일 클릭으로
            # 상태 토글을 실행하는 것 방지 (200ms 이내 재실행 차단)
            if time.time() - getattr(self, '_pref_popup_closed_ms', 0) < 0.2:
                return
            current_status = vals[5]
            is_excluded  = "제외" in current_status
            new_excluded = not is_excluded

            # 다중 선택: 클릭된 행이 선택셋에 속하면 전체 선택 행에 동일 상태 적용
            sel_items = self.m_prob_tree.selection()
            if item in sel_items and len(sel_items) > 1:
                target_items = sel_items
            else:
                target_items = (item,)

            target_ids = []
            for it in target_items:
                v = self.m_prob_tree.item(it, "values")
                if v and len(v) >= 1:
                    target_ids.append(v[0])
            if not target_ids:
                return

            self.db_engine.set_exclusion_status(target_ids, new_excluded)

            new_status = "⛔ 제외됨" if new_excluded else "✅ 정상"
            new_tag    = ("excluded",) if new_excluded else ("normal",)
            for it in target_items:
                v = list(self.m_prob_tree.item(it, "values"))
                if not v or len(v) < 6:
                    continue
                v[5] = new_status
                self.m_prob_tree.item(it, values=tuple(v), tags=new_tag)

    def _mgr_show_pref_popup(self, item, bbox, cur_pref_val, prob_id):
        """선호도 셀 클릭 시 Good/Soso/Bad 버튼 팝업.
        닫기 3중 방어:
          ① Treeview <Button-1> 직접 바인딩 (가장 확실)
          ② root.bind_all <Button-1> 위젯 계층 확인
          ③ <Escape> 키
        """
        # ── 기존 팝업이 열려있으면 먼저 닫기 ─────────────────────────
        if getattr(self, '_pref_popup_close', None):
            self._pref_popup_close()
            self._pref_popup_close = None

        bx, by, bw, bh = bbox
        tree = self.m_prob_tree

        VAL_TO_TXT = {None: "─", "Good": "👍 Good", "Soso": "😐 Soso", "Bad": "💔 Bad"}
        PREF_STYLE = {
            "Good": {"on_bg": "#2e7d32", "on_fg": "white",
                     "off_bg": "#e8f5e9", "off_fg": "#2e7d32"},
            "Soso": {"on_bg": "#e65100", "on_fg": "white",
                     "off_bg": "#fff3e0", "off_fg": "#e65100"},
            "Bad":  {"on_bg": "#c62828", "on_fg": "white",
                     "off_bg": "#ffebee", "off_fg": "#c62828"},
        }

        _closed  = [False]
        _bids    = []       # (widget, sequence, funcid) 목록

        # ── 팝업 Toplevel ────────────────────────────────────────────
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        sx = tree.winfo_rootx() + bx
        sy = tree.winfo_rooty() + by + bh
        popup.geometry(f"+{sx}+{sy}")

        def _close(_event=None):
            if _closed[0]:
                return
            _closed[0] = True
            self._pref_popup_close = None
            self._pref_popup_closed_ms = time.time()  # 재오픈 방지용 타임스탬프
            print(f"[PREF POPUP] closed")
            # ── 바인딩 해제 ──────────────────────────────────────
            for (w, seq, fid) in _bids:
                try:
                    w.unbind(seq, fid)
                except Exception:
                    pass
            try:
                popup.destroy()
            except Exception:
                pass

        # ── 버튼 배치 ────────────────────────────────────────────────
        inner = tk.Frame(popup, bg="#f0f0f0", padx=4, pady=4)
        inner.pack(padx=1, pady=1)

        for pref_name, style in PREF_STYLE.items():
            is_active = (cur_pref_val == pref_name)

            def _make_handler(pn):
                def _handler():
                    new_val = None if (cur_pref_val == pn) else pn
                    self.db_engine.set_preference(
                        self.current_user_id, str(prob_id), new_val)
                    cur_vals    = list(tree.item(item, "values"))
                    cur_vals[6] = VAL_TO_TXT[new_val]
                    tree.item(item, values=tuple(cur_vals))
                    _close()
                return _handler

            tk.Button(
                inner, text=pref_name,
                bg=style["on_bg"] if is_active else style["off_bg"],
                fg=style["on_fg"] if is_active else style["off_fg"],
                font=("Segoe UI", 9, "bold" if is_active else "normal"),
                relief="flat", padx=12, pady=5, cursor="hand2",
                command=_make_handler(pref_name)
            ).pack(side="left", padx=3)

        popup.update_idletasks()
        print(f"[PREF POPUP] opened at +{sx}+{sy}, size={popup.winfo_width()}x{popup.winfo_height()}")

        self._pref_popup_close = _close

        # ── ① Treeview 클릭 → 즉시 닫기 (100ms 후 등록) ────────────
        def _setup_binds():
            # ① Treeview 자체에 Button-1 바인딩: 어느 셀을 눌러도 닫힘
            fid1 = tree.bind("<Button-1>", lambda e: _close(), add="+")
            _bids.append((tree, "<Button-1>", fid1))
            print(f"[PREF POPUP] tree <Button-1> bound: {fid1}")

            # ② root.bind_all: 트리 밖 영역 클릭도 닫기 (위젯 계층 확인)
            def _on_any_click(event):
                if _closed[0]:
                    return
                # 클릭된 위젯이 popup 소속인지 master 체인으로 확인
                w = event.widget
                while w is not None:
                    if w is popup:
                        return  # popup 내부 클릭 → 무시
                    try:
                        w = w.master
                    except Exception:
                        break
                print(f"[PREF POPUP] outside click → close, widget={event.widget}")
                _close()

            fid2 = self.root.bind("<Button-1>", _on_any_click, add="+")
            _bids.append((self.root, "<Button-1>", fid2))
            print(f"[PREF POPUP] root <Button-1> bound: {fid2}")

            # ③ Escape 키
            fid3 = self.root.bind("<Escape>", _close, add="+")
            _bids.append((self.root, "<Escape>", fid3))
            fid4 = tree.bind("<Escape>", _close, add="+")
            _bids.append((tree, "<Escape>", fid4))
            print(f"[PREF POPUP] Escape bound")

        popup.after(150, _setup_binds)

    def _mgr_edit_cell(self, item, col_id, field, cur_val, prob_id):
        """Treeview 셀(단원/난이도) 위에 Combobox를 place로 오버레이하여 인라인 편집.
        bbox()로 셀 좌표를 구하고, 부모 프레임 기준으로 place() 배치."""
        import json as _json

        bbox = self.m_prob_tree.bbox(item, col_id)
        if not bbox:
            return   # 스크롤로 뷰포트 밖에 있으면 무시

        bx, by, bw, bh = bbox

        # Treeview → 부모(right_frame) 좌표 변환
        tx = self.m_prob_tree.winfo_x()
        ty = self.m_prob_tree.winfo_y()
        parent = self.m_prob_tree.master

        # ── 옵션 준비 ───────────────────────────────────────────
        if field == "difficulty":
            options  = ["A: 최상", "B: 상", "C: 중", "D: 하"]
            cb_width = max(bw, 110)
        else:  # unit_code
            _cfg_path = os.path.join(_backend_dir, "curriculum_config.json")
            try:
                with open(_cfg_path, "r", encoding="utf-8") as _f:
                    _cfg = _json.load(_f)
                _unit_map = _cfg.get("unit_mappings", {})
            except Exception:
                _unit_map = {}
            # MOCK_EXAM 등에서 unit_code 를 의도적으로 빈 값으로 둘 수 있도록 첫 항목 추가
            options  = ["(빈 값으로 지움)"] + [f"{k}: {v}" for k, v in _unit_map.items()]
            cb_width = max(bw, 240)

        # ── Combobox 생성 및 배치 ────────────────────────────────
        cb = ttk.Combobox(parent, values=options, state="readonly",
                          font=("Segoe UI", 9))
        cb.place(x=tx + bx, y=ty + by, width=cb_width, height=bh + 2)

        # 현재 값 선택 (코드 또는 이름으로 매칭)
        for opt in options:
            opt_code, _, opt_name = opt.partition(": ")
            if opt_name == cur_val or opt_code == cur_val.split(":")[0].strip():
                cb.set(opt)
                break

        cb.focus_set()
        cb.event_generate("<Button-1>")   # 드롭다운 자동 열기

        _closed = [False]

        def _close():
            if _closed[0]:
                return
            _closed[0] = True
            # 콤보박스 닫힌 직후 ButtonRelease-1이 #6(상태) 셀을 잘못 토글하는 것 방지
            self._pref_popup_closed_ms = time.time()
            try:
                cb.place_forget()
                cb.destroy()
            except Exception:
                pass

        def _commit(e=None):
            sel = cb.get()
            if sel:
                cur_vals = list(self.m_prob_tree.item(item, "values"))
                if field == "difficulty":
                    code, _, name = sel.partition(": ")
                    self.db_engine.update_problem_meta(str(prob_id), "difficulty", code)
                    cur_vals[4] = code
                else:
                    # unit_code: 빈 값 옵션이면 "" 로 명시 저장 (MOCK_EXAM 정책)
                    if sel.startswith("(빈 값"):
                        self.db_engine.update_problem_meta(str(prob_id), "unit_code", "", "")
                        cur_vals[2] = ""
                    else:
                        code, _, name = sel.partition(": ")
                        self.db_engine.update_problem_meta(str(prob_id), "unit_code", code, name)
                        cur_vals[2] = name or code
                self.m_prob_tree.item(item, values=tuple(cur_vals))
            _close()

        def _on_focusout(e):
            def _delayed():
                if _closed[0]:
                    return
                try:
                    if cb.winfo_exists():
                        _close()
                except Exception:
                    pass
            parent.after(200, _delayed)

        cb.bind("<<ComboboxSelected>>", _commit)
        cb.bind("<Escape>",   lambda e: _close())
        cb.bind("<FocusOut>", _on_focusout)

    # ─────────────────────────────────────────────
    # Tab 5: 시험지 관리 (Library)
    # ─────────────────────────────────────────────

    def _build_library_tab(self):
        """시험지 관리 탭 빌드"""
        f = self.tab_library
        for w in f.winfo_children():
            w.destroy()

        # ── 상단 타이틀 ──
        title_bar = tk.Frame(f, bg="#1976d2", pady=8)
        title_bar.pack(fill="x")
        tk.Label(title_bar, text="시험지 관리", font=("Segoe UI", 13, "bold"),
                 bg="#1976d2", fg="white").pack(side="left", padx=15)

        # ── 메인 영역 (좌+우) ──
        main = tk.Frame(f, bg="white")
        main.pack(fill="both", expand=True)

        # ── 좌측: 폴더 트리 ──
        left = tk.Frame(main, bg="#f5f5f5", width=210, bd=0)
        left.pack(side="left", fill="y", padx=(0, 1))
        left.pack_propagate(False)

        lbl_frame = tk.Frame(left, bg="#f5f5f5")
        lbl_frame.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(lbl_frame, text="폴더", font=("Segoe UI", 10, "bold"),
                 bg="#f5f5f5", fg="#555").pack(side="left")
        tk.Label(lbl_frame, text="우클릭으로 관리", font=("Segoe UI", 8),
                 bg="#f5f5f5", fg="#aaa").pack(side="right")

        # 폴더 트리뷰 스타일 (1.5배 행 간격)
        style = ttk.Style()
        style.configure("FolderTree.Treeview", rowheight=30, font=("Segoe UI", 10),
                         background="#f5f5f5", fieldbackground="#f5f5f5", borderwidth=0)
        style.configure("FolderTree.Treeview.Heading", font=("Segoe UI", 9))
        style.map("FolderTree.Treeview",
                  background=[("selected", "#1976d2")],
                  foreground=[("selected", "white")])

        tree_frame_left = tk.Frame(left, bg="#f5f5f5")
        tree_frame_left.pack(fill="both", expand=True, padx=5, pady=5)

        self.lib_folder_tree = ttk.Treeview(tree_frame_left, show="tree",
                                             selectmode="browse",
                                             style="FolderTree.Treeview")
        sb_left = ttk.Scrollbar(tree_frame_left, orient="vertical",
                                 command=self.lib_folder_tree.yview)
        self.lib_folder_tree.configure(yscrollcommand=sb_left.set)
        self.lib_folder_tree.pack(side="left", fill="both", expand=True)
        sb_left.pack(side="right", fill="y")

        self.lib_folder_tree.bind("<<TreeviewSelect>>", self._lib_on_folder_select)
        self.lib_folder_tree.bind("<Double-1>", self._lib_rename_folder_dbl)
        self.lib_folder_tree.bind("<Button-3>", self._lib_show_folder_menu)

        # ── 우측: 시험지 목록 ──
        right = tk.Frame(main, bg="white")
        right.pack(side="left", fill="both", expand=True)

        # 정렬 + 버튼 바 (우측 상단)
        sort_bar = tk.Frame(right, bg="#f9f9f9", pady=5, padx=10)
        sort_bar.pack(fill="x")
        tk.Label(sort_bar, text="정렬:", font=("Segoe UI", 9), bg="#f9f9f9").pack(side="left")
        self.lib_sort_var = tk.StringVar(value="생성일자순")
        for txt in ["이름순", "생성일자순"]:
            tk.Radiobutton(sort_bar, text=txt, variable=self.lib_sort_var, value=txt,
                           bg="#f9f9f9", font=("Segoe UI", 9),
                           command=self._lib_refresh_tests).pack(side="left", padx=6)

        # 버튼 4개 - 우측 상단
        tk.Button(sort_bar, text="삭제", command=self._lib_delete_test,
                  bg="#f44336", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10).pack(side="right", padx=4)
        tk.Button(sort_bar, text="정보수정", command=self._lib_edit_info,
                  bg="#546e7a", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10).pack(side="right", padx=4)
        tk.Button(sort_bar, text="이동", command=self._lib_move_test,
                  bg="#ff9800", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10).pack(side="right", padx=4)
        tk.Button(sort_bar, text="복사", command=self._lib_copy_test,
                  bg="#00897b", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10).pack(side="right", padx=4)
        tk.Button(sort_bar, text="문항 보기", command=self._lib_view_problems,
                  bg="#1976d2", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10).pack(side="right", padx=4)
        tk.Button(sort_bar, text="▶ 시험지 출제", command=self._lib_generate_from_saved,
                  bg="#2e7d32", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10).pack(side="right", padx=4)
        tk.Button(sort_bar, text="✏ 오답 만들기", command=self._lib_make_wrong_answers,
                  bg="#7b1fa2", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10).pack(side="right", padx=4)

        # 시험지 트리뷰
        tree_frame = tk.Frame(right, bg="white")
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        cols = ("title", "unit", "count", "created")
        self.lib_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                      selectmode="extended")  # 복수 선택
        self.lib_tree.heading("title", text="시험지 이름")
        self.lib_tree.heading("unit", text="단원")
        self.lib_tree.heading("count", text="문항수")
        self.lib_tree.heading("created", text="생성일자")
        self.lib_tree.column("title", width=280, anchor="w")
        self.lib_tree.column("unit", width=180, anchor="w")
        self.lib_tree.column("count", width=60, anchor="center")
        self.lib_tree.column("created", width=140, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.lib_tree.yview)
        self.lib_tree.configure(yscrollcommand=sb.set)
        self.lib_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ── 하단 상태바 ──
        btn_bar = tk.Frame(f, bg="#f5f5f5", pady=6, padx=10)
        btn_bar.pack(fill="x", side="bottom")
        self.lib_status_lbl = tk.Label(btn_bar, text="폴더를 선택하세요",
                                        bg="#f5f5f5", fg="#777", font=("Segoe UI", 9))
        self.lib_status_lbl.pack(side="left")

        # 내부 데이터
        self._lib_folder_data = {}   # {folder_id: {id, name, parent_id, ...}}
        self._lib_test_data = []     # [{id, title, ...}, ...]
        self._lib_current_folder_id = None

        self._lib_load_folders()

    def _lib_load_folders(self, keep_selection=False):
        """폴더 트리 로드 (계층 구조, 최대 3단)"""
        prev_sel = self._lib_current_folder_id  # 선택 유지용

        folders = self.db_engine.get_folders(self.current_user_id)
        self._lib_folder_data = {}
        for f in folders:
            self._lib_folder_data[f["id"]] = f

        # 트리 초기화
        for item in self.lib_folder_tree.get_children():
            self.lib_folder_tree.delete(item)

        # 루트 항목
        self.lib_folder_tree.insert("", "end", iid="root",
                                    text="📁 전체 (루트)", open=True)

        # 재귀 삽입 (depth 1~3)
        inserted = set()
        def _insert_children(parent_id, tree_parent_iid, depth):
            if depth > 3:
                return
            children = [f for f in folders if f.get("parent_id") == parent_id]
            children.sort(key=lambda x: x.get("id", 0))  # 생성 순서 유지
            for f in children:
                if f["id"] in inserted:
                    continue
                inserted.add(f["id"])
                icon = "🔒" if f.get("is_protected") else "📁"
                iid = f"f_{f['id']}"
                self.lib_folder_tree.insert(
                    tree_parent_iid, "end", iid=iid,
                    text=f"{icon} {f['name']}",  # Treeview가 자동으로 들여쓰기 처리
                    open=True
                )
                _insert_children(f["id"], iid, depth + 1)

        _insert_children(None, "root", 1)

        # 선택 복원 또는 루트 선택
        if keep_selection and prev_sel is not None:
            target_iid = f"f_{prev_sel}"
            if self.lib_folder_tree.exists(target_iid):
                self.lib_folder_tree.selection_set(target_iid)
                self.lib_folder_tree.see(target_iid)
                return  # _lib_on_folder_select가 이미 호출됨
        self.lib_folder_tree.selection_set("root")
        self._lib_current_folder_id = None
        self._lib_refresh_tests()

    def _lib_on_folder_select(self, event=None):
        sel = self.lib_folder_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "root":
            self._lib_current_folder_id = None
        else:
            try:
                fid = int(iid.replace("f_", ""))
                self._lib_current_folder_id = fid
            except Exception:
                self._lib_current_folder_id = None
        self._lib_refresh_tests()

    # ── 폴더 우클릭 컨텍스트 메뉴 ──
    def _lib_show_folder_menu(self, event):
        """우클릭 컨텍스트 메뉴"""
        # 클릭 위치의 항목 선택
        iid = self.lib_folder_tree.identify_row(event.y)
        if iid:
            self.lib_folder_tree.selection_set(iid)

        menu = tk.Menu(self.root, tearoff=0)
        is_root = (iid == "root" or not iid)
        is_protected = False
        if not is_root and iid:
            try:
                fid = int(iid.replace("f_", ""))
                f = self._lib_folder_data.get(fid, {})
                is_protected = bool(f.get("is_protected"))
            except Exception:
                pass

        # 현재 선택 폴더의 depth 계산
        depth = self._lib_get_folder_depth(iid)

        if depth < 3:
            menu.add_command(label="📁 새 폴더 만들기", command=self._lib_create_folder)
        else:
            menu.add_command(label="📁 새 폴더 만들기 (3단 최대)", state="disabled")

        if not is_root:
            menu.add_separator()
            if not is_protected:
                menu.add_command(label="✏ 이름 변경", command=self._lib_rename_folder)
                menu.add_command(label="🗑 폴더 삭제", command=self._lib_delete_folder)
            else:
                menu.add_command(label="🔒 보호된 폴더 (수정 불가)", state="disabled")

        menu.tk_popup(event.x_root, event.y_root)

    def _lib_get_folder_depth(self, iid) -> int:
        """트리 항목의 depth 반환 (root=0, 1단=1, 2단=2, 3단=3)"""
        if not iid or iid == "root":
            return 0
        depth = 0
        cur = iid
        while cur and cur != "root":
            parent = self.lib_folder_tree.parent(cur)
            depth += 1
            cur = parent
        return depth

    def _lib_create_folder(self):
        """선택된 폴더 아래 새 폴더 생성"""
        sel = self.lib_folder_tree.selection()
        iid = sel[0] if sel else "root"
        depth = self._lib_get_folder_depth(iid)
        if depth >= 3:
            messagebox.showwarning("제한", "최대 3단 폴더까지만 만들 수 있습니다.")
            return

        if iid == "root":
            parent_id = None
            parent_name = "루트"
        else:
            try:
                parent_id = int(iid.replace("f_", ""))
                parent_name = self._lib_folder_data.get(parent_id, {}).get("name", "")
            except Exception:
                parent_id = None
                parent_name = "루트"

        dlg = tk.Toplevel(self.root)
        dlg.title("새 폴더 만들기")
        dlg.geometry("300x140")
        dlg.resizable(False, False)
        dlg.grab_set()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 150
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 70
        dlg.geometry(f"+{x}+{y}")

        tk.Label(dlg, text=f"위치: 📁 {parent_name}", fg="#555",
                 font=("Segoe UI", 9)).pack(padx=15, pady=(12, 4), anchor="w")
        entry = tk.Entry(dlg, font=("Segoe UI", 11))
        entry.pack(fill="x", padx=15, pady=4)
        entry.focus_set()

        def _do_create():
            name = entry.get().strip()
            if not name:
                return
            result = self.db_engine.create_folder(name, self.current_user_id, parent_id=parent_id)
            if result.get("success"):
                dlg.destroy()
                self._lib_load_folders(keep_selection=True)
                # 새 폴더 선택
                new_iid = f"f_{result['id']}"
                if self.lib_folder_tree.exists(new_iid):
                    self.lib_folder_tree.selection_set(new_iid)
                    self.lib_folder_tree.see(new_iid)
                    self._lib_on_folder_select()
            else:
                messagebox.showerror("오류", result.get("message", "폴더 생성 실패"))

        entry.bind("<Return>", lambda e: _do_create())
        tk.Button(dlg, text="만들기", command=_do_create,
                  bg="#1976d2", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat").pack(pady=8)

    def _lib_rename_folder(self):
        """선택된 폴더 이름 변경 (메뉴에서 호출)"""
        sel = self.lib_folder_tree.selection()
        if not sel or sel[0] == "root":
            return
        self._lib_do_rename(sel[0])

    def _lib_rename_folder_dbl(self, event):
        """더블클릭으로 이름 변경"""
        iid = self.lib_folder_tree.identify_row(event.y)
        if not iid or iid == "root":
            return
        f = self._lib_folder_data.get(int(iid.replace("f_", "")), {})
        if f.get("is_protected"):
            return
        self._lib_do_rename(iid)

    def _lib_do_rename(self, iid):
        try:
            fid = int(iid.replace("f_", ""))
        except Exception:
            return
        f = self._lib_folder_data.get(fid, {})
        if f.get("is_protected"):
            messagebox.showwarning("제한", "보호된 폴더는 이름을 변경할 수 없습니다.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("폴더 이름 변경")
        dlg.geometry("300x130")
        dlg.resizable(False, False)
        dlg.grab_set()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 150
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 65
        dlg.geometry(f"+{x}+{y}")

        tk.Label(dlg, text="새 이름:", font=("Segoe UI", 9), fg="#555").pack(
            padx=15, pady=(12, 4), anchor="w")
        entry = tk.Entry(dlg, font=("Segoe UI", 11))
        entry.insert(0, f.get("name", ""))
        entry.select_range(0, "end")
        entry.pack(fill="x", padx=15, pady=4)
        entry.focus_set()

        def _do_rename():
            new_name = entry.get().strip()
            if not new_name:
                return
            ok = self.db_engine.rename_folder(fid, new_name)
            if ok:
                dlg.destroy()
                self._lib_load_folders(keep_selection=True)
            else:
                messagebox.showerror("오류", "이름 변경 실패")

        entry.bind("<Return>", lambda e: _do_rename())
        tk.Button(dlg, text="변경", command=_do_rename,
                  bg="#1976d2", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat").pack(pady=8)

    def _lib_delete_folder(self):
        """선택된 폴더 삭제 (비어 있을 때만)"""
        sel = self.lib_folder_tree.selection()
        if not sel or sel[0] == "root":
            messagebox.showwarning("안내", "삭제할 폴더를 선택하세요.")
            return
        try:
            fid = int(sel[0].replace("f_", ""))
        except Exception:
            return
        f = self._lib_folder_data.get(fid, {})
        fname = f.get("name", "")

        if not messagebox.askyesno("폴더 삭제", f"'{fname}' 폴더를 삭제할까요?"):
            return

        result = self.db_engine.delete_folder(fid)
        if result.get("success"):
            self._lib_current_folder_id = None
            self._lib_load_folders()
        else:
            messagebox.showerror("삭제 실패", result.get("message", "알 수 없는 오류"))

    def _lib_refresh_tests(self):
        """현재 폴더의 시험지 목록 새로고침"""
        tests = self.db_engine.get_tests(directory_id=self._lib_current_folder_id, user_id=self.current_user_id)

        # 정렬
        sort = self.lib_sort_var.get()
        if sort == "이름순":
            tests.sort(key=lambda t: t.get("title") or "")
        else:  # 생성일자순
            tests.sort(key=lambda t: t.get("created_at") or "", reverse=True)

        self._lib_test_data = tests

        for row in self.lib_tree.get_children():
            self.lib_tree.delete(row)

        for t in tests:
            try:
                p_ids = json.loads(t.get("problem_ids", "[]"))
                count = len(p_ids)
            except Exception:
                count = 0
            created = (t.get("created_at") or "")[:16]  # YYYY-MM-DD HH:MM
            self.lib_tree.insert("", "end", iid=str(t["id"]), values=(
                t.get("title", ""),
                t.get("unit_summary", ""),
                count,
                created
            ))

        self.lib_status_lbl.config(text=f"시험지 {len(tests)}개")

    def _lib_get_selected_tests(self):
        """선택된 시험지 목록 반환 (복수 선택 지원)"""
        sel = self.lib_tree.selection()
        if not sel:
            messagebox.showwarning("안내", "시험지를 선택해주세요.")
            return []
        selected = []
        id_set = {int(s) for s in sel}
        for t in self._lib_test_data:
            if t["id"] in id_set:
                selected.append(t)
        return selected

    def _lib_get_selected_test(self):
        """선택된 첫 번째 시험지 데이터 반환 (단일 선택용)"""
        tests = self._lib_get_selected_tests()
        return tests[0] if tests else None

    def _lib_view_problems(self):
        """문항 보기 - 첫 번째 선택 항목만 보여주기"""
        sel = self.lib_tree.selection()
        if not sel:
            messagebox.showwarning("안내", "시험지를 선택해주세요.")
            return
        # 복수 선택 시 첫 번째만
        test_id = int(sel[0])
        test = None
        for t in self._lib_test_data:
            if t["id"] == test_id:
                test = t
                break
        if not test:
            return
        detail = self.db_engine.get_test_detail(test["id"], self.current_user_id)
        if not detail:
            messagebox.showerror("오류", "시험지 데이터를 불러올 수 없습니다.")
            return
        self._lib_show_problem_view(detail)

    def _lib_generate_from_saved(self):
        """저장된 시험지를 출제 루트로 넣기 — 문항 목록을 final_problems에 세팅 후 출제 다이얼로그 호출"""
        test = self._lib_get_selected_test()
        if not test:
            return
        detail = self.db_engine.get_test_detail(test["id"], self.current_user_id)
        if not detail or not detail.get("problems"):
            messagebox.showerror("오류", "시험지 데이터를 불러올 수 없습니다.")
            return
        problems = detail["problems"]
        if not messagebox.askyesno(
            "시험지 출제",
            f"'{test.get('title', '시험지')}' ({len(problems)}문항)을\n출제 루트로 넣겠습니까?\n\n현재 작업 중인 문항 목록이 교체됩니다."
        ):
            return
        # 메인 GUI 출제 루트에 세팅
        self.final_problems = problems
        # ★ 전역속성 오염 방지: saved_exam_* 에도 저장하되, 다이얼로그에는 직접 파라미터 전달
        _lib_title = test.get("title", "")
        _lib_unit  = test.get("unit_summary", "")
        self.saved_exam_title = _lib_title
        self.saved_exam_unit  = _lib_unit
        self._open_generate_dialog(exam_title=_lib_title, exam_unit=_lib_unit)

    def _lib_show_problem_view(self, detail):
        """문항 목록 화면 (라이브러리 탭 내 전환) — 인라인 선호도 버튼 포함"""
        f = self.tab_library
        for w in f.winfo_children():
            w.pack_forget()

        view = tk.Frame(f, bg="white")
        view.pack(fill="both", expand=True)

        # ── 상단 바 ─────────────────────────────────────────────────
        top = tk.Frame(view, bg="#1976d2", pady=8)
        top.pack(fill="x")
        tk.Label(top, text=f"문항 보기 - {detail['title']}",
                 font=("Segoe UI", 12, "bold"), bg="#1976d2", fg="white").pack(side="left", padx=15)
        tk.Button(top, text="← 돌아가기", command=lambda: self._lib_back_to_list(view),
                  bg="#1565c0", fg="white", font=("Segoe UI", 9),
                  relief="flat", padx=10).pack(side="right", padx=10)

        # ── 컬럼 헤더 ───────────────────────────────────────────────
        # (편집가능 여부: True → 헤더 주황색, 셀에 호버 노란 배경 표시)
        COLS = [
            ("no",     "번호",             4,  "center", False),
            ("source", "출처",             100, "w",      False),
            ("unit",   "단원  ✎더블클릭", 18, "w",      True),
            ("diff",   "난이도 ✎",         8,  "center", True),
            ("type",   "유형",             6,  "center", False),
            ("pref",   "선호도",           22, "center", False),
            ("del",    "삭제",             6,  "center", False),
        ]
        hdr = tk.Frame(view, bg="#e3f2fd", pady=5)
        hdr.pack(fill="x", padx=12, pady=(8, 0))
        for _, col_name, col_w, col_anchor, editable in COLS:
            fg = "#e65100" if editable else "#1565c0"   # 편집 가능 → 주황색
            tk.Label(hdr, text=col_name, font=("Segoe UI", 9, "bold"),
                     bg="#e3f2fd", fg=fg, width=col_w,
                     anchor=col_anchor).pack(side="left")

        # ── 스크롤 캔버스 ────────────────────────────────────────────
        list_outer = tk.Frame(view, bg="white")
        list_outer.pack(fill="both", expand=True, padx=12, pady=(2, 8))

        canvas = tk.Canvas(list_outer, bg="white", highlightthickness=0)
        vsb = ttk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="white")
        cwin = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(cwin, width=e.width))

        def _mwheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        # Enter/Leave 시에만 휠 바인딩 → 다른 탭/위젯의 휠 가로채기 방지
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _mwheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        view.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ── 선호도 색상 정의 ─────────────────────────────────────────
        PREF_STYLE = {
            "Good": {"on_bg": "#2e7d32", "on_fg": "white",
                     "off_bg": "#e8f5e9", "off_fg": "#2e7d32"},
            "Soso": {"on_bg": "#e65100", "on_fg": "white",
                     "off_bg": "#fff3e0", "off_fg": "#e65100"},
            "Bad":  {"on_bg": "#c62828", "on_fg": "white",
                     "off_bg": "#ffebee", "off_fg": "#c62828"},
        }
        level_map = {"A": "최상", "B": "상", "C": "중", "D": "하"}
        level_map_r = {"최상": "A", "상": "B", "중": "C", "하": "D"}

        # ── curriculum_config.json 로드 (단원 드롭다운용) ────────────
        import json as _json
        _cfg_path = os.path.join(_backend_dir, "curriculum_config.json")
        try:
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                _cfg = _json.load(_f)
            _unit_map = _cfg.get("unit_mappings", {})  # {"A1": "다항식의 연산", ...}
        except Exception:
            _unit_map = {}
        # 드롭다운 옵션: ["A1: 다항식의 연산", ...]
        _unit_options = [f"{k}: {v}" for k, v in _unit_map.items()]
        _diff_options = ["A: 최상", "B: 상", "C: 중", "D: 하"]

        # ── 인라인 편집 헬퍼 ─────────────────────────────────────────
        def _make_inline_editor(lbl, pid_, field_, options_, row_bg_):
            """더블클릭 시 label 위에 Combobox를 place로 오버레이.
            pack_forget/pack 방식은 위치가 어긋나므로 place 방식 사용.
            """
            def _on_dblclick(e):
                cur_txt = lbl.cget("text")
                # label의 row 내 좌표·크기 확정
                lbl.update_idletasks()
                lx, ly = lbl.winfo_x(), lbl.winfo_y()
                lw, lh = lbl.winfo_width(), lbl.winfo_height()

                cb = ttk.Combobox(lbl.master, values=options_,
                                  state="readonly", font=("Segoe UI", 9))
                # 단원 Combobox는 옵션이 많으므로 폭을 넉넉하게
                cb_w = max(lw, 200) if field_ != "difficulty" else max(lw, 120)
                cb.place(x=lx, y=ly, width=cb_w, height=lh + 2)

                # 현재 값과 가장 가까운 옵션 선택 (코드 또는 이름으로 매칭)
                for opt in options_:
                    opt_code, _, opt_name = opt.partition(": ")
                    if opt_name == cur_txt or opt_code == cur_txt.split(":")[0].strip():
                        cb.set(opt)
                        break

                cb.focus_set()
                cb.event_generate("<Button-1>")  # 드롭다운 자동 열기

                _closed = [False]

                def _close():
                    if _closed[0]:
                        return
                    _closed[0] = True
                    try:
                        cb.place_forget()
                        cb.destroy()
                    except Exception:
                        pass

                def _commit(e=None):
                    sel = cb.get()
                    if sel:
                        code, _, name = sel.partition(": ")
                        if field_ == "difficulty":
                            self.db_engine.update_problem_meta(str(pid_), "difficulty", code)
                            lbl.configure(text=f"{code}: {name}" if name else code)
                        else:  # unit_code
                            self.db_engine.update_problem_meta(str(pid_), "unit_code", code, name)
                            lbl.configure(text=name or code)
                    _close()

                def _on_focusout(e):
                    # 드롭다운 팝업 열릴 때 FocusOut 오발동 방지 → 200ms 지연 후 닫기
                    def _delayed():
                        if _closed[0]:
                            return
                        try:
                            if cb.winfo_exists():
                                _close()
                        except Exception:
                            pass
                    lbl.master.after(200, _delayed)

                cb.bind("<<ComboboxSelected>>", _commit)
                cb.bind("<Escape>",   lambda e: _close())
                cb.bind("<FocusOut>", _on_focusout)
            return _on_dblclick

        problems = detail.get("problems", [])
        problem_ids = [p.get("id") for p in problems if p.get("id") is not None]

        # 기존 선호도 일괄 조회
        pref_map = self.db_engine.get_preferences_bulk(self.current_user_id, problem_ids)

        # ── 문항 행 생성 ─────────────────────────────────────────────
        for i, p in enumerate(problems, 1):
            row_bg = "white" if i % 2 == 0 else "#fafafa"
            row = tk.Frame(inner, bg=row_bg, pady=3)
            row.pack(fill="x", padx=2)

            num   = p.get("endnote_index", "?")
            fname = (p.get("file_name", "") or "").replace(".hwp", "").replace(".HWP", "")
            source_txt = f"{fname}  {num}번"
            unit_txt   = p.get("middle_unit") or p.get("large_unit") or ""
            diff_code  = p.get("difficulty", "")
            diff_txt   = f"{diff_code}: {level_map[diff_code]}" if diff_code in level_map else diff_code
            type_txt   = p.get("problem_type", "")
            pid        = p.get("id")

            tk.Label(row, text=str(i),     bg=row_bg, width=4,  anchor="center", font=("Segoe UI", 9)).pack(side="left")
            tk.Label(row, text=source_txt, bg=row_bg, width=100, anchor="w",      font=("Segoe UI", 9)).pack(side="left")

            # 단원 레이블 — 더블클릭으로 편집 (호버 시 노란 배경으로 편집 가능 표시)
            unit_lbl = tk.Label(row, text=unit_txt, bg=row_bg, width=18, anchor="w",
                                font=("Segoe UI", 9), cursor="hand2")
            unit_lbl.pack(side="left")
            unit_lbl.bind("<Enter>",          lambda e, l=unit_lbl, b=row_bg: l.configure(bg="#fff9c4"))
            unit_lbl.bind("<Leave>",          lambda e, l=unit_lbl, b=row_bg: l.configure(bg=b))
            unit_lbl.bind("<Double-Button-1>",
                          _make_inline_editor(unit_lbl, pid, "unit_code", _unit_options, row_bg))

            # 난이도 레이블 — 더블클릭으로 편집 (호버 시 노란 배경)
            diff_lbl = tk.Label(row, text=diff_txt, bg=row_bg, width=8, anchor="center",
                                font=("Segoe UI", 9), cursor="hand2")
            diff_lbl.pack(side="left")
            diff_lbl.bind("<Enter>",          lambda e, l=diff_lbl, b=row_bg: l.configure(bg="#fff9c4"))
            diff_lbl.bind("<Leave>",          lambda e, l=diff_lbl, b=row_bg: l.configure(bg=b))
            diff_lbl.bind("<Double-Button-1>",
                          _make_inline_editor(diff_lbl, pid, "difficulty", _diff_options, row_bg))

            tk.Label(row, text=type_txt, bg=row_bg, width=6, anchor="center", font=("Segoe UI", 9)).pack(side="left")

            # 선호도 버튼 프레임
            pref_frame = tk.Frame(row, bg=row_bg)
            pref_frame.pack(side="left", padx=(4, 0))

            pid = p.get("id")
            cur_pref = pref_map.get(str(pid)) if pid is not None else None
            btn_refs = {}

            for pref_name, style in PREF_STYLE.items():
                is_on = (cur_pref == pref_name)
                btn = tk.Button(
                    pref_frame, text=pref_name,
                    font=("Segoe UI", 8),
                    bg=style["on_bg"] if is_on else style["off_bg"],
                    fg=style["on_fg"] if is_on else style["off_fg"],
                    relief="flat", padx=6, pady=1, bd=0, cursor="hand2"
                )
                btn.pack(side="left", padx=2)
                btn_refs[pref_name] = btn

            # 클릭 핸들러 (closure로 pid·pref·btn_refs 캡처)
            def _make_pref_handler(pid_, pref_n_, btn_refs_, pref_map_):
                def _handler():
                    cur = pref_map_.get(str(pid_))
                    if cur == pref_n_:          # 같은 버튼 재클릭 → 해제
                        self.db_engine.set_preference(self.current_user_id, str(pid_), None)
                        pref_map_[str(pid_)] = None
                        new_active = None
                    else:
                        self.db_engine.set_preference(self.current_user_id, str(pid_), pref_n_)
                        pref_map_[str(pid_)] = pref_n_
                        new_active = pref_n_
                    for pn, b in btn_refs_.items():
                        s = PREF_STYLE[pn]
                        if pn == new_active:
                            b.configure(bg=s["on_bg"], fg=s["on_fg"])
                        else:
                            b.configure(bg=s["off_bg"], fg=s["off_fg"])
                return _handler

            for pref_name, btn in btn_refs.items():
                btn.configure(command=_make_pref_handler(pid, pref_name, btn_refs, pref_map))

            # 삭제 버튼 — 이 시험지 목록(saved_tests.problem_ids)에서만 제거
            # (DB의 problems 행은 유지. 삭제 후 재렌더로 번호 재정렬.)
            def _make_delete_handler(pid_=pid, row_num=i, src_txt=source_txt):
                def _handler():
                    if not messagebox.askyesno(
                        "삭제 확인",
                        f"{row_num}번 문제를 이 시험지에서 제거할까요?\n"
                        f"  └ {src_txt}\n\n"
                        f"(DB의 문제 자체는 삭제되지 않습니다)"
                    ):
                        return
                    import json as _js
                    _tid = detail.get('id')
                    try:
                        # detail에 저장된 problem_ids에서 pid_ 제거
                        _raw_pids = detail.get('problem_ids', '[]')
                        if isinstance(_raw_pids, str):
                            try:
                                _pids = _js.loads(_raw_pids or '[]')
                            except Exception:
                                _pids = []
                        elif isinstance(_raw_pids, list):
                            _pids = list(_raw_pids)
                        else:
                            _pids = [str(q.get('id')) for q in detail.get('problems', [])]
                        _pids = [x for x in _pids if str(x) != str(pid_)]

                        payload = {
                            "id": _tid,
                            "title": detail.get("title", ""),
                            "unit_summary": detail.get("unit_summary", ""),
                            "directory_id": detail.get("directory_id"),
                            "problem_ids": _js.dumps(_pids),
                            "metadata": detail.get("metadata", "{}"),
                        }
                        res = self.db_engine.save_test(
                            payload, detail.get("user_id", self.current_user_id)
                        )
                        if not (res and res.get("success")):
                            msg = (res or {}).get("message", "DB 응답 없음")
                            messagebox.showerror("오류", f"삭제 실패:\n{msg}")
                            return
                        # detail 메모리도 동기화
                        detail['problem_ids'] = _js.dumps(_pids)
                    except Exception as _e:
                        messagebox.showerror("오류", f"삭제 실패: {_e}")
                        return
                    detail['problems'] = [
                        q for q in detail.get('problems', [])
                        if str(q.get('id')) != str(pid_)
                    ]
                    self._lib_show_problem_view(detail)
                return _handler

            tk.Button(
                row, text="삭제",
                command=_make_delete_handler(),
                bg="#c62828", fg="white",
                font=("Segoe UI", 8, "bold"),
                relief="flat", width=6, padx=2, pady=1, cursor="hand2"
            ).pack(side="left", padx=(8, 0))

        # ── 하단 정보 바 ─────────────────────────────────────────────
        bottom = tk.Frame(view, bg="#f5f5f5", pady=6)
        bottom.pack(fill="x", side="bottom")
        tk.Label(bottom, text=f"총 {len(problems)}문항",
                 bg="#f5f5f5", fg="#555", font=("Segoe UI", 9)).pack(side="left", padx=15)
        _role_tag = " (관리자)" if self.current_user_role == "admin" else ""
        tk.Label(bottom, text=f"사용자: {self.current_user_display_id}{_role_tag}",
                 bg="#f5f5f5", fg="#999", font=("Segoe UI", 8)).pack(side="right", padx=15)

    def _lib_back_to_list(self, view_frame):
        """문항 보기에서 목록으로 복귀"""
        view_frame.destroy()
        self._build_library_tab()

    def _lib_delete_test(self):
        """시험지 삭제 (복수 선택 지원)"""
        tests = self._lib_get_selected_tests()
        if not tests:
            return
        count = len(tests)
        if count == 1:
            msg = f"'{tests[0]['title']}' 시험지를 삭제할까요?\n(복구 불가)"
        else:
            titles = "\n".join(f"  · {t['title']}" for t in tests[:5])
            if count > 5:
                titles += f"\n  · ... 외 {count - 5}개"
            msg = f"선택한 {count}개 시험지를 삭제할까요?\n{titles}\n(복구 불가)"
        if not messagebox.askyesno("삭제 확인", msg):
            return
        ids = [t["id"] for t in tests]
        ok_cnt = 0
        for tid in ids:
            try:
                if self.db_engine.delete_test(tid):
                    ok_cnt += 1
            except Exception as e:
                print(f"[delete_test] id={tid} 오류: {e}")
        self._lib_refresh_tests()
        if ok_cnt == count:
            self.lib_status_lbl.config(text=f"{count}개 삭제 완료")
        else:
            self.lib_status_lbl.config(text=f"{ok_cnt}/{count} 삭제됨 (실패 {count - ok_cnt}건)")

    def _lib_move_test(self):
        """시험지를 다른 폴더로 이동 (복수 선택 지원, 계층 구조 표시)"""
        tests = self._lib_get_selected_tests()
        if not tests:
            return
        count = len(tests)
        folders = self.db_engine.get_folders(self.current_user_id)

        dlg = tk.Toplevel(self.root)
        dlg.title("폴더 이동")
        dlg.geometry("300x280")
        dlg.resizable(False, False)
        dlg.grab_set()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 150
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 140
        dlg.geometry(f"+{x}+{y}")

        if count == 1:
            label_text = f"'{tests[0].get('title', '')}'\n이동할 폴더 선택:"
        else:
            label_text = f"선택한 {count}개 시험지를\n이동할 폴더 선택:"
        tk.Label(dlg, text=label_text, pady=8, font=("Segoe UI", 9)).pack()

        # 트리뷰로 계층 폴더 선택
        move_tree = ttk.Treeview(dlg, show="tree", selectmode="browse", height=8)
        move_tree.pack(fill="both", expand=True, padx=10)
        move_tree.insert("", "end", iid="root", text="📁 루트 (최상위)", open=True)

        folder_map = {f["id"]: f for f in folders}
        inserted = set()
        def _insert(parent_id, tree_parent, depth):
            if depth > 3:
                return
            children = [f for f in folders if f.get("parent_id") == parent_id]
            children.sort(key=lambda x: x.get("name", ""))
            for f in children:
                if f["id"] in inserted:
                    continue
                inserted.add(f["id"])
                icon = "🔒" if f.get("is_protected") else "📁"
                iid = f"f_{f['id']}"
                move_tree.insert(tree_parent, "end", iid=iid,
                                 text=f"{'  ' * (depth-1)}{icon} {f['name']}", open=True)
                _insert(f["id"], iid, depth + 1)
        _insert(None, "root", 1)

        def _do_move():
            sel = move_tree.selection()
            if not sel:
                messagebox.showwarning("안내", "이동할 폴더를 선택하세요.", parent=dlg)
                return
            iid = sel[0]
            new_dir_id = None if iid == "root" else int(iid.replace("f_", ""))
            ok_cnt = 0
            errors = []
            for t in tests:
                payload = {
                    "id": t["id"],
                    "title": t.get("title", ""),
                    "unit_summary": t.get("unit_summary", ""),
                    "directory_id": new_dir_id,
                    "problem_ids": t.get("problem_ids", "[]"),
                    "metadata": t.get("metadata", "{}"),
                }
                try:
                    res = self.db_engine.save_test(payload, t.get("user_id", self.current_user_id))
                except Exception as e:
                    errors.append(f"'{t.get('title','')}': {e}")
                    continue
                if res and res.get("success"):
                    ok_cnt += 1
                else:
                    errors.append(f"'{t.get('title','')}': {(res or {}).get('message','DB 응답 없음')}")
            dlg.destroy()
            try:
                self._lib_load_folders(keep_selection=True)
            except Exception:
                pass
            self._lib_refresh_tests()
            if ok_cnt == count:
                self.lib_status_lbl.config(text=f"{count}개 이동 완료")
                messagebox.showinfo("이동 완료", f"{count}개 시험지를 이동했습니다.")
            else:
                self.lib_status_lbl.config(text=f"{ok_cnt}/{count} 이동됨 (실패 {count - ok_cnt}건)")
                detail = "\n".join(errors[:5])
                if len(errors) > 5:
                    detail += f"\n…(외 {len(errors)-5}건)"
                messagebox.showerror(
                    "이동 일부 실패",
                    f"{ok_cnt}/{count} 이동 성공\n실패 {count - ok_cnt}건:\n\n{detail}"
                )

        tk.Button(dlg, text="이동", command=_do_move,
                  bg="#1976d2", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat").pack(pady=8)

    def _lib_copy_test(self):
        """시험지를 다른 폴더로 복사 (원본 유지, 복수 선택 지원)"""
        tests = self._lib_get_selected_tests()
        if not tests:
            return
        count = len(tests)
        folders = self.db_engine.get_folders(self.current_user_id)

        dlg = tk.Toplevel(self.root)
        dlg.title("폴더 복사")
        dlg.geometry("300x280")
        dlg.resizable(False, False)
        dlg.grab_set()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 150
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 140
        dlg.geometry(f"+{x}+{y}")

        if count == 1:
            label_text = f"'{tests[0].get('title', '')}'\n복사할 폴더 선택:"
        else:
            label_text = f"선택한 {count}개 시험지를\n복사할 폴더 선택:"
        tk.Label(dlg, text=label_text, pady=8, font=("Segoe UI", 9)).pack()

        copy_tree = ttk.Treeview(dlg, show="tree", selectmode="browse", height=8)
        copy_tree.pack(fill="both", expand=True, padx=10)
        copy_tree.insert("", "end", iid="root", text="📁 루트 (최상위)", open=True)

        inserted = set()
        def _insert(parent_id, tree_parent, depth):
            if depth > 3:
                return
            children = [f for f in folders if f.get("parent_id") == parent_id]
            children.sort(key=lambda x: x.get("name", ""))
            for f in children:
                if f["id"] in inserted:
                    continue
                inserted.add(f["id"])
                icon = "🔒" if f.get("is_protected") else "📁"
                iid = f"f_{f['id']}"
                copy_tree.insert(tree_parent, "end", iid=iid,
                                 text=f"{'  ' * (depth-1)}{icon} {f['name']}", open=True)
                _insert(f["id"], iid, depth + 1)
        _insert(None, "root", 1)

        def _do_copy():
            sel = copy_tree.selection()
            if not sel:
                messagebox.showwarning("안내", "복사할 폴더를 선택하세요.", parent=dlg)
                return
            iid = sel[0]
            new_dir_id = None if iid == "root" else int(iid.replace("f_", ""))
            ok_cnt = 0
            errors = []
            for t in tests:
                payload = {
                    # id 미포함 → save_test 가 INSERT (새 doc)
                    "title": t.get("title", ""),
                    "unit_summary": t.get("unit_summary", ""),
                    "directory_id": new_dir_id,
                    "problem_ids": t.get("problem_ids", "[]"),
                    "metadata": t.get("metadata", "{}"),
                }
                try:
                    res = self.db_engine.save_test(payload, t.get("user_id", self.current_user_id))
                except Exception as e:
                    errors.append(f"'{t.get('title','')}': {e}")
                    continue
                if res and res.get("success"):
                    ok_cnt += 1
                else:
                    errors.append(f"'{t.get('title','')}': {(res or {}).get('message','DB 응답 없음')}")
            dlg.destroy()
            try:
                self._lib_load_folders(keep_selection=True)
            except Exception:
                pass
            self._lib_refresh_tests()
            if ok_cnt == count:
                self.lib_status_lbl.config(text=f"{count}개 복사 완료")
                messagebox.showinfo("복사 완료", f"{count}개 시험지를 복사했습니다.")
            else:
                self.lib_status_lbl.config(text=f"{ok_cnt}/{count} 복사됨 (실패 {count - ok_cnt}건)")
                detail = "\n".join(errors[:5])
                if len(errors) > 5:
                    detail += f"\n…(외 {len(errors)-5}건)"
                messagebox.showerror(
                    "복사 일부 실패",
                    f"{ok_cnt}/{count} 복사 성공\n실패 {count - ok_cnt}건:\n\n{detail}"
                )

        tk.Button(dlg, text="복사", command=_do_copy,
                  bg="#00897b", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat").pack(pady=8)

    def _lib_edit_info(self):
        """선택된 시험지의 이름·단원 수정 (단일 선택)"""
        tests = self._lib_get_selected_tests()
        if not tests:
            return
        if len(tests) > 1:
            messagebox.showwarning("안내", "정보수정은 시험지 1개만 선택해주세요.")
            return
        test = tests[0]

        dlg = tk.Toplevel(self.root)
        dlg.title("정보수정")
        dlg.geometry("360x200")
        dlg.resizable(False, False)
        dlg.grab_set()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 180
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 100
        dlg.geometry(f"+{x}+{y}")

        pad = {"padx": 16, "pady": 5}
        tk.Label(dlg, text="시험지 이름", font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", **pad)
        var_title = tk.StringVar(value=test.get("title", ""))
        ent_title = tk.Entry(dlg, textvariable=var_title, font=("Segoe UI", 10))
        ent_title.pack(fill="x", padx=16)
        ent_title.icursor("end")

        tk.Label(dlg, text="단원", font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", **pad)
        var_unit = tk.StringVar(value=test.get("unit_summary", ""))
        ent_unit = tk.Entry(dlg, textvariable=var_unit, font=("Segoe UI", 10))
        ent_unit.pack(fill="x", padx=16)

        def _do_save():
            new_title = var_title.get().strip()
            if not new_title:
                messagebox.showwarning("안내", "시험지 이름을 입력하세요.", parent=dlg)
                ent_title.focus_set()
                return
            new_unit = var_unit.get().strip()
            payload = {
                "id": test["id"],
                "title": new_title,
                "unit_summary": new_unit,
                "directory_id": test.get("directory_id"),
                "problem_ids": test.get("problem_ids", "[]"),
                "metadata": test.get("metadata", "{}"),
            }
            res = self.db_engine.save_test(
                payload, test.get("user_id", self.current_user_id)
            )
            if not (res and res.get("success")):
                msg = (res or {}).get("message", "DB 응답 없음")
                messagebox.showerror("오류", f"수정 실패:\n{msg}", parent=dlg)
                return
            dlg.destroy()
            self._lib_refresh_tests()
            self.lib_status_lbl.config(text="정보 수정 완료")

        btn_row = tk.Frame(dlg)
        btn_row.pack(pady=10)
        tk.Button(btn_row, text="저장", command=_do_save,
                  bg="#1976d2", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=14).pack(side="left", padx=6)
        tk.Button(btn_row, text="취소", command=dlg.destroy,
                  bg="#9e9e9e", fg="white", font=("Segoe UI", 10),
                  relief="flat", padx=14).pack(side="left", padx=6)

        dlg.bind("<Return>", lambda e: _do_save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        ent_title.focus_set()

    def _lib_make_wrong_answers(self):
        """선택된 시험지의 오답 만들기 - 채점 화면 열기"""
        test = self._lib_get_selected_test()
        if not test:
            return
        # 문제 상세 로드
        detail = self.db_engine.get_test_detail(test["id"], self.current_user_id)
        if not detail:
            messagebox.showerror("오류", "시험지 데이터를 불러올 수 없습니다.")
            return
        problems = detail.get("problems", [])
        if not problems:
            messagebox.showwarning("안내", "이 시험지에 문항이 없습니다.")
            return
        # 기존 채점 기록 로드 (있으면 복원)
        existing_scores = self.db_engine.get_scores_for_test(test["id"])
        # 채점 다이얼로그 열기 (gui_instance=self 로 메인 GUI 전달)
        ScoringDialog(self.root, self.db_engine, test, problems, existing_scores,
                      source_hwp_dir=self.source_hwp_dir.get(),
                      gui_instance=self)


    # =========================================================
    # 사용자 관리 탭 (admin 전용) — Phase 2-H
    # =========================================================
    def _build_users_tab(self):
        """admin 전용: 사용자 목록 + 신규 발급 / 비번 재설정 / 비활성화."""
        from backend import user_admin

        for w in self.tab_users.winfo_children():
            w.destroy()

        # ── 헤더 ────────────────────────────────────────────────
        header = tk.Frame(self.tab_users, bg=CLR_BG)
        header.pack(fill="x", padx=18, pady=(14, 8))

        tk.Label(header, text="👥 사용자 관리",
                 bg=CLR_BG, fg=CLR_FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        tk.Button(header, text="+ 새 계정 발급",
                  command=self._users_new_account_dialog,
                  bg=CLR_ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"),
                  padx=14, pady=6, cursor="hand2").pack(side="right")
        tk.Button(header, text="↻ 새로고침",
                  command=self._build_users_tab,
                  bg=CLR_PANEL, fg=CLR_FG, relief="flat",
                  font=("Segoe UI", 9),
                  padx=10, pady=6, cursor="hand2").pack(side="right", padx=(0, 8))

        # ── 사용자 목록 ─────────────────────────────────────────
        list_fr = tk.Frame(self.tab_users, bg=CLR_BG)
        list_fr.pack(fill="both", expand=True, padx=18, pady=8)

        # 컬럼 헤더
        hdr = tk.Frame(list_fr, bg="#252525")
        hdr.pack(fill="x")
        for txt, w in [("ID", 14), ("이름", 14), ("역할", 8), ("상태", 8), ("작업", 50)]:
            tk.Label(hdr, text=txt, bg="#252525", fg="#cccccc",
                     font=("Segoe UI", 9, "bold"),
                     width=w, anchor="w").pack(side="left", padx=4, pady=6)

        # 스크롤 영역
        canvas = tk.Canvas(list_fr, bg=CLR_BG, highlightthickness=0)
        sb = ttk.Scrollbar(list_fr, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=CLR_BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # 마우스 휠 — Enter/Leave 토글 (전역 가로채기 방지)
        def _mwheel(e):
            try:
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _mwheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        inner.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _mwheel))
        inner.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        try:
            users = user_admin.list_users()
        except Exception as e:
            tk.Label(inner, text=f"사용자 목록 조회 실패: {e}",
                     bg=CLR_BG, fg="#ff6b6b",
                     font=("Segoe UI", 10)).pack(pady=20)
            return

        if not users:
            tk.Label(inner, text="등록된 사용자가 없습니다.",
                     bg=CLR_BG, fg="#888",
                     font=("Segoe UI", 10)).pack(pady=20)
            return

        for u in users:
            self._users_make_row(inner, u)

    def _users_make_row(self, parent, user: dict):
        """사용자 한 명 행 렌더링."""
        from backend import user_admin

        uid = user.get("uid", "")
        display_id = user.get("display_id", "")
        display_name = user.get("display_name", "") or "-"
        role = user.get("role", "user")
        active = bool(user.get("active", True))
        is_self = (uid == self.current_user_id)

        row_bg = "#2a2a2a" if active else "#3a2a2a"
        row = tk.Frame(parent, bg=row_bg)
        row.pack(fill="x", pady=1)

        tk.Label(row, text=display_id, bg=row_bg, fg=CLR_FG,
                 font=("Segoe UI", 10), width=14, anchor="w").pack(side="left", padx=4, pady=6)
        tk.Label(row, text=display_name, bg=row_bg, fg="#cccccc",
                 font=("Segoe UI", 10), width=14, anchor="w").pack(side="left", padx=4, pady=6)

        role_color = "#ffb74d" if role == "admin" else "#90caf9"
        tk.Label(row, text=role, bg=row_bg, fg=role_color,
                 font=("Segoe UI", 9, "bold"), width=8, anchor="w").pack(side="left", padx=4, pady=6)

        status_txt = "활성" if active else "비활성"
        status_color = "#06c98a" if active else "#ff6b6b"
        tk.Label(row, text=status_txt, bg=row_bg, fg=status_color,
                 font=("Segoe UI", 9), width=8, anchor="w").pack(side="left", padx=4, pady=6)

        # ── 액션 버튼 ────────────────────────────────────────
        btn_fr = tk.Frame(row, bg=row_bg)
        btn_fr.pack(side="left", padx=4)

        def _btn(parent_, text, color, cmd, state="normal"):
            b = tk.Button(parent_, text=text, command=cmd,
                          bg=color, fg="white",
                          font=("Segoe UI", 8, "bold"),
                          relief="flat", padx=8, pady=2,
                          cursor="hand2", state=state)
            b.pack(side="left", padx=2)
            return b

        # 비번 재설정 — 모두 가능
        _btn(btn_fr, "비번 재설정", "#3a86ff",
             lambda u=user: self._users_reset_password_dialog(u))

        # 활성/비활성 토글 — 본인 비활성화 차단
        if is_self:
            _btn(btn_fr, "비활성화", "#666666", lambda: None, state="disabled")
        elif active:
            _btn(btn_fr, "비활성화", "#c62828",
                 lambda u=user: self._users_toggle_active(u, False))
        else:
            _btn(btn_fr, "활성화", "#06c98a",
                 lambda u=user: self._users_toggle_active(u, True))

        # 역할 토글 — 본인 강등 차단
        if not is_self:
            target_role = "user" if role == "admin" else "admin"
            _btn(btn_fr, f"→ {target_role}", "#7c3aed",
                 lambda u=user, r=target_role: self._users_change_role(u, r))

        # 삭제 — 본인 차단
        if not is_self:
            _btn(btn_fr, "삭제", "#9e1010",
                 lambda u=user: self._users_delete(u))

    # ── 사용자 관리 액션들 ─────────────────────────────────────────

    def _users_new_account_dialog(self):
        """신규 계정 발급 다이얼로그."""
        from backend import user_admin

        dlg = tk.Toplevel(self.root)
        dlg.title("새 계정 발급")
        dlg.configure(bg=CLR_BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        w, h = 360, 420
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dlg, text="새 계정 발급", bg=CLR_BG, fg=CLR_FG,
                 font=("Segoe UI", 13, "bold")).pack(pady=(18, 14))

        form = tk.Frame(dlg, bg=CLR_BG)
        form.pack(padx=24, fill="x")

        def _make_entry(label, show=None):
            tk.Label(form, text=label, bg=CLR_BG, fg=CLR_FG,
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 2))
            e = tk.Entry(form, bg="#3a3a3a", fg=CLR_FG,
                         insertbackground=CLR_FG, relief="flat",
                         font=("Segoe UI", 10), show=show or "")
            e.pack(fill="x", ipady=5)
            return e

        e_id = _make_entry("ID (예: kim)")
        e_name = _make_entry("이름 (선택)")
        e_pw = _make_entry("임시 비밀번호 (6자 이상)", show="•")

        # role 선택
        tk.Label(form, text="역할", bg=CLR_BG, fg=CLR_FG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 2))
        role_var = tk.StringVar(value="user")
        role_fr = tk.Frame(form, bg=CLR_BG)
        role_fr.pack(anchor="w")
        for r_val, r_txt in [("user", "일반 사용자"), ("admin", "관리자")]:
            tk.Radiobutton(role_fr, text=r_txt, variable=role_var, value=r_val,
                           bg=CLR_BG, fg=CLR_FG, selectcolor=CLR_PANEL,
                           activebackground=CLR_BG, activeforeground=CLR_FG,
                           font=("Segoe UI", 9)).pack(side="left", padx=(0, 12))

        err = tk.Label(dlg, text="", bg=CLR_BG, fg="#ff6b6b",
                       font=("Segoe UI", 9))
        err.pack(pady=(8, 0))

        def _do_create():
            display_id = e_id.get().strip()
            display_name = e_name.get().strip()
            pw = e_pw.get()
            role = role_var.get()
            if not display_id:
                err.config(text="ID를 입력하세요.")
                return
            if not pw or len(pw) < 6:
                err.config(text="비밀번호는 6자 이상이어야 합니다.")
                return
            try:
                user_admin.create_user(display_id, pw, role=role,
                                        display_name=display_name)
            except Exception as e:
                err.config(text=f"실패: {e}")
                return
            dlg.destroy()
            messagebox.showinfo("완료",
                f"계정 발급 완료\n\nID: {display_id}\n비번: {pw}\n역할: {role}\n\n사용자에게 전달하세요.")
            self._build_users_tab()

        btn_fr = tk.Frame(dlg, bg=CLR_BG)
        btn_fr.pack(pady=14)
        tk.Button(btn_fr, text="취소", command=dlg.destroy,
                  bg="#555555", fg="white", relief="flat",
                  font=("Segoe UI", 10), padx=18, pady=6,
                  cursor="hand2").pack(side="left", padx=4)
        tk.Button(btn_fr, text="발급", command=_do_create,
                  bg=CLR_ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=22, pady=6,
                  cursor="hand2").pack(side="left", padx=4)

        e_id.focus_set()

    def _users_reset_password_dialog(self, user: dict):
        """비번 재설정 다이얼로그."""
        from backend import user_admin

        new_pw = simpledialog.askstring(
            "비밀번호 재설정",
            f"'{user.get('display_id')}' 의 새 임시 비밀번호 (6자 이상):",
            show="•", parent=self.root)
        if not new_pw:
            return
        if len(new_pw) < 6:
            messagebox.showerror("오류", "비밀번호는 6자 이상이어야 합니다.")
            return
        try:
            user_admin.reset_password(user["uid"], new_pw)
        except Exception as e:
            messagebox.showerror("실패", str(e))
            return
        messagebox.showinfo("완료",
            f"비밀번호 재설정 완료\n\nID: {user.get('display_id')}\n새 비번: {new_pw}\n\n사용자에게 전달하세요.")

    def _force_logout_if_self(self, target_uid: str, reason: str):
        """대상이 본인이면 즉시 로그아웃 (defense-in-depth)."""
        if target_uid != getattr(self, "current_user_id", None):
            return
        try:
            from backend import auth as _auth
            _auth.logout()
        except Exception:
            pass
        messagebox.showwarning("자동 로그아웃", f"{reason}\n프로그램을 다시 시작하세요.")
        try:
            self.root.destroy()
        except Exception:
            os._exit(0)

    def _users_toggle_active(self, user: dict, active: bool):
        from backend import user_admin

        action = "활성화" if active else "비활성화"
        if not messagebox.askyesno("확인",
                f"'{user.get('display_id')}' 계정을 {action}하시겠습니까?"):
            return
        try:
            user_admin.set_active(user["uid"], active)
        except Exception as e:
            messagebox.showerror("실패", str(e))
            return
        if not active:
            self._force_logout_if_self(user["uid"], "본인 계정이 비활성화되었습니다.")
        self._build_users_tab()

    def _users_change_role(self, user: dict, new_role: str):
        from backend import user_admin

        if not messagebox.askyesno("확인",
                f"'{user.get('display_id')}' 의 역할을 '{new_role}' 로 변경하시겠습니까?"):
            return
        try:
            user_admin.update_role(user["uid"], new_role)
        except Exception as e:
            messagebox.showerror("실패", str(e))
            return
        if new_role != "admin":
            self._force_logout_if_self(user["uid"], "본인 권한이 변경되었습니다.")
        self._build_users_tab()

    def _users_delete(self, user: dict):
        from backend import user_admin

        if not messagebox.askyesno("⚠ 삭제 확인",
                f"'{user.get('display_id')}' 계정을 정말 삭제하시겠습니까?\n\n"
                f"이 작업은 되돌릴 수 없습니다.\n"
                f"Firebase Auth + Firestore users/ 양쪽에서 영구 삭제됩니다.",
                icon="warning"):
            return
        try:
            user_admin.delete_user(user["uid"])
        except Exception as e:
            messagebox.showerror("실패", str(e))
            return
        self._force_logout_if_self(user["uid"], "본인 계정이 삭제되었습니다.")
        self._build_users_tab()

class ScoringDialog:
    """
    채점 화면 다이얼로그.
    - 각 문항 번호 옆에 O/X 토글 버튼 (기본 O)
    - 세로 20개 × 가로 5단 레이아웃 (큼직한 버튼)
    - [적용] 버튼: 채점 저장 → X 문항만 골라 오답 시험지 생성
    """

    COLS = 10       # 가로 단 수
    ROWS = 20       # 단당 세로 문항 수

    def __init__(self, parent, db_engine, test, problems, existing_scores, source_hwp_dir="", gui_instance=None):
        self.db_engine = db_engine
        self.test = test
        self.problems = problems
        self.source_hwp_dir = source_hwp_dir
        self.gui = gui_instance  # 메인 GUI 인스턴스 (HWP 생성 공통 루트 사용)

        self.top = tk.Toplevel(parent)
        self.top.title(f"채점 - {test.get('title', '')}")
        self.top.grab_set()
        self.top.resizable(True, True)

        # 창 크기: 화면의 95% 이내로 제한 (10단이라 넓게)
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        w = min(self.COLS * 130 + 40, int(sw * 0.95))
        h = min(int(sh * 0.85), 780)
        h = max(h, 400)
        x = (sw - w) // 2
        y = max(30, (sh - h) // 2 - 30)
        self.top.geometry(f"{w}x{h}+{x}+{y}")

        # 상태 변수: {problem_id: BooleanVar}  True=O, False=X
        self.score_vars = {}

        self._build_ui(existing_scores)

    def _build_ui(self, existing_scores):
        top = self.top

        # ── 상단 제목바 + 버튼 ──
        title_bar = tk.Frame(top, bg="#7b1fa2", pady=8)
        title_bar.pack(fill="x")
        tk.Label(title_bar,
                 text=f"채점  |  {self.test.get('title', '')}  ({len(self.problems)}문항)",
                 font=("Segoe UI", 12, "bold"), bg="#7b1fa2", fg="white").pack(side="left", padx=15)

        # 버튼 3개 - 타이틀바 우측
        tk.Button(title_bar, text="닫기", command=self.top.destroy,
                  bg="#9c4dbb", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10, pady=2).pack(side="right", padx=6)
        tk.Button(title_bar, text="▶ 시험지 생성",
                  command=self._generate_hwp,
                  bg="#1565c0", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10, pady=2).pack(side="right", padx=4)
        tk.Button(title_bar, text="✔ 적용 (저장)",
                  command=self._save_scores_and_open_dialog,
                  bg="#2e7d32", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10, pady=2).pack(side="right", padx=4)

        # ── 스크롤 영역 ──
        canvas_frame = tk.Frame(top, bg="white")
        canvas_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(canvas_frame, bg="white", highlightthickness=0)
        vscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="white")
        canvas_win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_win, width=e.width)
        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # 마우스 휠 스크롤 (Enter/Leave 토글 → 다이얼로그 외부 가로채기 방지)
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ── 문항 버튼 배치 (세로 ROWS개 × 가로 COLS단) ──
        # 각 단(column group)은 프레임으로 구성
        col_frames = []
        for c in range(self.COLS):
            cf = tk.Frame(inner, bg="white", padx=8)
            cf.pack(side="left", anchor="n", padx=4, pady=10)
            col_frames.append(cf)

        for idx, prob in enumerate(self.problems):
            pid = prob.get("id", f"__idx_{idx}")
            col = idx // self.ROWS          # 단 번호
            if col >= self.COLS:
                col = self.COLS - 1         # 넘치면 마지막 단에 이어붙임

            cf = col_frames[col]

            # 초기값: 항상 O(True) - 새 채점 시작
            init_val = True
            var = tk.BooleanVar(value=init_val)
            self.score_vars[pid] = var

            row_frame = tk.Frame(cf, bg="white")
            row_frame.pack(fill="x", pady=2)

            # 번호 레이블
            tk.Label(row_frame, text=f"{idx + 1}번",
                     font=("Segoe UI", 10, "bold"), bg="white",
                     width=4, anchor="e").pack(side="left", padx=(0, 4))

            # O/X 토글 버튼
            btn = tk.Button(row_frame, width=4, font=("Segoe UI", 13, "bold"),
                            relief="flat", cursor="hand2")

            def _make_toggle(b, v):
                def _toggle():
                    v.set(not v.get())
                    if v.get():
                        b.config(text="O", bg="#43a047", fg="white")
                    else:
                        b.config(text="X", bg="#e53935", fg="white")
                return _toggle

            toggle_fn = _make_toggle(btn, var)
            btn.config(command=toggle_fn)
            # 초기 색상 적용
            if init_val:
                btn.config(text="O", bg="#43a047", fg="white")
            else:
                btn.config(text="X", bg="#e53935", fg="white")
            btn.pack(side="left")

        # 저장 후 생성에 쓸 wrong_problems 캐시
        self._wrong_problems = []
        self._saved_test_id = None

    def _collect_wrong_problems(self):
        """X 문항 추출 + 채점 DB 저장. 오답 없으면 None 반환."""
        scores = {pid: (1 if var.get() else 0) for pid, var in self.score_vars.items()}
        self.db_engine.save_scores(self.test["id"], scores)
        wrong = [p for p in self.problems if not scores.get(p.get("id", ""), True)]
        return wrong

    def _save_scores_and_open_dialog(self):
        """적용(저장): 채점 저장 + 저장 다이얼로그 (Step4와 동일)"""
        wrong = self._collect_wrong_problems()
        if not wrong:
            messagebox.showinfo("안내", "오답이 없습니다. 모두 O로 채점됐습니다.", parent=self.top)
            return
        self._wrong_problems = wrong
        self._open_save_dialog(wrong)

    def _open_save_dialog(self, wrong_problems):
        """랜덤출제 Step4의 저장 다이얼로그와 동일한 형태"""
        orig_title = self.test.get("title", "")
        orig_unit = self.test.get("unit_summary", "")

        dlg = tk.Toplevel(self.top)
        dlg.title("오답 시험지 저장")
        dlg.geometry("400x360")
        dlg.resizable(False, False)
        dlg.grab_set()
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        dlg.geometry(f"+{(sw-400)//2}+{(sh-360)//2}")

        container = tk.Frame(dlg, padx=20, pady=20)
        container.pack(fill="both", expand=True)

        # 제목
        tk.Label(container, text="시험지 이름", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entry_title = tk.Entry(container, font=("Segoe UI", 10))
        entry_title.pack(fill="x", pady=(0, 10))
        entry_title.insert(0, f"{orig_title}의 오답")

        # 단원
        tk.Label(container, text="출제 단원 (요약)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entry_unit = tk.Entry(container, font=("Segoe UI", 10))
        entry_unit.pack(fill="x", pady=(0, 10))
        entry_unit.insert(0, orig_unit)

        # 저장 폴더 (기본값: 오답 폴더)
        tk.Label(container, text="저장 폴더", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        folders = self.db_engine.get_folders(self.gui.current_user_id)
        folder_opts = ["/ (최상위)"] + [f"📁 {f['name']}" for f in folders]
        folder_ids  = [None]          + [f["id"]           for f in folders]

        cbo_folder = ttk.Combobox(container, values=folder_opts, state="readonly",
                                  font=("Segoe UI", 10))
        cbo_folder.pack(fill="x", pady=(0, 5))
        # 오답 폴더를 기본 선택 — 없으면 lazy 발급 후 폴더 목록 새로고침
        wrong_folder_id = self.db_engine.get_protected_folder_id("오답", self.gui.current_user_id)
        if wrong_folder_id is None and hasattr(self.db_engine, "ensure_protected_folder"):
            try:
                wrong_folder_id = self.db_engine.ensure_protected_folder(self.gui.current_user_id, "오답")
                folders = self.db_engine.get_folders(self.gui.current_user_id)
                folder_opts = ["/ (최상위)"] + [f"📁 {f['name']}" for f in folders]
                folder_ids  = [None]          + [f["id"]           for f in folders]
                cbo_folder["values"] = folder_opts
            except Exception as e:
                print(f"[ScoringDialog] 오답 폴더 lazy 발급 실패: {e}")
        default_idx = next((i for i, fid in enumerate(folder_ids) if fid == wrong_folder_id), 0)
        cbo_folder.current(default_idx)

        def _add_folder():
            import tkinter.simpledialog as sd
            name = sd.askstring("새 폴더", "폴더 이름:", parent=dlg)
            if name:
                res = self.db_engine.create_folder(name, self.gui.current_user_id)
                if res["success"]:
                    folders2 = self.db_engine.get_folders(self.gui.current_user_id)
                    opts2 = ["/ (최상위)"] + [f"📁 {f['name']}" for f in folders2]
                    ids2  = [None]          + [f["id"]           for f in folders2]
                    cbo_folder["values"] = opts2
                    ni = next((i for i, f in enumerate(folders2) if f["id"] == res["id"]), -1)
                    if ni != -1:
                        cbo_folder.current(ni + 1)
                    nonlocal folder_ids
                    folder_ids = ids2
                else:
                    messagebox.showerror("오류", res["message"], parent=dlg)

        tk.Button(container, text="+ 새 폴더 만들기", command=_add_folder,
                  bg="#f0f0f0", relief="flat").pack(anchor="e", pady=(0, 15))

        def _do_save():
            title = entry_title.get().strip()
            unit  = entry_unit.get().strip()
            if not title:
                messagebox.showwarning("필수", "시험지 이름을 입력하세요.", parent=dlg)
                return
            idx = cbo_folder.current()
            dir_id = folder_ids[idx if idx >= 0 else 0]
            p_ids = [p["id"] for p in wrong_problems]
            res = self.db_engine.save_test({
                "title": title,
                "unit_summary": unit,
                "directory_id": dir_id,
                "problem_ids": p_ids,
                "metadata": {"source_test_id": self.test["id"], "type": "wrong_answers"}
            }, self.gui.current_user_id)
            if res["success"]:
                self._saved_test_id = res["id"]
                # 시험지 생성 버튼을 위해 제목/단원 기억
                self._saved_wa_title = title
                self._saved_wa_unit  = unit
                messagebox.showinfo("저장 완료", "오답 시험지가 저장되었습니다.", parent=dlg)
                dlg.destroy()
            else:
                messagebox.showerror("저장 실패", res["message"], parent=dlg)

        btn_area = tk.Frame(dlg, pady=10)
        btn_area.pack(fill="x", side="bottom")
        tk.Button(btn_area, text="저장", command=_do_save,
                  bg="#7b1fa2", fg="white", font=("Segoe UI", 10, "bold"),
                  width=10).pack(side="right", padx=10)
        tk.Button(btn_area, text="취소", command=dlg.destroy, width=8).pack(side="right")

    def _generate_hwp(self):
        """시험지 생성: 메인 GUI의 공통 루트(_open_generate_dialog → _start_hwp_generation_process) 그대로 사용"""
        if self.gui is None:
            messagebox.showerror("오류", "GUI 인스턴스를 찾을 수 없습니다.", parent=self.top)
            return

        # 오답 문항이 없으면 채점 먼저 수집
        if not self._wrong_problems:
            wrong = self._collect_wrong_problems()
            if not wrong:
                messagebox.showinfo("안내", "오답이 없습니다.", parent=self.top)
                return
            self._wrong_problems = wrong

        wa_title = getattr(self, "_saved_wa_title", f"{self.test.get('title', '')}의 오답")
        wa_unit  = getattr(self, "_saved_wa_unit",  self.test.get("unit_summary", ""))

        # ★ 메인 GUI의 final_problems에 오답 문항 세팅
        self.gui.final_problems = self._wrong_problems
        # ★ 메인 GUI의 saved_exam_title/unit에 오답 제목/단원 세팅
        self.gui.saved_exam_title = wa_title
        self.gui.saved_exam_unit  = wa_unit

        # 채점 창 닫고
        self.top.destroy()

        # ★ 메인 GUI의 공통 출제 다이얼로그 호출 (랜덤출제/시험지출제와 완전히 동일한 루트)
        self.gui._open_generate_dialog()

    def _resolve_hwp_path(self, filename, user_dir=""):
        """파일명으로 원본 HWP 경로 탐색"""
        import os
        # 모듈 레벨 base_dir 사용 (frozen=exe 옆, dev=프로젝트 루트)
        parent_dir = os.path.dirname(base_dir)
        scan_dirs = []
        if user_dir and os.path.exists(user_dir):
            scan_dirs.append(user_dir)
        scan_dirs += [os.path.join(base_dir, "exercise"), base_dir]
        # 직접 검색
        for d in scan_dirs:
            cand = os.path.join(d, filename)
            if os.path.exists(cand):
                return cand
        # 재귀 탐색
        for d in ([user_dir] if user_dir and os.path.exists(user_dir) else []) + [base_dir, parent_dir]:
            for root, _, files in os.walk(d):
                if filename in files:
                    return os.path.join(root, filename)
        return None


class ExclusionSettingDialog:
    """일회성 출제 제외 시험지 선택 다이얼로그.

    DB의 is_excluded 컬럼은 건드리지 않음 (문제관리 탭의 영구 제외 전용).
    체크된 시험지의 problem_ids는 gui._oneshot_excluded_problem_ids에 저장되어
    한 시험지 작성 세션 동안만 출제에서 제외됨.

    - 폴더 탭: 폴더 클릭 → 하위 시험지 펼침(아코디언)
    - 날짜 탭: 최신순으로 전체 시험지 나열
    - 체크 = 이번 출제에서 제외, 해제 = 다시 출제 풀에 포함
    - [✔ 적용] 으로 반영, [닫기]로 취소
    """

    def __init__(self, parent, db_engine, gui):
        self.db_engine = db_engine
        self.gui = gui  # ModernProblemScannerGUI 참조 (oneshot set 갱신용)

        self.top = tk.Toplevel(parent)
        self.top.title("일회성 출제 제외 시험지 선택")
        self.top.geometry("700x600")
        self.top.grab_set()
        self.top.resizable(True, True)

        # 체크 상태: {test_id: BooleanVar}  (두 탭 공유)
        self.check_vars = {}

        # 시험지별 problem_ids 캐시 (다이얼로그 수명 동안만)
        self._test_pids = {}        # test_id → list[int]
        self._total_count = {}      # test_id → int
        self._load_test_pids()

        # 초기 체크 상태 = gui의 oneshot test_ids (재오픈 시 이전 선택 유지)
        self._initial_test_ids = set(getattr(self.gui, '_oneshot_excluded_test_ids', set()) or set())

        # ── 상단 바 (제목 + 적용/닫기) ──
        top_bar = tk.Frame(self.top, bg="#2d2d2d", pady=6)
        top_bar.pack(fill="x", side="top")

        tk.Label(top_bar, text="일회성 출제 제외 시험지 선택", bg="#2d2d2d", fg="white",
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=12)

        tk.Button(top_bar, text="닫기",
                  command=self.top.destroy,
                  bg="#555", fg="white", font=("Segoe UI", 9),
                  relief="flat", padx=10, pady=2).pack(side="right", padx=6)

        tk.Button(top_bar, text="✔ 적용",
                  command=self._apply,
                  bg="#1976d2", fg="white", font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=12, pady=2).pack(side="right", padx=2)

        # ── 안내 배너 ──
        banner = tk.Frame(self.top, bg="#e8f5e9", pady=6)
        banner.pack(fill="x", side="top")
        tk.Label(
            banner,
            text="✓ 체크한 시험지의 모든 문제는 이번 출제에서만 제외됩니다 (DB 미저장).",
            bg="#e8f5e9", fg="#2e7d32", font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=10)
        tk.Label(
            banner,
            text="새 시험지 시작(돌아가기/닫기) 시 자동 초기화됩니다.",
            bg="#e8f5e9", fg="#666", font=("Segoe UI", 8),
        ).pack(side="left", padx=4)

        # ── 현재 선택 요약 ──
        self.summary_var = tk.StringVar()
        self._update_summary()
        tk.Label(self.top, textvariable=self.summary_var, bg="#f5f5f5",
                 fg="#333", font=("Segoe UI", 9), anchor="w", pady=4
                 ).pack(fill="x", side="top", padx=6)

        # ── 탭 ──
        nb = ttk.Notebook(self.top)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        self.tab_folder = tk.Frame(nb, bg="white")
        self.tab_date   = tk.Frame(nb, bg="white")
        nb.add(self.tab_folder, text="  폴더별 보기  ")
        nb.add(self.tab_date,   text="  날짜별 보기  ")

        self._build_folder_tab()
        self._build_date_tab()

    # ── 헬퍼 ─────────────────────────────────────────────────

    def _load_test_pids(self):
        """모든 saved_tests의 problem_ids를 캐싱."""
        import sqlite3, json
        conn = sqlite3.connect(self.db_engine.db_path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, problem_ids FROM saved_tests")
            for row in cur.fetchall():
                try:
                    pids = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or [])
                except Exception:
                    pids = []
                self._test_pids[row[0]] = list(pids)
                self._total_count[row[0]] = len(pids)
        finally:
            conn.close()

    def _update_summary(self):
        """현재 체크된 시험지 수와 합산 문항 수를 상단 라벨에 갱신."""
        checked = {tid for tid, var in self.check_vars.items() if var.get()} \
                  if self.check_vars else set(self._initial_test_ids)
        n_tests = len(checked)
        n_pids = len({pid for tid in checked for pid in self._test_pids.get(tid, [])})
        if n_tests:
            self.summary_var.set(f"  현재 선택: {n_tests}개 시험지 / {n_pids}문항 제외 예정")
        else:
            self.summary_var.set("  현재 선택: 없음")

    def _make_check_row(self, parent, test_id, title, subtitle=""):
        """체크박스 행 생성. 체크된 시험지는 핑크 배경."""
        is_checked = test_id in self._initial_test_ids
        total_cnt = self._total_count.get(test_id, 0)
        bg = "#ffe8e8" if is_checked else "white"

        row = tk.Frame(parent, bg=bg, pady=2)
        row.pack(fill="x", padx=8)

        if test_id not in self.check_vars:
            var = tk.BooleanVar(value=is_checked)
            self.check_vars[test_id] = var
        else:
            var = self.check_vars[test_id]

        cb = tk.Checkbutton(row, variable=var, bg=bg, activebackground=bg,
                            command=lambda r=row, v=var: self._on_check_toggle(r, v))
        cb.pack(side="left")

        tk.Label(row, text=title, bg=bg, anchor="w",
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        if subtitle:
            tk.Label(row, text=f"  {subtitle}", bg=bg,
                     fg="#888", font=("Segoe UI", 8)).pack(side="left")

        tk.Label(row, text=f"{total_cnt}문항", bg=bg,
                 fg="#555", font=("Segoe UI", 8)).pack(side="right", padx=8)

    def _on_check_toggle(self, row_frame, var):
        """체크 변경 시 행 배경색 + 요약 라벨 갱신."""
        bg = "#ffe8e8" if var.get() else "white"
        row_frame.config(bg=bg)
        for child in row_frame.winfo_children():
            try:
                child.config(bg=bg)
            except Exception:
                pass
        self._update_summary()

    def _apply(self):
        """체크된 시험지의 problem_ids를 gui의 oneshot set에 반영 후 닫기."""
        checked_test_ids = {tid for tid, var in self.check_vars.items() if var.get()}

        new_pids = set()
        for tid in checked_test_ids:
            new_pids.update(self._test_pids.get(tid, []))

        self.gui._oneshot_excluded_test_ids    = checked_test_ids
        self.gui._oneshot_excluded_problem_ids = new_pids

        n_tests = len(checked_test_ids)
        n_pids  = len(new_pids)
        if n_tests:
            messagebox.showinfo(
                "적용 완료",
                f"✓ {n_tests}개 시험지 ({n_pids}문항) 가 이번 출제에서 제외됩니다.",
                parent=self.top,
            )
        else:
            messagebox.showinfo("적용 완료", "제외 시험지 없음.", parent=self.top)
        self.top.destroy()

    def _set_all_unchecked(self):
        """전체 해제: 모든 체크박스 OFF + 행 배경색 갱신."""
        self._initial_test_ids = set()
        self.check_vars.clear()
        for w in self.tab_folder.winfo_children(): w.destroy()
        for w in self.tab_date.winfo_children():   w.destroy()
        self._build_folder_tab()
        self._build_date_tab()
        self._update_summary()

    # ── 폴더 탭 (아코디언) ──────────────────────────────────────

    def _build_folder_tab(self):
        # 툴바
        tb = tk.Frame(self.tab_folder, bg="#f0f0f0", pady=4)
        tb.pack(fill="x")
        tk.Button(tb, text="⚡ 전체 해제",
                  command=self._set_all_unchecked,
                  bg="#e3f2fd", relief="flat", font=("Segoe UI", 9), padx=10).pack(side="left", padx=6)
        tk.Label(tb, text="시험지를 체크하면 그 시험지의 모든 문제가 이번 출제에서 제외됩니다.",
                 bg="#f0f0f0", fg="#666", font=("Segoe UI", 8)).pack(side="left", padx=8)

        # 스크롤 캔버스
        canvas = tk.Canvas(self.tab_folder, bg="white", highlightthickness=0)
        sb = ttk.Scrollbar(self.tab_folder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="white")
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        # 폴더 구조 로드
        folders   = self.db_engine.get_folders(self.gui.current_user_id)
        root_tests = self.db_engine.get_tests(directory_id=None, user_id=self.gui.current_user_id)

        def _make_accordion(parent_frame, label_text, tests, child_folders, depth=0):
            """아코디언 헤더 + 하위 시험지 목록 (계층 재귀 지원)"""
            is_open = tk.BooleanVar(value=False)
            pad_left = depth * 18

            hdr_bg = "#e8eaf6" if depth == 0 else "#ede7f6"
            hdr = tk.Frame(parent_frame, bg=hdr_bg, cursor="hand2")
            hdr.pack(fill="x", pady=(6 if depth == 0 else 3, 0), padx=(pad_left, 0))

            arrow_lbl = tk.Label(hdr, text="▶", bg=hdr_bg,
                                 font=("Segoe UI", 9), width=2)
            arrow_lbl.pack(side="left", padx=(6, 0))

            tk.Label(hdr, text=label_text, bg=hdr_bg,
                     font=("Segoe UI", 9, "bold"), anchor="w",
                     pady=5).pack(side="left", fill="x", expand=True)

            cnt_lbl = tk.Label(hdr, text=f"{len(tests)}개", bg=hdr_bg,
                               fg="#555", font=("Segoe UI", 8))
            cnt_lbl.pack(side="right", padx=8)

            body = tk.Frame(parent_frame, bg="#fafafa")

            if not tests and not child_folders:
                tk.Label(body, text="  시험지 없음", bg="#fafafa",
                         fg="#bbb", font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=4)
            else:
                for t in tests:
                    created = (t.get('created_at') or '')[:10]
                    self._make_check_row(body, t['id'], t['title'], subtitle=created)

            for cf in child_folders:
                cf_tests = self.db_engine.get_tests(directory_id=cf['id'], user_id=self.gui.current_user_id)
                cf_children = [f for f in folders if f.get("parent_id") == cf['id']]
                _make_accordion(body, f"📁 {cf['name']}", cf_tests, cf_children, depth + 1)

            def _toggle(e=None):
                if is_open.get():
                    body.pack_forget()
                    arrow_lbl.config(text="▶")
                    is_open.set(False)
                else:
                    body.pack(fill="x", after=hdr)
                    arrow_lbl.config(text="▼")
                    is_open.set(True)

            hdr.bind("<Button-1>", _toggle)
            arrow_lbl.bind("<Button-1>", _toggle)
            for child in hdr.winfo_children():
                child.bind("<Button-1>", _toggle)

        _make_accordion(inner, "📁 최상위 (폴더 없음)", root_tests, [], 0)

        root_level_folders = [f for f in folders if f.get("parent_id") is None]
        root_level_folders.sort(key=lambda x: x.get("name", ""))
        for folder in root_level_folders:
            tests = self.db_engine.get_tests(directory_id=folder['id'], user_id=self.gui.current_user_id)
            children = [f for f in folders if f.get("parent_id") == folder['id']]
            _make_accordion(inner, f"📁 {folder['name']}", tests, children, 0)

    # ── 날짜 탭 ─────────────────────────────────────────────────

    def _build_date_tab(self):
        # 툴바
        tb = tk.Frame(self.tab_date, bg="#f0f0f0", pady=4)
        tb.pack(fill="x")
        tk.Button(tb, text="⚡ 전체 해제",
                  command=self._set_all_unchecked,
                  bg="#e3f2fd", relief="flat", font=("Segoe UI", 9), padx=10).pack(side="left", padx=6)
        tk.Label(tb, text="시험지를 체크하면 그 시험지의 모든 문제가 이번 출제에서 제외됩니다.",
                 bg="#f0f0f0", fg="#666", font=("Segoe UI", 8)).pack(side="left", padx=8)

        canvas = tk.Canvas(self.tab_date, bg="white", highlightthickness=0)
        sb = ttk.Scrollbar(self.tab_date, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="white")
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        all_tests = self.db_engine.get_all_tests_sorted(self.gui.current_user_id)
        if not all_tests:
            tk.Label(inner, text="저장된 시험지가 없습니다.", bg="white",
                     fg="#aaa", font=("Segoe UI", 10)).pack(pady=20)
            return

        for t in all_tests:
            folder_name = t.get('folder_name') or '최상위'
            created = (t.get('created_at') or '')[:10]
            subtitle = f"[{folder_name}]  {created}"
            self._make_check_row(inner, t['id'], t['title'], subtitle=subtitle)



if __name__ == "__main__":
    # ── Firebase Admin SDK 초기화 ───────────────────────────────────
    # 키 파일은 .exe 와 분리됨. backend.firebase_init 가 우선순위로 탐색.
    from backend.firebase_init import init_admin_sdk, KeyNotFoundError
    try:
        _used_key = init_admin_sdk()
        if _used_key:
            print(f"[main_gui] Firebase admin key: {_used_key}")
    except KeyNotFoundError as _e:
        # 키 없음 → GUI 띄우기 전에 안내 다이얼로그 후 종료
        _err_root = tk.Tk()
        _err_root.withdraw()
        messagebox.showerror("Firebase 키 누락", str(_e))
        _err_root.destroy()
        sys.exit(1)

    # ── 로그인 (모달) — 메인 GUI 보이기 전에 ────────────────────────
    from backend.login_dialog import show_login_dialog
    _login_root = tk.Tk()
    _login_root.withdraw()  # 보이지 않게 (다이얼로그만 노출)
    _session = show_login_dialog(_login_root)
    _login_root.destroy()
    if _session is None:
        print("[main] 로그인 취소 → 종료")
        sys.exit(0)

    # ── 메인 GUI 시작 ─────────────────────────────────────────────
    root = tk.Tk()
    # Attempt to set dark title bar for Windows if possible
    try:
        from ctypes import windll, byref, sizeof, c_int
        HWND = windll.user32.GetParent(root.winfo_id())
        windll.dwmapi.DwmSetWindowAttribute(HWND, 35, byref(c_int(1)), sizeof(c_int))
    except:
        pass


    app = ModernProblemScannerGUI(root, session=_session)
    # 메인 창을 앞으로 가져오기 (다른 창/모니터에 가려 안 보이는 문제 방지)
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()
