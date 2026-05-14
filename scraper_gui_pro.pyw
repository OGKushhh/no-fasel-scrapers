#!/usr/bin/env python3
"""
Scraper Control Panel Pro — improved UI/UX.
"""

import subprocess
import sys
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import shlex
from datetime import datetime

# ========== CONFIGURATION ==========
PYTHON_EXE = r"C:\Users\abdo\AppData\Local\Programs\Python\Python312\python.exe"
# ===================================

# ── Script groups ────────────────────────────────────────────────────────────
SCRIPT_GROUPS = {
    "FaselHD": {
        "Series (all)":      [PYTHON_EXE, "-u", "FaselSeriesScraper.py"],
        "Series (asian)":    [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "asian-series"],
        "Series (tvshows)":  [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "tvshows"],
        "Movies":            [PYTHON_EXE, "-u", "FaselMoviesScraper.py"],
        "Anime":             [PYTHON_EXE, "-u", "FaselAnimeScraper.py"],
    },
    "Akwam": {
        "Arabic Series":     [PYTHON_EXE, "-u", "AkwamArabicSeries.py"],
    },
    "Episodes": {
        "Update All":        [PYTHON_EXE, "-u", "update_episodes.py"],
        "Update Specific":   [PYTHON_EXE, "-u", "update_specific_episodes.py"],
        "Check New":         [PYTHON_EXE, "-u", "check_new_episodes.py"],
    },
}

BACKFILL_TASKS = {
    "All Tasks":    "all",
    "Movies":       "movies",
    "Descriptions": "descriptions",
    "Episodes":     "episodes",
}

# ── Colour palettes ───────────────────────────────────────────────────────────
LIGHT = dict(
    bg="#f5f5f5", fg="#1a1a1a",
    sidebar="#e8e8e8", sidebar_border="#cccccc",
    text_bg="#ffffff", text_fg="#1a1a1a",
    btn_bg="#e0e0e0", btn_fg="#1a1a1a", btn_active="#d0d0d0",
    btn_run="#2a7d4f", btn_run_fg="#ffffff", btn_run_active="#235e3b",
    btn_stop="#c0392b", btn_stop_fg="#ffffff",
    btn_green="#27ae60", btn_green_fg="#ffffff",
    section_fg="#777777",
    status_bg="#dde8f0", status_fg="#333333",
    indicator_idle="#bbbbbb", indicator_run="#27ae60",
)
DARK = dict(
    bg="#1e1e1e", fg="#d4d4d4",
    sidebar="#252526", sidebar_border="#3c3c3c",
    text_bg="#0d0d0d", text_fg="#d4d4d4",
    btn_bg="#3a3a3a", btn_fg="#d4d4d4", btn_active="#4a4a4a",
    btn_run="#2a7d4f", btn_run_fg="#ffffff", btn_run_active="#235e3b",
    btn_stop="#922b21", btn_stop_fg="#ffffff",
    btn_green="#1e8449", btn_green_fg="#ffffff",
    section_fg="#888888",
    status_bg="#007acc", status_fg="#ffffff",
    indicator_idle="#555555", indicator_run="#2ecc71",
)


class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Scraper Control Panel")
        root.geometry("1100x720")
        root.minsize(800, 500)

        self.processes    = {}
        self.output_tabs  = {}
        self.custom_procs = {}
        self.indicators   = {}
        self.backfill_task_var = tk.StringVar(value="All Tasks")

        self.dark_mode = False
        self.T = LIGHT

        self._section_labels = []
        self._section_seps   = []

        self._build_ui()
        self._apply_theme()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)

        # Status bar
        self.status_var = tk.StringVar(value="  Ready")
        self.status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            anchor="w", padx=10, pady=3, font=("Consolas", 9),
        )
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

        # Sidebar
        self.sidebar = tk.Frame(self.root, width=235)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.rowconfigure(0, weight=1)
        self.sidebar.columnconfigure(0, weight=1)

        self._sidebar_canvas = tk.Canvas(self.sidebar, highlightthickness=0, width=233)
        sb_scroll = ttk.Scrollbar(self.sidebar, orient=tk.VERTICAL,
                                  command=self._sidebar_canvas.yview)
        self.scroll_frame = tk.Frame(self._sidebar_canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self._sidebar_canvas.configure(
                scrollregion=self._sidebar_canvas.bbox("all"))
        )
        self._sidebar_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self._sidebar_canvas.configure(yscrollcommand=sb_scroll.set)
        self._sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        sb_scroll.grid(row=0, column=1, sticky="ns")

        self._sidebar_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._sidebar_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        )

        self.script_buttons = {}

        # Script groups
        for group, scripts in SCRIPT_GROUPS.items():
            self._section_header(group)
            for name, cmd in scripts.items():
                self._script_row(name, cmd)

        # Backfill
        self._section_header("Backfill")
        self._backfill_row()

        # Bottom controls
        self._section_header("")
        self._bottom_controls()

        # Content / notebook
        content = tk.Frame(self.root)
        content.grid(row=0, column=1, sticky="nsew")
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
        self._log(f"Started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    def _section_header(self, text):
        f = tk.Frame(self.scroll_frame)
        f.pack(fill=tk.X, padx=0, pady=(10, 0))
        lbl = tk.Label(f, text=text.upper(), font=("Arial", 8, "bold"), anchor="w", padx=10)
        lbl.pack(fill=tk.X)
        self._section_labels.append(lbl)
        if text:
            sep = tk.Frame(f, height=1)
            sep.pack(fill=tk.X, padx=8, pady=(2, 0))
            self._section_seps.append(sep)

    def _script_row(self, name, cmd):
        row = tk.Frame(self.scroll_frame)
        row.pack(fill=tk.X, padx=8, pady=2)
        row.columnconfigure(1, weight=1)

        dot = tk.Label(row, text="●", font=("Arial", 10), width=2)
        dot.grid(row=0, column=0, padx=(2, 0))
        self.indicators[name] = dot

        start_btn = tk.Button(
            row, text=name, anchor="w",
            command=lambda n=name, c=cmd: self.start_script(n, c),
            relief=tk.FLAT, bd=0, padx=8, pady=5, font=("Arial", 9),
        )
        start_btn.grid(row=0, column=1, sticky="ew")

        stop_btn = tk.Button(
            row, text="⏹", width=3, pady=5,
            command=lambda n=name: self.stop_script(n),
            relief=tk.FLAT, bd=0, state=tk.DISABLED,
        )
        stop_btn.grid(row=0, column=2, padx=(2, 2))

        self.script_buttons[name] = (start_btn, stop_btn, row)

    def _backfill_row(self):
        row = tk.Frame(self.scroll_frame)
        row.pack(fill=tk.X, padx=8, pady=2)
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
            row, text="▶", width=3, pady=5,
            command=self.start_backfill, relief=tk.FLAT, bd=0,
        )
        self.backfill_start_btn.grid(row=0, column=2, padx=(0, 2))

        self.backfill_stop_btn = tk.Button(
            row, text="⏹", width=3, pady=5,
            command=self.stop_backfill, relief=tk.FLAT, bd=0, state=tk.DISABLED,
        )
        self.backfill_stop_btn.grid(row=0, column=3, padx=(0, 2))

    def _bottom_controls(self):
        self._custom_btn = tk.Button(
            self.scroll_frame, text="＋  Custom Command",
            command=self.add_custom_command,
            relief=tk.FLAT, bd=0, pady=6, font=("Arial", 9, "bold"),
        )
        self._custom_btn.pack(fill=tk.X, padx=8, pady=(4, 2))

        self.dark_toggle_btn = tk.Button(
            self.scroll_frame, text="🌙  Dark Mode",
            command=self.toggle_dark_mode,
            relief=tk.FLAT, bd=0, pady=6, font=("Arial", 9),
        )
        self.dark_toggle_btn.pack(fill=tk.X, padx=8, pady=(2, 12))

    # ── Theme ─────────────────────────────────────────────────────────────────
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

        for lbl in self._section_labels:
            lbl.configure(bg=T["sidebar"], fg=T["section_fg"])
            lbl.master.configure(bg=T["sidebar"])
        for sep in self._section_seps:
            sep.configure(bg=T["sidebar_border"])

        for name, (start_btn, stop_btn, row) in self.script_buttons.items():
            row.configure(bg=T["sidebar"])
            start_btn.configure(bg=T["sidebar"], fg=T["fg"],
                                activebackground=T["btn_active"], activeforeground=T["fg"])
            stop_btn.configure(bg=T["btn_stop"], fg=T["btn_stop_fg"],
                               activebackground=T["btn_stop"],
                               disabledforeground=T["sidebar_border"])

        for key, dot in self.indicators.items():
            dot.configure(bg=T["sidebar"])
            running = key in self.processes and self.processes[key].poll() is None
            dot.configure(fg=T["indicator_run"] if running else T["indicator_idle"])

        self.backfill_combo.master.configure(bg=T["sidebar"])
        self.backfill_start_btn.configure(bg=T["btn_run"], fg=T["btn_run_fg"],
                                          activebackground=T["btn_run_active"])
        self.backfill_stop_btn.configure(bg=T["btn_stop"], fg=T["btn_stop_fg"],
                                         activebackground=T["btn_stop"])

        self._custom_btn.configure(bg=T["btn_green"], fg=T["btn_green_fg"],
                                   activebackground=T["btn_green"])
        self.dark_toggle_btn.configure(bg=T["sidebar"], fg=T["fg"],
                                       activebackground=T["btn_active"])

        self.status_bar.configure(bg=T["status_bg"], fg=T["status_fg"])
        self.log_text.configure(bg=T["text_bg"], fg=T["text_fg"],
                                insertbackground=T["fg"])
        for widget in self.output_tabs.values():
            widget.configure(bg=T["text_bg"], fg=T["text_fg"],
                             insertbackground=T["fg"])

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.T = DARK if self.dark_mode else LIGHT
        self.dark_toggle_btn.config(
            text="☀️  Light Mode" if self.dark_mode else "🌙  Dark Mode"
        )
        self._apply_theme()

    # ── Script control ────────────────────────────────────────────────────────
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
        self._set_indicator(name, True)
        self._set_status(f"▶  {name}")

    def stop_script(self, name):
        proc = self.processes.get(name)
        if not proc or proc.poll() is not None:
            return
        self._kill_process(proc, name)
        self.processes.pop(name, None)
        self.output_tabs.pop(name, None)
        start_btn, stop_btn, _ = self.script_buttons[name]
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)
        self._set_indicator(name, False)
        self._set_status(f"⏹  Stopped: {name}")

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
        self._set_indicator("backfill", True)
        self._set_status(f"▶  Backfill: {task_label}")

        def _on_done():
            self.backfill_start_btn.config(state=tk.NORMAL)
            self.backfill_stop_btn.config(state=tk.DISABLED)
            self._set_indicator("backfill", False)
            self.processes.pop("backfill", None)
            self.output_tabs.pop("backfill", None)
        threading.Thread(
            target=lambda: (proc.wait(), self.root.after(0, _on_done)),
            daemon=True
        ).start()

    def stop_backfill(self):
        proc = self.processes.get("backfill")
        if not proc or proc.poll() is not None:
            return
        self._kill_process(proc, "backfill")
        self.processes.pop("backfill", None)
        self.output_tabs.pop("backfill", None)
        self.backfill_start_btn.config(state=tk.NORMAL)
        self.backfill_stop_btn.config(state=tk.DISABLED)
        self._set_indicator("backfill", False)
        self._set_status("⏹  Backfill stopped")

    # ── Custom command ────────────────────────────────────────────────────────
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
        text_widget = self._make_output_widget(tab_frame)

        proc, _ = self._run_subprocess(cmd_list, tab_name, text_widget)
        if proc:
            self.custom_procs[proc.pid] = (proc, text_widget, tab_frame, tab_name)
            threading.Thread(
                target=self._watch_custom, args=(proc, tab_frame, tab_name), daemon=True
            ).start()

    def _watch_custom(self, proc, tab_frame, tab_name):
        proc.wait()
        self.root.after(0, lambda: self._remove_custom_tab(tab_frame, tab_name, proc.pid))

    def _remove_custom_tab(self, tab_frame, tab_name, pid):
        for i in range(self.notebook.index("end")):
            try:
                if self.notebook.tab(i, "text").strip() == tab_name:
                    self.notebook.forget(i)
                    break
            except tk.TclError:
                pass
        self.custom_procs.pop(pid, None)

    # ── Subprocess helpers ────────────────────────────────────────────────────
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
            text_widget = self._make_output_widget(tab_frame)
            self.notebook.select(tab_frame)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=flags, env=env,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not start:\n{' '.join(cmd)}\n\n{e}")
            return None, None

        stamp = datetime.now().strftime("%H:%M:%S")
        self._append_output(text_widget,
            f"{'─'*60}\n▶  {tab_name}  [{stamp}]\n{'─'*60}\n")

        def _reader():
            for line in iter(proc.stdout.readline, ""):
                self.root.after(0, lambda l=line: self._append_output(text_widget, l))
            proc.wait()
            ts = datetime.now().strftime("%H:%M:%S")
            self.root.after(0, lambda: self._append_output(
                text_widget,
                f"{'─'*60}\n⏹  Finished (exit {proc.returncode})  [{ts}]\n{'─'*60}\n"
            ))
            self.root.after(0, lambda: self._set_status(
                f"✔  Done: {tab_name}  (exit {proc.returncode})"
            ))
            for sname, (sbtn, stpbtn, _) in self.script_buttons.items():
                if self.processes.get(sname) is proc:
                    self.root.after(0, lambda b=sbtn:  b.config(state=tk.NORMAL))
                    self.root.after(0, lambda b=stpbtn: b.config(state=tk.DISABLED))
                    self.root.after(0, lambda n=sname: self._set_indicator(n, False))
                    self.processes.pop(sname, None)
                    self.output_tabs.pop(sname, None)
                    break

        threading.Thread(target=_reader, daemon=True).start()
        return proc, text_widget

    def _make_output_widget(self, parent):
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

        strip = tk.Frame(outer, height=28, bg=T["btn_bg"])
        strip.grid(row=1, column=0, sticky="ew")

        tk.Button(
            strip, text="Clear output",
            command=lambda t=text: (t.config(state=tk.NORMAL), t.delete("1.0", tk.END)),
            relief=tk.FLAT, bd=0, padx=10, pady=3, font=("Arial", 8),
            bg=T["btn_bg"], fg=T["fg"], activebackground=T["btn_active"],
        ).pack(side=tk.RIGHT, padx=6, pady=2)

        return text

    def _append_output(self, widget, line):
        was_disabled = str(widget.cget("state")) == "disabled"
        if was_disabled:
            widget.config(state=tk.NORMAL)
        widget.insert(tk.END, line)
        widget.see(tk.END)
        if was_disabled:
            widget.config(state=tk.DISABLED)

    def _kill_process(self, proc, name=""):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as e:
            self._log(f"Error stopping {name}: {e}\n")

    def _set_indicator(self, key, running):
        dot = self.indicators.get(key)
        if dot:
            dot.configure(fg=self.T["indicator_run"] if running else self.T["indicator_idle"])

    def _set_status(self, msg):
        self.status_var.set(f"  {msg}")

    def _log(self, msg):
        self._append_output(self.log_text, msg)


# ─────────────────────────────────────────────────────────────────────────────
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
