# -*- coding: utf-8 -*-
"""
Phase 2-D: 로그인 모달 다이얼로그

설계도: 로그인시스템설계도.md §4-2

사용:
    from backend.login_dialog import show_login_dialog
    session = show_login_dialog(root)
    if session is None:
        sys.exit(0)  # 사용자가 취소 → 앱 종료
    # else: session = {uid, role, display_id, ...}

Modal: 이 다이얼로그가 닫힐 때까지 메인 창은 못 씀.
"""
import tkinter as tk
from tkinter import ttk

from backend import auth


CLR_BG = "#1e1e1e"
CLR_PANEL = "#2d2d2d"
CLR_FG = "#ffffff"
CLR_ACCENT = "#3a86ff"
CLR_ERROR = "#ff6b6b"
CLR_INPUT_BG = "#3a3a3a"


class LoginDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.parent = parent
        self.session = None  # 로그인 성공 시 채워짐

        self.title("로그인")
        self.configure(bg=CLR_BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build_ui()
        self._center_on_parent(380, 280)

        self.transient(parent)
        self.grab_set()
        # 로그인 창을 항상 최상위로 + 강제 표시 (다른 창/모니터에 가려 안 보이는 문제 방지)
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))
        self.focus_force()
        self.entry_id.focus_set()

    def _center_on_parent(self, w, h):
        self.update_idletasks()
        if self.parent.winfo_viewable():
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
        else:
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        # 타이틀
        title = tk.Label(self, text="상승수학 문항관리 시스템",
                         bg=CLR_BG, fg=CLR_FG,
                         font=("Segoe UI", 14, "bold"))
        title.pack(pady=(20, 4))
        sub = tk.Label(self, text="로그인", bg=CLR_BG, fg="#aaaaaa",
                       font=("Segoe UI", 10))
        sub.pack(pady=(0, 18))

        # 입력 영역
        form = tk.Frame(self, bg=CLR_BG)
        form.pack(padx=30, fill="x")

        tk.Label(form, text="ID", bg=CLR_BG, fg=CLR_FG,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.entry_id = tk.Entry(form, bg=CLR_INPUT_BG, fg=CLR_FG,
                                 insertbackground=CLR_FG,
                                 font=("Segoe UI", 11), relief="flat",
                                 highlightthickness=1, highlightcolor=CLR_ACCENT,
                                 highlightbackground="#555555")
        self.entry_id.grid(row=1, column=0, sticky="ew", ipady=6, pady=(0, 12))

        tk.Label(form, text="비밀번호", bg=CLR_BG, fg=CLR_FG,
                 font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", pady=(0, 2))
        self.entry_pw = tk.Entry(form, show="•", bg=CLR_INPUT_BG, fg=CLR_FG,
                                 insertbackground=CLR_FG,
                                 font=("Segoe UI", 11), relief="flat",
                                 highlightthickness=1, highlightcolor=CLR_ACCENT,
                                 highlightbackground="#555555")
        self.entry_pw.grid(row=3, column=0, sticky="ew", ipady=6, pady=(0, 8))

        form.columnconfigure(0, weight=1)

        # 에러 라벨
        self.lbl_err = tk.Label(self, text="", bg=CLR_BG, fg=CLR_ERROR,
                                font=("Segoe UI", 9))
        self.lbl_err.pack(pady=(0, 6))

        # 로그인 버튼
        self.btn_login = tk.Button(self, text="로그인",
                                   bg=CLR_ACCENT, fg="#ffffff",
                                   activebackground="#2563eb", activeforeground="#ffffff",
                                   font=("Segoe UI", 11, "bold"),
                                   relief="flat", cursor="hand2",
                                   command=self._on_login)
        self.btn_login.pack(padx=30, pady=(4, 16), fill="x", ipady=8)

        # 키바인딩
        self.entry_id.bind("<Return>", lambda e: self.entry_pw.focus_set())
        self.entry_pw.bind("<Return>", lambda e: self._on_login())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.btn_login.configure(state=state, text="로그인 중..." if busy else "로그인")
        self.entry_id.configure(state=state)
        self.entry_pw.configure(state=state)
        self.update_idletasks()

    def _on_login(self):
        display_id = self.entry_id.get().strip()
        password = self.entry_pw.get().strip()
        if not display_id:
            self._show_error("ID를 입력하세요.")
            self.entry_id.focus_set()
            return
        if not password:
            self._show_error("비밀번호를 입력하세요.")
            self.entry_pw.focus_set()
            return

        self.lbl_err.configure(text="")
        self._set_busy(True)
        try:
            session = auth.login(display_id, password)
        except auth.AuthError as e:
            self._set_busy(False)
            self._show_error(str(e))
            self.entry_pw.delete(0, "end")
            self.entry_pw.focus_set()
            return
        except Exception as e:
            self._set_busy(False)
            self._show_error(f"오류: {e}")
            return
        # 성공
        self.session = session
        self.destroy()

    def _on_cancel(self):
        self.session = None
        self.destroy()

    def _show_error(self, msg: str):
        self.lbl_err.configure(text=msg)


def show_login_dialog(parent: tk.Tk):
    """모달 로그인 다이얼로그를 띄우고 결과 세션 dict 또는 None 반환.

    캐시된 세션이 있으면 그것부터 자동 사용.
    """
    cached = auth.load_cached_session()
    if cached:
        return cached

    dlg = LoginDialog(parent)
    parent.wait_window(dlg)
    return dlg.session
