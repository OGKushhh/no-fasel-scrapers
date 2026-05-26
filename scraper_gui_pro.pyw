#!/usr/bin/env python3
"""
Scraper Control Panel Pro — improved UI/UX.
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
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))  # folder where this .pyw lives
# ===================================

SCRIPT_GROUPS = {
    "FaselHD": {
        "Series (all)":     [PYTHON_EXE, "-u", "FaselSeriesScraper.py"],
        "Series (asian)":   [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "asian-series"],
        "Series (tvshows)": [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "tvshows"],
        "Movies":           [PYTHON_EXE, "-u", "FaselMoviesScraper.py"],
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
        "Ratings (TMDb + OMDb fallback)": [PYTHON_EXE, "-u", "update_ratings.py", "--primary", "tmdb", "--fallback"],
        "Ratings (IMDbAPI + OMDb fallback)": [PYTHON_EXE, "-u", "update_ratings.py", "--primary", "imdbapi", "--fallback"],
        "Ratings (IMDbAPI only)": [PYTHON_EXE, "-u", "update_ratings.py", "--primary", "imdbapi"],
    },
}

BACKFILL_TASKS = {
    "All Tasks":    "all",
    "Movies":       "movies",
    "Descriptions": "descriptions",
}

LIGHT = dict(
    bg="#f0f0f0", fg="#1a1a1a",
    sidebar="#e4e4e4", sidebar_border="#b0b0b0",
    text_bg="#ffffff", text_fg="#1a1a1a",
    btn_bg="#d8d8d8", btn_fg="#1a1a1a", btn_active="#c8c8c8",
    btn_run="#2a7d4f", btn_run_fg="#ffffff", btn_run_active="#235e3b",
    btn_stop="#c0392b", btn_stop_fg="#ffffff",
    btn_stop_idle="#cccccc", btn_stop_idle_fg="#888888",
    btn_green="#27ae60", btn_green_fg="#ffffff",
    section_fg="#777777",
    status_bg="#dde8f0", status_fg="#333333",
    indicator_idle="#bbbbbb", indicator_run="#27ae60",
)
DARK = dict(
    bg="#1e1e1e", fg="#d4d4d4",
    sidebar="#252526", sidebar_border="#111111",
    text_bg="#0d0d0d", text_fg="#d4d4d4",
    btn_bg="#3a3a3a", btn_fg="#d4d4d4", btn_active="#4a4a4a",
    btn_run="#2a7d4f", btn_run_fg="#ffffff", btn_run_active="#235e3b",
    btn_stop="#922b21", btn_stop_fg="#ffffff",
    btn_stop_idle="#333333", btn_stop_idle_fg="#555555",
    btn_green="#1e8449", btn_green_fg="#ffffff",
    section_fg="#888888",
    status_bg="#007acc", status_fg="#ffffff",
    indicator_idle="#444444", indicator_run="#2ecc71",
)


class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Scraper Control Panel")
        root.geometry("1150x720")
        root.minsize(800, 500)

        self.processes      = {}
        self.output_tabs    = {}
        self.custom_procs   = {}
        self.indicators     = {}
        self._stopped_procs = set()
        self.backfill_task_var = tk.StringVar(value="All Tasks")
        self.auto_scroll    = {}
        self.start_times    = {}
        self.script_buttons = {}

        self.dark_mode = False
        self.T = LIGHT

        self._section_labels = []
        self._section_seps   = []

        self._build_ui()
        self._apply_theme()

    # -------------------------------------------------------------------------
    # UI CONSTRUCTION
    # -------------------------------------------------------------------------
    def _build_ui(self):
        # column 0 = sidebar, column 1 = hard border, column 2 = content
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, minsize=240, weight=0)
        self.root.columnconfigure(1, minsize=2,   weight=0)
        self.root.columnconfigure(2, weight=1)

        # Status bar
        self.status_var = tk.StringVar(value="  Ready")
        self.status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            anchor="w", padx=10, pady=4, font=("Consolas", 9),
        )
        self.status_bar.grid(row=1, column=0, columnspan=3, sticky="ew")

        # Sidebar
        self.sidebar = tk.Frame(self.root, width=240)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.rowconfigure(0, weight=1)
        self.sidebar.columnconfigure(0, weight=1)

        self._sidebar_canvas = tk.Canvas(self.sidebar, highlightthickness=0, width=238, bd=0)
        sb_scroll = ttk.Scrollbar(self.sidebar, orient=tk.VERTICAL, command=self._sidebar_canvas.yview)
        self.scroll_frame = tk.Frame(self._sidebar_canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self._sidebar_canvas.configure(scrollregion=self._sidebar_canvas.bbox("all"))
        )
        self._sidebar_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self._sidebar_canvas.configure(yscrollcommand=sb_scroll.set)
        self._sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        sb_scroll.grid(row=0, column=1, sticky="ns")
        self._sidebar_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._sidebar_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        )

        # Divider — 2px hard border between sidebar and content
        self._divider = tk.Frame(self.root, width=2)
        self._divider.grid(row=0, column=1, sticky="nsew")

        # Content area — 6px left padding so it breathes away from the divider
        content = tk.Frame(self.root)
        content.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(content)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        log_frame = tk.Frame(self.notebook)
        self.notebook.add(log_frame, text="  Log  ")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        for tag, col in [("ok","#27ae60"),("warn","#e67e22"),("err","#e74c3c"),("dim","#888888")]:
            self.log_text.tag_configure(tag, foreground=col)
        self.auto_scroll[id(self.log_text)] = tk.BooleanVar(value=True)
        self._log(f"Started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Populate sidebar
        for group, scripts in SCRIPT_GROUPS.items():
            self._section_header(group)
            for name, cmd in scripts.items():
                self._script_row(name, cmd)
        self._section_header("Backfill")
        self._backfill_row()
        self._section_header("")
        self._bottom_controls()

    def _section_header(self, text):
        f = tk.Frame(self.scroll_frame)
        f.pack(fill=tk.X, pady=(10, 0))
        lbl = tk.Label(f, text=text.upper(), font=("Arial", 8, "bold"), anchor="w", padx=10)
        lbl.pack(fill=tk.X)
        self._section_labels.append(lbl)
        if text:
            sep = tk.Frame(f, height=1)
            sep.pack(fill=tk.X, padx=8, pady=(2, 0))
            self._section_seps.append(sep)

    def _script_row(self, name, cmd):
        T = self.T
        outer = tk.Frame(self.scroll_frame)
        outer.pack(fill=tk.X, padx=6, pady=1)
        outer.columnconfigure(0, weight=1)

        top = tk.Frame(outer)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        dot = tk.Label(top, text="●", font=("Arial", 10), width=2,
                       bg=T["sidebar"], fg=T["indicator_idle"])
        dot.grid(row=0, column=0, padx=(2, 0))
        self.indicators[name] = dot

        start_btn = tk.Button(
            top, text=name, anchor="w",
            command=lambda n=name, c=cmd: self.start_script(n, c),
            relief=tk.FLAT, bd=0, padx=6, pady=3, font=("Arial", 9),
            bg=T["sidebar"], fg=T["fg"],
            activebackground=T["btn_active"], activeforeground=T["fg"],
        )
        start_btn.grid(row=0, column=1, sticky="ew")

        stop_btn = tk.Button(
            outer, text="⏹  Stop",
            command=lambda n=name: self.stop_script(n),
            relief=tk.FLAT, bd=0, pady=2, font=("Arial", 8),
            state=tk.DISABLED,
            bg=T["btn_stop_idle"], fg=T["btn_stop_idle_fg"],
            activebackground=T["btn_stop"], activeforeground=T["btn_stop_fg"],
            disabledforeground=T["btn_stop_idle_fg"],
        )
        stop_btn.grid(row=1, column=0, sticky="ew", padx=(20, 0), pady=(0, 2))

        self.script_buttons[name] = (start_btn, stop_btn, outer)

    def _backfill_row(self):
        row = tk.Frame(self.scroll_frame)
        row.pack(fill=tk.X, padx=6, pady=2)
        row.columnconfigure(1, weight=1)

        dot = tk.Label(row, text="●", font=("Arial", 10), width=2)
        dot.grid(row=0, column=0, padx=(2, 0))
        self.indicators["backfill"] = dot

        self.backfill_combo = ttk.Combobox(
            row, textvariable=self.backfill_task_var,
            values=list(BACKFILL_TASKS.keys()),
            state="readonly", font=("Arial", 9),
        )
        self.backfill_combo.grid(row=0, column=1, sticky="ew", padx=(4, 2), pady=4)

        self.backfill_start_btn = tk.Button(
            row, text="▶", width=3, pady=4,
            command=self.start_backfill,
            relief=tk.GROOVE, bd=1, font=("Arial", 9),
        )
        self.backfill_start_btn.grid(row=0, column=2, padx=(2, 2))

        self.backfill_stop_btn = tk.Button(
            row, text="⏹", width=3, pady=4,
            command=self.stop_backfill,
            relief=tk.GROOVE, bd=1,
            state=tk.DISABLED, font=("Arial", 9),
        )
        self.backfill_stop_btn.grid(row=0, column=3, padx=(2, 2))

    def _bottom_controls(self):
        self._custom_btn = tk.Button(
            self.scroll_frame, text="＋  Custom Command",
            command=self.add_custom_command,
            relief=tk.FLAT, bd=0, pady=6, font=("Arial", 9, "bold"),
        )
        self._custom_btn.pack(fill=tk.X, padx=8, pady=(4, 2))

        self._stop_all_btn = tk.Button(
            self.scroll_frame, text="⏹  Stop All",
            command=self.stop_all_scripts,
            relief=tk.FLAT, bd=0, pady=6, font=("Arial", 9, "bold"),
        )
        self._stop_all_btn.pack(fill=tk.X, padx=8, pady=(2, 2))

        self.dark_toggle_btn = tk.Button(
            self.scroll_frame, text="🌙  Dark Mode",
            command=self.toggle_dark_mode,
            relief=tk.FLAT, bd=0, pady=6, font=("Arial", 9),
        )
        self.dark_toggle_btn.pack(fill=tk.X, padx=8, pady=(2, 12))

    # -------------------------------------------------------------------------
    # THEME
    # -------------------------------------------------------------------------
    def _style_stop_btn(self, btn, is_running: bool):
        T = self.T
        if is_running:
            btn.configure(
                bg=T["btn_stop"], fg=T["btn_stop_fg"],
                activebackground=T["btn_stop"], activeforeground=T["btn_stop_fg"],
                disabledforeground=T["btn_stop_fg"],
                relief=tk.GROOVE,
            )
        else:
            btn.configure(
                bg=T["btn_stop_idle"], fg=T["btn_stop_idle_fg"],
                activebackground=T["btn_stop"], activeforeground=T["btn_stop_fg"],
                disabledforeground=T["btn_stop_idle_fg"],
                relief=tk.GROOVE,
            )

    def _apply_theme(self):
        T = self.T
        self.root.configure(bg=T["bg"])

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame",        background=T["bg"])
        style.configure("TNotebook",     background=T["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=T["btn_bg"], foreground=T["fg"],
                        padding=[12, 4], font=("Arial", 9))
        style.map("TNotebook.Tab",
                  background=[("selected", T["text_bg"]), ("active", T["btn_active"])],
                  foreground=[("selected", T["fg"])])
        style.configure("TScrollbar",  background=T["btn_bg"], troughcolor=T["bg"])
        style.configure("TCombobox",   fieldbackground=T["btn_bg"], foreground=T["fg"],
                        background=T["btn_bg"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", T["btn_bg"])],
                  foreground=[("readonly", T["fg"])])

        self.sidebar.configure(bg=T["sidebar"])
        self._sidebar_canvas.configure(bg=T["sidebar"])
        self.scroll_frame.configure(bg=T["sidebar"])
        self._divider.configure(bg=T["sidebar_border"])

        for lbl in self._section_labels:
            lbl.configure(bg=T["sidebar"], fg=T["section_fg"])
            lbl.master.configure(bg=T["sidebar"])
        for sep in self._section_seps:
            sep.configure(bg=T["sidebar_border"])

        for name, (start_btn, stop_btn, outer) in self.script_buttons.items():
            # outer frame + inner top frame
            outer.configure(bg=T["sidebar"])
            for child in outer.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=T["sidebar"])
            start_btn.configure(bg=T["sidebar"], fg=T["fg"],
                                activebackground=T["btn_active"], activeforeground=T["fg"])
            is_running = name in self.processes and self.processes[name].poll() is None
            self._style_stop_btn(stop_btn, is_running)

        for key, dot in self.indicators.items():
            dot.configure(bg=T["sidebar"])
            running = key in self.processes and self.processes[key].poll() is None
            dot.configure(fg=T["indicator_run"] if running else T["indicator_idle"])

        self.backfill_combo.master.configure(bg=T["sidebar"])
        self.backfill_start_btn.configure(bg=T["btn_run"], fg=T["btn_run_fg"],
                                          activebackground=T["btn_run_active"])
        bf_running = "backfill" in self.processes and self.processes["backfill"].poll() is None
        self._style_stop_btn(self.backfill_stop_btn, bf_running)

        self._custom_btn.configure(bg=T["btn_green"], fg=T["btn_green_fg"],
                                   activebackground=T["btn_green"])
        self._stop_all_btn.configure(bg=T["btn_stop"], fg=T["btn_stop_fg"],
                                     activebackground=T["btn_stop"])
        self.dark_toggle_btn.configure(bg=T["sidebar"], fg=T["fg"],
                                       activebackground=T["btn_active"])
        self.status_bar.configure(bg=T["status_bg"], fg=T["status_fg"])
        self.log_text.configure(bg=T["text_bg"], fg=T["text_fg"], insertbackground=T["fg"])
        for widget in self.output_tabs.values():
            widget.configure(bg=T["text_bg"], fg=T["text_fg"], insertbackground=T["fg"])

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.T = DARK if self.dark_mode else LIGHT
        self.dark_toggle_btn.config(text="☀️  Light Mode" if self.dark_mode else "🌙  Dark Mode")
        self._apply_theme()

    # -------------------------------------------------------------------------
    # SCRIPT CONTROL
    # -------------------------------------------------------------------------
    def start_script(self, name, cmd):
        if name in self.processes and self.processes[name].poll() is None:
            messagebox.showwarning("Already running", f'"{name}" is already running.')
            return
        extra = []
        if name == "Update Specific":
            ids = simpledialog.askstring("Series IDs", "Enter IDs (space-separated):")
            if not ids:
                return
            extra = ["--ids"] + ids.split()

        proc, text_widget = self._run_subprocess(cmd + extra, name)
        if proc is None:
            return

        self.processes[name]   = proc
        self.output_tabs[name] = text_widget
        start_btn, stop_btn, _ = self.script_buttons[name]
        start_btn.config(state=tk.DISABLED)
        stop_btn.config(state=tk.NORMAL)
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
        start_btn, stop_btn, _ = self.script_buttons[name]
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)
        self._style_stop_btn(stop_btn, False)
        self._set_indicator(name, False)
        self._set_status(f"⏹  Stopped: {name}")

    def stop_all_scripts(self):
        names = list(self.processes.keys())
        if not names:
            self._set_status("⏹  Nothing running")
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
                start_btn, stop_btn, _ = self.script_buttons[name]
                start_btn.config(state=tk.NORMAL)
                stop_btn.config(state=tk.DISABLED)
                self._style_stop_btn(stop_btn, False)
        self.backfill_start_btn.config(state=tk.NORMAL)
        self.backfill_stop_btn.config(state=tk.DISABLED)
        self._style_stop_btn(self.backfill_stop_btn, False)
        self._set_status(f"⏹  Stopped all ({len(names)} processes)")

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
        self.backfill_start_btn.config(state=tk.DISABLED)
        self.backfill_stop_btn.config(state=tk.NORMAL)
        self._style_stop_btn(self.backfill_stop_btn, True)
        self._set_indicator("backfill", True)
        self._set_status(f"▶  Backfill: {task_label}")

        def _on_done():
            if proc.pid in self._stopped_procs:
                return
            self.root.after(0, lambda: self.backfill_start_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.backfill_stop_btn.config(state=tk.DISABLED))
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
        self.backfill_start_btn.config(state=tk.NORMAL)
        self.backfill_stop_btn.config(state=tk.DISABLED)
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
        if proc.pid not in self._stopped_procs:
            self.root.after(0, lambda: self._remove_custom_tab(tab_frame, tab_name, proc.pid))
        else:
            self._stopped_procs.discard(proc.pid)
            self.root.after(0, lambda: self.custom_procs.pop(proc.pid, None))

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
            f"{'─'*60}\n▶  {tab_name}  [{stamp}]\n{'─'*60}\n")

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
                f"{'─'*60}\n⏹  Finished (exit {code})  [{ts}]  ⏱ {elapsed_str}\n{'─'*60}\n"
            ))
            self.root.after(0, lambda: self._set_status(
                f"{'✔' if code == 0 else '✖'}  Done: {tab_name}  (exit {code})  ⏱ {elapsed_str}"
            ))
            for sname, (sbtn, stpbtn, _) in self.script_buttons.items():
                if self.processes.get(sname) is proc:
                    self.root.after(0, lambda b=sbtn: b.config(state=tk.NORMAL))
                    self.root.after(0, lambda b=stpbtn: b.config(state=tk.DISABLED))
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
            outer, wrap=tk.WORD, font=("Consolas", 9),
            bg=T["text_bg"], fg=T["text_fg"],
            insertbackground=T["fg"], relief=tk.FLAT, bd=0,
        )
        text.grid(row=0, column=0, sticky="nsew")
        for tag, col in [("ok","#27ae60"),("warn","#e67e22"),("err","#e74c3c"),("dim","#888888")]:
            text.tag_configure(tag, foreground=col)

        scroll_var = tk.BooleanVar(value=True)
        self.auto_scroll[id(text)] = scroll_var

        strip = tk.Frame(outer, height=28, bg=T["btn_bg"])
        strip.grid(row=1, column=0, sticky="ew")

        def _clear(t=text):
            t.config(state=tk.NORMAL)
            t.delete("1.0", tk.END)
            t.config(state=tk.DISABLED)

        tk.Button(
            strip, text="Clear", command=_clear,
            relief=tk.FLAT, bd=0, padx=10, pady=3, font=("Arial", 8),
            bg=T["btn_bg"], fg=T["fg"], activebackground=T["btn_active"],
        ).pack(side=tk.RIGHT, padx=4, pady=2)

        tk.Checkbutton(
            strip, text="Auto-scroll", variable=scroll_var,
            relief=tk.FLAT, bd=0, font=("Arial", 8),
            bg=T["btn_bg"], fg=T["fg"], activebackground=T["btn_active"],
            selectcolor=T["btn_bg"],
        ).pack(side=tk.RIGHT, padx=4, pady=2)

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
                strip, text="✕  Close tab", command=_close_tab,
                relief=tk.FLAT, bd=0, padx=10, pady=3, font=("Arial", 8),
                bg=T["btn_bg"], fg=T["fg"], activebackground=T["btn_active"],
            ).pack(side=tk.LEFT, padx=4, pady=2)

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
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True
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
                    self._log(f"⚠️ Warning: {name} (PID {proc.pid}) did not exit after kill\n")
        except Exception as e:
            self._log(f"⚠️ Error stopping {name}: {e}\n")

    def _set_indicator(self, key, running):
        dot = self.indicators.get(key)
        if dot:
            dot.configure(fg=self.T["indicator_run"] if running else self.T["indicator_idle"])

    def _set_status(self, msg):
        self.status_var.set(f"  {msg}")

    def _log(self, msg):
        self._append_output(self.log_text, msg)


# -----------------------------------------------------------------------------
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
