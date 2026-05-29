#!/usr/bin/env python3
"""
Scraper Control Panel Pro — redesigned UI.
"""

import subprocess
import sys
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import shlex
from datetime import datetime

# ========== CONFIGURATION ==========
PYTHON_EXE  = r"C:\Users\abdo\AppData\Local\Programs\Python\Python312\python.exe"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
# ===================================

SCRIPT_GROUPS = {
    "FaselHD": {
        "Series (all)":     [PYTHON_EXE, "-u", "FaselSeriesScraper.py"],
        "Series (asian)":   [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "asian-series"],
        "Series (tvshows)": [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "tvshows"],
        "Movies (all)":     [PYTHON_EXE, "-u", "FaselMoviesScraper.py"],
        "Movies (dubbed)":  [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "dubbed-movies"],
        "Movies (hindi)":   [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "hindi"],
        "Movies (asian)":   [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "asian-movies"],
        "Movies (anime)":   [PYTHON_EXE, "-u", "FaselMoviesScraper.py", "--category", "anime-movies"],
        "Anime":            [PYTHON_EXE, "-u", "FaselAnimeScraper.py"],
    },
    "Akwam": {
        "Arabic Series":    [PYTHON_EXE, "-u", "AkwamArabicSeries.py"],
    },
    "Episodes": {
        "Update All":       [PYTHON_EXE, "-u", "update_episodes.py"],
        "Update Specific":  [PYTHON_EXE, "-u", "update_specific_episodes.py"],
        "Check New":        [PYTHON_EXE, "-u", "check_new_episodes.py"],
    },
    "Ratings": {
        "IMDbAPI → TMDb → OMDb": [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "imdbapi,tmdb,omdb"],
        "TMDb → OMDb":           [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "tmdb,omdb"],
        "IMDbAPI → TMDb":        [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "imdbapi,tmdb"],
        "TMDb only":             [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "tmdb"],
        "IMDbAPI only":          [PYTHON_EXE, "-u", "update_ratings.py", "--sources", "imdbapi"],
        "TMDb‑first":            [PYTHON_EXE, "-u", "update_ratings.py", "--tmdb-first"],
        "Custom order":          [PYTHON_EXE, "-u", "update_ratings.py"],
        "Specific category":     [PYTHON_EXE, "-u", "update_ratings.py"],
    },
    "Series IMDb Match": {
        "All series":        [PYTHON_EXE, "-u", "match_series_imdb.py"],
        "Series only":       [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "series"],
        "TV Shows only":     [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "tvshows"],
        "Asian Series only": [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "asian-series"],
        "Anime only":        [PYTHON_EXE, "-u", "match_series_imdb.py", "--category", "anime"],
    },
    "MAL": {
        "Anime (all)":        [PYTHON_EXE, "-u", "update_mal.py"],
        "Anime only":         [PYTHON_EXE, "-u", "update_mal.py", "--category", "anime.json"],
        "Anime Movies only":  [PYTHON_EXE, "-u", "update_mal.py", "--category", "anime-movies.json"],
        "Force re-process":   [PYTHON_EXE, "-u", "update_mal.py", "--force"],
        "Specific IDs":       [PYTHON_EXE, "-u", "update_mal.py"],
    },
    "Metadata": {
        "Runtime: all sources":       [PYTHON_EXE, "-u", "update_runtime.py", "--sources", "imdbapi,tmdb,omdb"],
        "Runtime: IMDbAPI → TMDb":    [PYTHON_EXE, "-u", "update_runtime.py", "--sources", "imdbapi,tmdb"],
        "Runtime: IMDbAPI only":      [PYTHON_EXE, "-u", "update_runtime.py", "--sources", "imdbapi"],
        "Runtime: Custom order":      [PYTHON_EXE, "-u", "update_runtime.py"],
        "Runtime: Specific category": [PYTHON_EXE, "-u", "update_runtime.py"],
    },
}

BACKFILL_TASKS = {
    "All Tasks":    "all",
    "Movies":       "movies",
    "Descriptions": "descriptions",
}

# ── Colour palettes ──────────────────────────────────────────────────────────
DARK = dict(
    bg="#0f1117",
    sidebar="#161b27",
    sidebar_border="#1e2535",
    panel="#1a2030",
    fg="#c9d1e0",
    fg_muted="#5a6580",
    fg_section="#3a4d6a",
    text_bg="#0d1018",
    text_fg="#b8c4d8",
    accent="#3b82f6",
    accent_dim="#1d4ed8",
    run="#22c55e",
    run_dim="#16a34a",
    run_text="#ffffff",
    stop="#ef4444",
    stop_dim="#b91c1c",
    stop_text="#ffffff",
    stop_idle="#1e2535",
    stop_idle_fg="#3a4d6a",
    indicator_idle="#232d42",
    indicator_run="#22c55e",
    indicator_busy="#f59e0b",
    hover="#1e2a42",
    status_bg="#0d1018",
    status_fg="#5a6580",
    status_accent="#3b82f6",
)

LIGHT = dict(
    bg="#f4f6fb",
    sidebar="#eef1f8",
    sidebar_border="#dde3f0",
    panel="#ffffff",
    fg="#1e2740",
    fg_muted="#8896b5",
    fg_section="#b0bbd4",
    text_bg="#ffffff",
    text_fg="#1e2740",
    accent="#2563eb",
    accent_dim="#1d4ed8",
    run="#16a34a",
    run_dim="#15803d",
    run_text="#ffffff",
    stop="#dc2626",
    stop_dim="#b91c1c",
    stop_text="#ffffff",
    stop_idle="#e8ecf5",
    stop_idle_fg="#a0aec0",
    indicator_idle="#dde3f0",
    indicator_run="#16a34a",
    indicator_busy="#d97706",
    hover="#e4eaf8",
    status_bg="#eef1f8",
    status_fg="#8896b5",
    status_accent="#2563eb",
)


class PillButton(tk.Frame):
    def __init__(self, parent, text, command=None,
                 bg="#3b82f6", fg="#ffffff",
                 hover_bg=None, active_bg=None,
                 font=("Segoe UI", 11), padx=12, pady=4,
                 width=None, **kw):
        super().__init__(parent, bg=bg, cursor="hand2", **kw)

        self._bg     = bg
        self._fg     = fg
        self._hover  = hover_bg  or bg
        self._active = active_bg or bg
        self._cmd    = command
        self._enabled = True

        self._lbl = tk.Label(
            self, text=text, bg=bg, fg=fg,
            font=font, padx=padx, pady=pady,
            cursor="hand2",
        )
        if width:
            self._lbl.config(width=width)
        self._lbl.pack(fill=tk.BOTH, expand=True)

        for w in (self, self._lbl):
            w.bind("<Enter>",              self._on_enter)
            w.bind("<Leave>",              self._on_leave)
            w.bind("<Button-1>",           self._on_press)
            w.bind("<ButtonRelease-1>",    self._on_release)

    def _set_color(self, color):
        self.configure(bg=color)
        self._lbl.configure(bg=color)

    def _on_enter(self, _=None):
        if self._enabled:
            self._set_color(self._hover)

    def _on_leave(self, _=None):
        self._set_color(self._bg)

    def _on_press(self, _=None):
        if self._enabled:
            self._set_color(self._active)

    def _on_release(self, _=None):
        if self._enabled:
            self._set_color(self._hover)
            if self._cmd:
                self._cmd()

    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw.pop("state") != tk.DISABLED
            alpha = self._fg if self._enabled else self._active
            self._lbl.configure(fg=alpha)
        if "text" in kw:
            self._lbl.configure(text=kw.pop("text"))
        if "command" in kw:
            self._cmd = kw.pop("command")
        if "bg" in kw:
            self._bg = kw["bg"]
            self._lbl.configure(bg=kw["bg"])
        if "fg" in kw:
            self._fg = kw.pop("fg")
            if self._enabled:
                self._lbl.configure(fg=self._fg)
        if kw:
            super().configure(**kw)

    config = configure


class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Scraper Control Panel")
        root.geometry("1200x740")
        root.minsize(860, 520)

        self.processes         = {}
        self.output_tabs       = {}
        self.custom_procs      = {}
        self.indicators        = {}
        self._stopped_procs    = set()
        self.backfill_task_var = tk.StringVar(value="All Tasks")
        self.auto_scroll       = {}
        self.script_buttons    = {}

        self.dark_mode = True
        self.T         = DARK

        self._section_labels = []
        self._section_seps   = []

        self._build_ui()
        self._apply_theme()

    # -------------------------------------------------------------------------
    # UI CONSTRUCTION
    # -------------------------------------------------------------------------
    def _build_ui(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, minsize=252, weight=0)
        self.root.columnconfigure(1, minsize=1,   weight=0)
        self.root.columnconfigure(2, weight=1)

        # Status bar
        self.status_bar = tk.Frame(self.root, height=26)
        self.status_bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.status_bar.grid_propagate(False)

        self._status_dot = tk.Label(self.status_bar, text="●", font=("Segoe UI", 10))
        self._status_dot.pack(side=tk.LEFT, padx=(10, 4))

        self.status_var  = tk.StringVar(value="Ready")
        self._status_lbl = tk.Label(
            self.status_bar, textvariable=self.status_var,
            anchor="w", font=("Consolas", 10),
        )
        self._status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._clock_lbl = tk.Label(self.status_bar, font=("Consolas", 10), anchor="e")
        self._clock_lbl.pack(side=tk.RIGHT, padx=10)
        self._tick_clock()

        # Sidebar
        self.sidebar = tk.Frame(self.root, width=252)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.rowconfigure(1, weight=1)
        self.sidebar.columnconfigure(0, weight=1)

        self._title_bar = tk.Frame(self.sidebar, height=52)
        self._title_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._title_bar.grid_propagate(False)
        self._title_bar.columnconfigure(0, weight=1)

        self._title_lbl = tk.Label(
            self._title_bar, text="⬡  SCRAPER",
            font=("Segoe UI", 14, "bold"), anchor="w",
        )
        self._title_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=14)

        self._theme_btn = tk.Label(
            self._title_bar, text="◐",
            font=("Segoe UI", 16), cursor="hand2",
        )
        self._theme_btn.grid(row=0, column=1, padx=12)
        self._theme_btn.bind("<Button-1>", lambda _: self.toggle_dark_mode())

        self._sidebar_canvas = tk.Canvas(
            self.sidebar, highlightthickness=0, bd=0, width=250,
        )
        sb_scroll = ttk.Scrollbar(
            self.sidebar, orient=tk.VERTICAL,
            command=self._sidebar_canvas.yview,
        )
        self.scroll_frame = tk.Frame(self._sidebar_canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self._sidebar_canvas.configure(
                scrollregion=self._sidebar_canvas.bbox("all")
            )
        )
        self._sidebar_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self._sidebar_canvas.configure(yscrollcommand=sb_scroll.set)
        self._sidebar_canvas.grid(row=1, column=0, sticky="nsew")
        sb_scroll.grid(row=1, column=1, sticky="ns")
        self._sidebar_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._sidebar_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        )

        self._sidebar_footer = tk.Frame(self.sidebar, height=52)
        self._sidebar_footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._sidebar_footer.grid_propagate(False)
        self._sidebar_footer.columnconfigure(0, weight=1)
        self._sidebar_footer.columnconfigure(1, weight=1)

        self._custom_btn = PillButton(
            self._sidebar_footer, text="＋  Custom",
            command=self.add_custom_command,
            font=("Segoe UI", 10, "bold"),
            padx=8, pady=5,
        )
        self._custom_btn.grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=10)

        self._stop_all_btn = PillButton(
            self._sidebar_footer, text="⏹  Stop All",
            command=self.stop_all_scripts,
            font=("Segoe UI", 10, "bold"),
            padx=8, pady=5,
        )
        self._stop_all_btn.grid(row=0, column=1, sticky="ew", padx=(4, 10), pady=10)

        self._divider = tk.Frame(self.root, width=1)
        self._divider.grid(row=0, column=1, sticky="nsew")

        content = tk.Frame(self.root)
        content.grid(row=0, column=2, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(content)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))

        log_frame = tk.Frame(self.notebook)
        self.notebook.add(log_frame, text="  Log  ")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 11),
            state=tk.DISABLED, relief=tk.FLAT, bd=0,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        for tag, col in [("ok","#22c55e"),("warn","#f59e0b"),("err","#ef4444"),("dim","#4a5568")]:
            self.log_text.tag_configure(tag, foreground=col)
        self.auto_scroll[id(self.log_text)] = tk.BooleanVar(value=True)
        self._log(f"Started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        for group, scripts in SCRIPT_GROUPS.items():
            self._section_header(group)
            for name, cmd in scripts.items():
                self._script_row(name, cmd)

        self._section_header("Backfill")
        self._backfill_row()
        self._section_header("Manual")
        self._manual_row()

    def _tick_clock(self):
        self._clock_lbl.config(text=datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _section_header(self, text):
        f = tk.Frame(self.scroll_frame)
        f.pack(fill=tk.X, pady=(10, 0))

        lbl = tk.Label(
            f, text=text.upper(),
            font=("Segoe UI", 11, "bold"), anchor="w", padx=16, pady=2,
        )
        lbl.pack(fill=tk.X)
        self._section_labels.append(lbl)

        if text:
            sep = tk.Frame(f, height=1)
            sep.pack(fill=tk.X, padx=12, pady=(1, 0))
            self._section_seps.append(sep)

    def _script_row(self, name, cmd):
        T = self.T
        outer = tk.Frame(self.scroll_frame)
        outer.pack(fill=tk.X, padx=4, pady=1)
        outer.columnconfigure(1, weight=1)

        dot = tk.Label(outer, text="●", font=("Segoe UI", 10), width=2)
        dot.grid(row=0, column=0, padx=(6, 0), pady=4)
        self.indicators[name] = dot

        lbl = tk.Label(
            outer, text=name, anchor="w",
            font=("Segoe UI", 11), padx=4, pady=5, cursor="hand2",
        )
        lbl.grid(row=0, column=1, sticky="ew")

        stop_btn = PillButton(
            outer, text="⏹  Stop",
            command=lambda n=name: self.stop_script(n),
            font=("Segoe UI", 10), padx=10, pady=4,
        )
        stop_btn.grid(row=0, column=2, padx=(2, 6), pady=3)
        stop_btn.grid_remove()

        def _start(_evt=None, n=name, c=cmd):
            self.start_script(n, c)

        def _enter(_evt=None, o=outer, l=lbl, d=dot):
            bg = self.T["hover"]
            o.configure(bg=bg)
            l.configure(bg=bg)
            d.configure(bg=bg)

        def _leave(_evt=None, o=outer, l=lbl, d=dot):
            bg = self.T["sidebar"]
            o.configure(bg=bg)
            l.configure(bg=bg)
            d.configure(bg=bg)

        for w in (outer, lbl, dot):
            w.bind("<Button-1>", _start)
            w.bind("<Enter>",    _enter)
            w.bind("<Leave>",    _leave)

        self.script_buttons[name] = (lbl, stop_btn, outer)

    def _backfill_row(self):
        row = tk.Frame(self.scroll_frame)
        row.pack(fill=tk.X, padx=4, pady=(4, 2))
        row.columnconfigure(1, weight=1)
        self._backfill_row_frame = row

        dot = tk.Label(row, text="●", font=("Segoe UI", 10), width=2)
        dot.grid(row=0, column=0, padx=(6, 0))
        self.indicators["backfill"] = dot

        self.backfill_combo = ttk.Combobox(
            row, textvariable=self.backfill_task_var,
            values=list(BACKFILL_TASKS.keys()),
            state="readonly", font=("Segoe UI", 10),
        )
        self.backfill_combo.grid(row=0, column=1, sticky="ew", padx=(4, 2), pady=4)

        self.backfill_start_btn = PillButton(
            row, text="▶",
            command=self.start_backfill,
            font=("Segoe UI", 10, "bold"), padx=7, pady=2,
        )
        self.backfill_start_btn.grid(row=0, column=2, padx=2)

        self.backfill_stop_btn = PillButton(
            row, text="⏹  Stop",
            command=self.stop_backfill,
            font=("Segoe UI", 10), padx=10, pady=4,
        )
        self.backfill_stop_btn.grid(row=0, column=3, padx=(2, 6))
        self.backfill_stop_btn.grid_remove()

    def _manual_row(self):
        row = tk.Frame(self.scroll_frame)
        row.pack(fill=tk.X, padx=8, pady=(4, 16))

        self._imdb_btn = PillButton(
            row, text="✏  Set IMDb ID",
            command=self.open_imdb_dialog,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._imdb_btn.pack(fill=tk.X, padx=4, pady=2)

        self._rating_by_id_btn = PillButton(
            row, text="⭐  Get Rating by ID",
            command=self.open_rating_by_id,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._rating_by_id_btn.pack(fill=tk.X, padx=4, pady=2)

        self._mal_by_id_btn = PillButton(
            row, text="🎌  Get MAL by ID",
            command=self.open_mal_by_id,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._mal_by_id_btn.pack(fill=tk.X, padx=4, pady=2)

        self._runtime_by_id_btn = PillButton(
            row, text="⏱  Get Runtime by ID",
            command=self.open_runtime_by_id,
            font=("Segoe UI", 11), padx=10, pady=5,
        )
        self._runtime_by_id_btn.pack(fill=tk.X, padx=4, pady=2)

    # -------------------------------------------------------------------------
    # THEME
    # -------------------------------------------------------------------------
    def _style_stop_btn(self, btn, is_running):
        T = self.T
        if is_running:
            btn._bg    = T["stop"]
            btn._hover = T["stop_dim"]
            btn._active= T["stop_dim"]
            btn._fg    = T["stop_text"]
            btn._enabled = True
            btn._lbl.configure(fg=T["stop_text"])
            btn._set_color(btn._bg)
            try:
                btn.grid()
            except Exception:
                pass
        else:
            btn._bg    = T["stop_idle"]
            btn._hover = T["stop_idle"]
            btn._active= T["stop_idle"]
            btn._fg    = T["stop_idle_fg"]
            btn._enabled = False
            btn._lbl.configure(fg=T["stop_idle_fg"])
            btn._set_color(btn._bg)
            try:
                btn.grid_remove()
            except Exception:
                pass

    def _apply_theme(self):
        T = self.T

        self.root.configure(bg=T["bg"])

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame",        background=T["bg"])
        style.configure("TNotebook",     background=T["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=T["sidebar"], foreground=T["fg_muted"],
                        padding=[14, 6], font=("Segoe UI", 11))
        style.map("TNotebook.Tab",
                  background=[("selected", T["panel"]), ("active", T["hover"])],
                  foreground=[("selected", T["fg"]),    ("active", T["fg"])])
        style.configure("TScrollbar",    background=T["sidebar"],
                        troughcolor=T["bg"], borderwidth=0, arrowsize=10)
        style.configure("TCombobox",     fieldbackground=T["sidebar"],
                        foreground=T["fg"], background=T["sidebar"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", T["sidebar"])],
                  foreground=[("readonly", T["fg"])])

        for w in (self.sidebar, self._sidebar_canvas, self.scroll_frame,
                  self._title_bar, self._sidebar_footer):
            w.configure(bg=T["sidebar"])

        self._title_lbl.configure(bg=T["sidebar"], fg=T["fg"])
        self._theme_btn.configure(bg=T["sidebar"], fg=T["fg_muted"])
        self._divider.configure(bg=T["sidebar_border"])

        for lbl in self._section_labels:
            lbl.configure(bg=T["sidebar"], fg=T["fg_section"])
            lbl.master.configure(bg=T["sidebar"])
        for sep in self._section_seps:
            sep.configure(bg=T["sidebar_border"])

        for name, (lbl, stop_btn, outer) in self.script_buttons.items():
            outer.configure(bg=T["sidebar"])
            lbl.configure(bg=T["sidebar"], fg=T["fg"])
            dot = self.indicators.get(name)
            if dot:
                dot.configure(bg=T["sidebar"])
                running = name in self.processes and self.processes[name].poll() is None
                dot.configure(fg=T["indicator_run"] if running else T["indicator_idle"])
            running = name in self.processes and self.processes[name].poll() is None
            self._style_stop_btn(stop_btn, running)

        self._backfill_row_frame.configure(bg=T["sidebar"])
        bf_dot = self.indicators.get("backfill")
        if bf_dot:
            bf_dot.configure(bg=T["sidebar"])
            bf_run = "backfill" in self.processes and self.processes["backfill"].poll() is None
            bf_dot.configure(fg=T["indicator_run"] if bf_run else T["indicator_idle"])

        bf_run = "backfill" in self.processes and self.processes["backfill"].poll() is None
        self.backfill_start_btn._bg    = T["run"]
        self.backfill_start_btn._hover = T["run_dim"]
        self.backfill_start_btn._active= T["run_dim"]
        self.backfill_start_btn._fg    = T["run_text"]
        self.backfill_start_btn._lbl.configure(fg=T["run_text"])
        self.backfill_start_btn._set_color(T["run"])
        self._style_stop_btn(self.backfill_stop_btn, bf_run)

        self._custom_btn._bg    = T["accent"]
        self._custom_btn._hover = T["accent_dim"]
        self._custom_btn._active= T["accent_dim"]
        self._custom_btn._fg    = "#ffffff"
        self._custom_btn._lbl.configure(fg="#ffffff")
        self._custom_btn._set_color(T["accent"])

        self._stop_all_btn._bg    = T["stop"]
        self._stop_all_btn._hover = T["stop_dim"]
        self._stop_all_btn._active= T["stop_dim"]
        self._stop_all_btn._fg    = T["stop_text"]
        self._stop_all_btn._lbl.configure(fg=T["stop_text"])
        self._stop_all_btn._set_color(T["stop"])

        idle_bg = T["hover"]
        for btn in [self._imdb_btn, self._rating_by_id_btn, self._runtime_by_id_btn, self._mal_by_id_btn]:
            btn._bg    = idle_bg
            btn._hover = T["accent"]
            btn._active= T["accent_dim"]
            btn._fg    = T["fg"]
            btn._lbl.configure(fg=T["fg"])
            btn._set_color(idle_bg)
            btn.master.configure(bg=T["sidebar"])

        self.status_bar.configure(bg=T["status_bg"])
        self._status_dot.configure(bg=T["status_bg"], fg=T["status_accent"])
        self._status_lbl.configure(bg=T["status_bg"], fg=T["status_fg"])
        self._clock_lbl.configure(bg=T["status_bg"], fg=T["fg_muted"])

        self.log_text.configure(bg=T["text_bg"], fg=T["text_fg"],
                                insertbackground=T["fg"])
        for tag, col in [("ok", T["run"]), ("warn", T["indicator_busy"]),
                         ("err", T["stop"]), ("dim", T["fg_muted"])]:
            self.log_text.tag_configure(tag, foreground=col)

        for widget in self.output_tabs.values():
            try:
                widget.configure(bg=T["text_bg"], fg=T["text_fg"],
                                 insertbackground=T["fg"])
            except tk.TclError:
                pass

        for child in self.root.winfo_children():
            if isinstance(child, tk.Frame) and child not in (
                self.sidebar, self._divider, self.status_bar
            ):
                child.configure(bg=T["bg"])

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.T = DARK if self.dark_mode else LIGHT
        self._apply_theme()

    # -------------------------------------------------------------------------
    # SCRIPT CONTROL
    # -------------------------------------------------------------------------
    def start_script(self, name, cmd):
        if name in self.processes and self.processes[name].poll() is None:
            messagebox.showwarning("Already running", f'"{name}" is already running.')
            return
        extra = []
        if name == "Specific IDs":
            ids = simpledialog.askstring("Content IDs", "Enter IDs (space-separated):")
            if not ids:
                return
            extra = ["--ids"] + ids.split()
        elif name == "Update Specific":
            ids = simpledialog.askstring("Series IDs", "Enter IDs (space-separated):")
            if not ids:
                return
            extra = ["--ids"] + ids.split()
        elif name == "Custom order":
            sources = simpledialog.askstring(
                "Rating Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            extra = ["--sources", sources.strip()]
        elif name == "Specific category":
            sources = simpledialog.askstring(
                "Rating Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            category = simpledialog.askstring(
                "Category",
                "Enter category file name (e.g., movies.json, series.json)"
            )
            if not category:
                return
            extra = ["--sources", sources.strip(), "--category", category.strip()]
        elif name == "Runtime: Custom order":
            sources = simpledialog.askstring(
                "Runtime Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            extra = ["--sources", sources.strip()]
        elif name == "Runtime: Specific category":
            sources = simpledialog.askstring(
                "Runtime Sources",
                "Enter source order (comma-separated)\nOptions: imdbapi, tmdb, omdb"
            )
            if not sources:
                return
            category = simpledialog.askstring(
                "Category",
                "Enter category file name (e.g., movies.json, series.json)"
            )
            if not category:
                return
            extra = ["--sources", sources.strip(), "--category", category.strip()]

        proc, text_widget = self._run_subprocess(cmd + extra, name)
        if proc is None:
            return

        self.processes[name]   = proc
        self.output_tabs[name] = text_widget

        lbl, stop_btn, _ = self.script_buttons[name]
        lbl.config(fg=self.T["fg_muted"])
        self._style_stop_btn(stop_btn, True)
        self._set_indicator(name, True)
        self._set_status(f"▶  {name}")

    def stop_script(self, name):
        proc = self.processes.get(name)
        if not proc or proc.poll() is not None:
            return
        self._stopped_procs.add(proc.pid)
        self._kill_process(proc, name)
        self.processes.pop(name, None)
        self.output_tabs.pop(name, None)
        lbl, stop_btn, _ = self.script_buttons[name]
        lbl.config(fg=self.T["fg"])
        self._style_stop_btn(stop_btn, False)
        self._set_indicator(name, False)
        self._set_status(f"⏹  Stopped: {name}")

    def stop_all_scripts(self):
        names = list(self.processes.keys())
        if not names:
            self._set_status("Nothing running")
            return
        for name in names:
            proc = self.processes.get(name)
            if proc and proc.poll() is None:
                self._stopped_procs.add(proc.pid)
                self._kill_process(proc, name)
            self.processes.pop(name, None)
            self.output_tabs.pop(name, None)
            self._set_indicator(name, False)
            if name in self.script_buttons:
                lbl, stop_btn, _ = self.script_buttons[name]
                lbl.config(fg=self.T["fg"])
                self._style_stop_btn(stop_btn, False)
        self.backfill_start_btn.configure(state=tk.NORMAL)
        self._style_stop_btn(self.backfill_stop_btn, False)
        self._set_status(f"⏹  Stopped {len(names)} process(es)")

    def start_backfill(self):
        if "backfill" in self.processes and self.processes["backfill"].poll() is None:
            messagebox.showwarning("Already running", "Backfill is already running.")
            return
        task_label = self.backfill_task_var.get()
        cmd = [PYTHON_EXE, "-u", "backfill.py", "--task", BACKFILL_TASKS[task_label]]
        tab_name = f"Backfill: {task_label}"

        proc, text_widget = self._run_subprocess(cmd, tab_name)
        if proc is None:
            return

        self.processes["backfill"]   = proc
        self.output_tabs["backfill"] = text_widget
        self.backfill_start_btn.configure(state=tk.DISABLED)
        self._style_stop_btn(self.backfill_stop_btn, True)
        self._set_indicator("backfill", True)
        self._set_status(f"▶  Backfill: {task_label}")

        def _on_done():
            if proc.pid in self._stopped_procs:
                return
            self.root.after(0, lambda: self.backfill_start_btn.configure(state=tk.NORMAL))
            self.root.after(0, lambda: self._style_stop_btn(self.backfill_stop_btn, False))
            self.root.after(0, lambda: self._set_indicator("backfill", False))
            self.processes.pop("backfill", None)
            self.output_tabs.pop("backfill", None)

        threading.Thread(target=lambda: (proc.wait(), _on_done()), daemon=True).start()

    def stop_backfill(self):
        proc = self.processes.get("backfill")
        if not proc or proc.poll() is not None:
            return
        self._stopped_procs.add(proc.pid)
        self._kill_process(proc, "backfill")
        self.processes.pop("backfill", None)
        self.output_tabs.pop("backfill", None)
        self.backfill_start_btn.configure(state=tk.NORMAL)
        self._style_stop_btn(self.backfill_stop_btn, False)
        self._set_indicator("backfill", False)
        self._set_status("⏹  Backfill stopped")

    # -------------------------------------------------------------------------
    # CUSTOM COMMAND
    # -------------------------------------------------------------------------
    def add_custom_command(self):
        cmd_str = simpledialog.askstring(
            "Custom Command", "Enter command (e.g. python myscript.py --arg):"
        )
        if not cmd_str:
            return
        cmd_list = shlex.split(cmd_str)
        if cmd_list[0].lower() == "python":
            cmd_list[0] = PYTHON_EXE
        if cmd_list[0] == PYTHON_EXE and "-u" not in cmd_list:
            cmd_list.insert(1, "-u")

        tab_name  = f"Custom: {os.path.basename(cmd_list[0])}"
        tab_frame = tk.Frame(self.notebook)
        self.notebook.add(tab_frame, text=f"  {tab_name}  ")
        tab_frame.rowconfigure(0, weight=1)
        tab_frame.columnconfigure(0, weight=1)
        text_widget = self._make_output_widget(tab_frame, tab_name)

        proc, _ = self._run_subprocess(cmd_list, tab_name, text_widget)
        if proc:
            self.custom_procs[proc.pid] = (proc, text_widget, tab_frame, tab_name)
            threading.Thread(
                target=self._watch_custom, args=(proc, tab_frame, tab_name), daemon=True
            ).start()

    def _watch_custom(self, proc, tab_frame, tab_name):
        proc.wait()
        # Do NOT remove the tab automatically. Let the user close it via the close button.
        if proc.pid not in self._stopped_procs:
            # Optionally update the tab title to indicate it's finished
            for i in range(self.notebook.index("end")):
                try:
                    if self.notebook.tab(i, "text").strip() == tab_name:
                        self.notebook.tab(i, text=f"  {tab_name} (finished)  ")
                        break
                except tk.TclError:
                    pass
        else:
            self._stopped_procs.discard(proc.pid)
        self.custom_procs.pop(proc.pid, None)

    def _remove_custom_tab(self, tab_frame, tab_name, pid):
        for i in range(self.notebook.index("end")):
            try:
                if self.notebook.tab(i, "text").strip() == tab_name:
                    self.notebook.forget(i)
                    break
            except tk.TclError:
                pass
        self.custom_procs.pop(pid, None)

    # -------------------------------------------------------------------------
    # SUBPROCESS HELPERS
    # -------------------------------------------------------------------------
    def _run_subprocess(self, cmd, tab_name, text_widget=None):
        T = self.T
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        if text_widget is None:
            tab_frame = tk.Frame(self.notebook)
            self.notebook.add(tab_frame, text=f"  {tab_name}  ")
            tab_frame.rowconfigure(0, weight=1)
            tab_frame.columnconfigure(0, weight=1)
            text_widget = self._make_output_widget(tab_frame, tab_name)
            self.notebook.select(tab_frame)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=flags, env=env,
                cwd=SCRIPTS_DIR,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not start:\n{' '.join(cmd)}\n\n{e}")
            return None, None

        t0    = time.monotonic()
        stamp = datetime.now().strftime("%H:%M:%S")
        self._append_output(text_widget,
            f"{'─'*64}\n▶  {tab_name}  [{stamp}]\n{'─'*64}\n")

        def _reader():
            for line in iter(proc.stdout.readline, ""):
                self.root.after(0, lambda l=line: self._append_output(text_widget, l))
            proc.wait()

            if proc.pid in self._stopped_procs:
                self._stopped_procs.discard(proc.pid)
                return

            elapsed = time.monotonic() - t0
            mins, secs = divmod(int(elapsed), 60)
            elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            ts   = datetime.now().strftime("%H:%M:%S")
            code = proc.returncode
            self.root.after(0, lambda: self._append_output(
                text_widget,
                f"{'─'*64}\n{'✔' if code==0 else '✖'}  Finished (exit {code})  [{ts}]  ⏱ {elapsed_str}\n{'─'*64}\n"
            ))
            self.root.after(0, lambda: self._set_status(
                f"{'✔' if code==0 else '✖'}  Done: {tab_name}  (exit {code})  ⏱ {elapsed_str}"
            ))
            for sname, (slbl, stpbtn, _) in self.script_buttons.items():
                if self.processes.get(sname) is proc:
                    self.root.after(0, lambda b=slbl: b.config(fg=self.T["fg"]))
                    self.root.after(0, lambda b=stpbtn: self._style_stop_btn(b, False))
                    self.root.after(0, lambda n=sname: self._set_indicator(n, False))
                    self.processes.pop(sname, None)
                    self.output_tabs.pop(sname, None)
                    break

        threading.Thread(target=_reader, daemon=True).start()
        return proc, text_widget

    def _make_output_widget(self, parent, tab_name=None):
        T = self.T
        outer = tk.Frame(parent)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        text = scrolledtext.ScrolledText(
            outer, wrap=tk.WORD, font=("Consolas", 11),
            bg=T["text_bg"], fg=T["text_fg"],
            insertbackground=T["fg"], relief=tk.FLAT, bd=0,
        )
        text.grid(row=0, column=0, sticky="nsew")
        for tag, col in [("ok", T["run"]), ("warn", T["indicator_busy"]),
                         ("err", T["stop"]), ("dim", T["fg_muted"])]:
            text.tag_configure(tag, foreground=col)

        scroll_var = tk.BooleanVar(value=True)
        self.auto_scroll[id(text)] = scroll_var

        strip = tk.Frame(outer, height=28, bg=T["sidebar"])
        strip.grid(row=1, column=0, sticky="ew")

        def _clear(t=text):
            t.config(state=tk.NORMAL)
            t.delete("1.0", tk.END)
            t.config(state=tk.DISABLED)

        tk.Checkbutton(
            strip, text="Auto-scroll", variable=scroll_var,
            relief=tk.FLAT, bd=0, font=("Segoe UI", 10),
            bg=T["sidebar"], fg=T["fg_muted"],
            activebackground=T["sidebar"], selectcolor=T["sidebar"],
        ).pack(side=tk.RIGHT, padx=6, pady=3)

        tk.Button(
            strip, text="Clear", command=_clear,
            relief=tk.FLAT, bd=0, padx=8,
            font=("Segoe UI", 10),
            bg=T["sidebar"], fg=T["fg_muted"],
            activebackground=T["hover"],
        ).pack(side=tk.RIGHT, padx=2, pady=3)

        if tab_name:
            def _close_tab():
                for i in range(self.notebook.index("end")):
                    try:
                        if self.notebook.tab(i, "text").strip() == tab_name.strip():
                            self.notebook.forget(i)
                            break
                    except tk.TclError:
                        pass
                self.auto_scroll.pop(id(text), None)

            tk.Button(
                strip, text="✕  Close", command=_close_tab,
                relief=tk.FLAT, bd=0, padx=8,
                font=("Segoe UI", 10),
                bg=T["sidebar"], fg=T["fg_muted"],
                activebackground=T["hover"],
            ).pack(side=tk.LEFT, padx=6, pady=3)

        return text

    def _append_output(self, widget, line):
        was_disabled = str(widget.cget("state")) == "disabled"
        if was_disabled:
            widget.config(state=tk.NORMAL)

        tag = None
        low = line.lower()
        if any(x in line for x in ("✅", "🆕", "📦", "💾", "✔")):
            tag = "ok"
        elif any(x in line for x in ("⚠️", "⚠", "warning", "Warning")):
            tag = "warn"
        elif any(x in line for x in ("❌", "error", "Error", "Traceback", "Exception")):
            tag = "err"
        elif line.startswith("⏹") or "exit " in low:
            tag = "err" if ("exit 0" not in low and "exit " in low) else "dim"
        elif line.startswith("▶") or line.startswith("─"):
            tag = "dim"

        widget.insert(tk.END, line, tag) if tag else widget.insert(tk.END, line)

        if self.auto_scroll.get(id(widget), tk.BooleanVar(value=True)).get():
            widget.see(tk.END)

        if was_disabled:
            widget.config(state=tk.DISABLED)

    def _kill_process(self, proc, name=""):
        if proc is None or proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True
                )
                if result.returncode != 0:
                    proc.terminate()
            else:
                import signal as _signal
                try:
                    os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
                except Exception:
                    proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._log(f"⚠️ {name} (PID {proc.pid}) did not exit after kill\n")
        except Exception as e:
            self._log(f"⚠️ Error stopping {name}: {e}\n")

    def _set_indicator(self, key, running):
        dot = self.indicators.get(key)
        if dot:
            dot.configure(fg=self.T["indicator_run"] if running else self.T["indicator_idle"])

    def _set_status(self, msg):
        self.status_var.set(msg)

    def _log(self, msg):
        self._append_output(self.log_text, msg)

    # -------------------------------------------------------------------------
    # MANUAL IMDb ID SETTER
    # -------------------------------------------------------------------------
    def open_imdb_dialog(self):
        categories = [
            "movies.json", "dubbed-movies.json", "hindi.json",
            "asian-movies.json", "anime-movies.json", "anime.json",
            "series.json", "tvshows.json", "asian-series.json"
        ]
        category = simpledialog.askstring(
            "Category",
            "Enter category file name:\n" + "\n".join(categories)
        )
        if not category:
            return

        content_id = simpledialog.askstring("Content ID", "Enter content ID (numeric):")
        if not content_id or not content_id.isdigit():
            messagebox.showerror("Error", "Invalid content ID. Must be numeric.")
            return

        imdb_id = simpledialog.askstring("IMDb ID", "Enter IMDb ID (e.g., tt1234567):")
        if not imdb_id or not imdb_id.startswith("tt"):
            messagebox.showerror("Error", "Invalid IMDb ID. Must start with 'tt'.")
            return

        cmd = [PYTHON_EXE, "-u", "set_imdb_id.py",
               "--category", category, "--id", content_id, "--imdb_id", imdb_id]
        proc, text_widget = self._run_subprocess(cmd, f"Set IMDb ID: {content_id}")
        if proc:
            key = f"Set IMDb ID {content_id}"
            self.processes[key]   = proc
            self.output_tabs[key] = text_widget

    # -------------------------------------------------------------------------
    # RATING / RUNTIME BY ID
    # -------------------------------------------------------------------------
    def open_rating_by_id(self):
        categories = [
            "movies.json", "dubbed-movies.json", "hindi.json",
            "asian-movies.json", "anime-movies.json", "anime.json",
            "series.json", "tvshows.json", "asian-series.json"
        ]
        category = simpledialog.askstring(
            "Category",
            "Enter category file name:\n" + "\n".join(categories)
        )
        if not category:
            return

        ids_str = simpledialog.askstring("Content IDs", "Enter one or more content IDs (space-separated):")
        if not ids_str:
            return
        ids = ids_str.split()

        cmd = [PYTHON_EXE, "-u", "update_ratings.py", "--category", category, "--ids"] + ids
        proc, text_widget = self._run_subprocess(cmd, f"Rating for IDs: {', '.join(ids)}")
        if proc:
            key = f"Rating IDs {category} {ids[0]}"
            self.processes[key] = proc
            self.output_tabs[key] = text_widget

    def open_runtime_by_id(self):
        categories = [
            "movies.json", "dubbed-movies.json", "hindi.json",
            "asian-movies.json", "anime-movies.json", "anime.json",
            "series.json", "tvshows.json", "asian-series.json"
        ]
        category = simpledialog.askstring(
            "Category",
            "Enter category file name:\n" + "\n".join(categories)
        )
        if not category:
            return

        ids_str = simpledialog.askstring("Content IDs", "Enter one or more content IDs (space-separated):")
        if not ids_str:
            return
        ids = ids_str.split()

        cmd = [PYTHON_EXE, "-u", "update_runtime.py", "--category", category, "--ids"] + ids
        proc, text_widget = self._run_subprocess(cmd, f"Runtime for IDs: {', '.join(ids)}")
        if proc:
            key = f"Runtime IDs {category} {ids[0]}"
            self.processes[key] = proc
            self.output_tabs[key] = text_widget


    def open_mal_by_id(self):
        ids_str = simpledialog.askstring("Content IDs", "Enter one or more anime IDs (space-separated):")
        if not ids_str:
            return
        ids = ids_str.split()
        category = simpledialog.askstring(
            "Category",
            "Enter category file (anime.json or anime-movies.json):",
        ) or "anime.json"
        cmd = [PYTHON_EXE, "-u", "update_mal.py", "--category", category, "--ids"] + ids
        proc, text_widget = self._run_subprocess(cmd, f"MAL for IDs: {', '.join(ids)}")
        if proc:
            key = f"MAL IDs {ids[0]}"
            self.processes[key]   = proc
            self.output_tabs[key] = text_widget


if __name__ == "__main__":
    if not os.path.exists(PYTHON_EXE):
        import tkinter.messagebox as _mb
        _mb.showerror("Configuration Error",
                      f"Python executable not found:\n{PYTHON_EXE}\n\n"
                      "Edit PYTHON_EXE at the top of this script.")
        sys.exit(1)

    root = tk.Tk()
    app  = ScraperGUI(root)
    root.mainloop()