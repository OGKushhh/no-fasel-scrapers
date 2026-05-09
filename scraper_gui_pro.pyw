#!/usr/bin/env python3
"""
Advanced Scraper GUI - Single column, dark mode fixed, configurable Python path.
"""

import subprocess
import sys
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog

# ========== CONFIGURATION ==========
# Change this to the full path of your Python executable that has all modules installed.
# Example: r"C:\Users\abdo\AppData\Local\Programs\Python\Python312\python.exe"
PYTHON_EXE = r"C:\Users\abdo\AppData\Local\Programs\Python\Python312\python.exe"
# ===================================

# ---------- YOUR SCRIPTS ----------
SCRIPTS = {
    "Fasel Series (all)": [PYTHON_EXE, "-u", "FaselSeriesScraper.py"],
    "Fasel Series (asian)": [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "asian-series"],
    "Fasel Series (tvshows)": [PYTHON_EXE, "-u", "FaselSeriesScraper.py", "tvshows"],
    "Fasel Movies": [PYTHON_EXE, "-u", "FaselMoviesScraper.py"],
    "Fasel Anime": [PYTHON_EXE, "-u", "FaselAnimeScraper.py"],
    "Akwam Arabic Series": [PYTHON_EXE, "-u", "AkwamArabicSeries.py"],
    "Update Episodes (all)": [PYTHON_EXE, "-u", "update_episodes.py"],
    "Update Specific Episodes": [PYTHON_EXE, "-u", "update_specific_episodes.py"],
    "Check New Episodes": [PYTHON_EXE, "-u", "check_new_episodes.py"],
}

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Scraper Control Panel Pro")
        root.geometry("1000x700")

        self.processes = {}
        self.output_tabs = {}
        self.custom_procs = {}

        self.dark_mode = False
        self.create_widgets()
        self.apply_light_theme()

    def create_widgets(self):
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # LEFT FRAME (scrollable buttons)
        left_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=1)

        canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Buttons grid – single column
        self.script_buttons = {}
        row = 0
        for name, cmd in SCRIPTS.items():
            btn_frame = ttk.Frame(self.scrollable_frame)
            btn_frame.grid(row=row, column=0, padx=5, pady=5, sticky="ew")

            start_btn = tk.Button(btn_frame, text=f"▶ {name}", command=lambda n=name, c=cmd: self.start_script(n, c),
                                  width=45, anchor="w")
            start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

            stop_btn = tk.Button(btn_frame, text="⏹", command=lambda n=name: self.stop_script(n),
                                 bg="red", fg="white", width=3)
            stop_btn.pack(side=tk.RIGHT, padx=(5,0))

            self.script_buttons[name] = (start_btn, stop_btn)
            row += 1

        # Add custom button
        add_btn = tk.Button(self.scrollable_frame, text="+ Add Custom Command", command=self.add_custom_command,
                            bg="green", fg="white", font=("Arial", 10, "bold"))
        add_btn.grid(row=row+1, column=0, pady=10, sticky="ew")

        # Dark mode toggle
        self.dark_toggle_btn = tk.Button(self.scrollable_frame, text="🌙 Dark Mode", command=self.toggle_dark_mode)
        self.dark_toggle_btn.grid(row=row+2, column=0, pady=5, sticky="ew")

        # RIGHT NOTEBOOK
        self.notebook = ttk.Notebook(self.paned)
        self.paned.add(self.notebook, weight=3)

        # Custom commands default tab
        self.custom_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.custom_tab, text="Custom Commands")
        self.custom_output = scrolledtext.ScrolledText(self.custom_tab, wrap=tk.WORD, font=("Consolas", 9))
        self.custom_output.pack(fill=tk.BOTH, expand=True)

    def apply_light_theme(self):
        self._apply_theme(
            bg="#f0f0f0", fg="#000000", text_bg="#ffffff", text_fg="#000000",
            button_bg="SystemButtonFace", button_fg="black", stop_bg="red"
        )

    def apply_dark_theme(self):
        self._apply_theme(
            bg="#2d2d2d", fg="#ffffff", text_bg="#1e1e1e", text_fg="#d4d4d4",
            button_bg="#4a4a4a", button_fg="white", stop_bg="darkred"
        )

    def _apply_theme(self, bg, fg, text_bg, text_fg, button_bg, button_fg, stop_bg):
        self.root.configure(bg=bg)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=bg)
        style.configure("TNotebook", background=bg)
        style.configure("TNotebook.Tab", background=bg, foreground=fg, padding=[10,2])
        style.map("TNotebook.Tab", background=[("selected", "#4a4a4a" if self.dark_mode else "#ffffff")])
        style.configure("TLabel", background=bg, foreground=fg)

        # Fix canvas and scrollable area backgrounds
        canvas = self.scrollable_frame.master.master
        if isinstance(canvas, tk.Canvas):
            canvas.configure(bg=bg, highlightbackground=bg, highlightthickness=0)
        left_frame = canvas.master
        if isinstance(left_frame, ttk.Frame):
            left_frame.configure(style="TFrame")
        self.scrollable_frame.configure(style="TFrame")

        # Buttons
        for start_btn, stop_btn in self.script_buttons.values():
            start_btn.config(bg=button_bg, fg=button_fg, activebackground=button_bg)
            stop_btn.config(bg=stop_bg, fg="white")

        self.dark_toggle_btn.config(bg=button_bg, fg=button_fg, activebackground=button_bg)
        # Keep + button green
        for child in self.scrollable_frame.winfo_children():
            if isinstance(child, tk.Button) and child["text"] == "+ Add Custom Command":
                child.config(bg="green", fg="white", activebackground="darkgreen")

        # Text widgets
        for widget in self.output_tabs.values():
            widget.config(bg=text_bg, fg=text_fg, insertbackground=fg)
        try:
            self.custom_output.config(bg=text_bg, fg=text_fg, insertbackground=fg)
        except:
            pass

    def start_script(self, name, cmd):
        if name in self.processes and self.processes[name].poll() is None:
            messagebox.showwarning("Already running", f"{name} is already running.")
            return

        extra = []
        if name == "Update Specific Episodes":
            ids = simpledialog.askstring("Series IDs", "Enter IDs (space‑separated):")
            if not ids:
                return
            extra = ["--ids"] + ids.split()

        full_cmd = cmd + extra
        proc, text_widget = self._run_subprocess(full_cmd, name)
        if proc is None:
            return

        self.processes[name] = proc
        self.output_tabs[name] = text_widget

        start_btn, stop_btn = self.script_buttons[name]
        start_btn.config(state=tk.DISABLED)
        stop_btn.config(state=tk.NORMAL)

    def stop_script(self, name):
        proc = self.processes.get(name)
        if not proc or proc.poll() is not None:
            return
        self._kill_process(proc, name)
        self.processes.pop(name, None)
        self.output_tabs.pop(name, None)
        start_btn, stop_btn = self.script_buttons[name]
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)

    def add_custom_command(self):
        cmd_str = simpledialog.askstring("Custom Command", "Enter command (e.g., python myscript.py --arg):")
        if not cmd_str:
            return
        import shlex
        cmd_list = shlex.split(cmd_str)
        if cmd_list[0].lower() == "python":
            cmd_list[0] = PYTHON_EXE
        if cmd_list[0] == PYTHON_EXE and "-u" not in cmd_list:
            cmd_list.insert(1, "-u")

        tab_name = f"Custom: {os.path.basename(cmd_list[0])}"
        tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(tab_frame, text=tab_name)
        text_widget = scrolledtext.ScrolledText(tab_frame, wrap=tk.WORD, font=("Consolas", 9))
        text_widget.pack(fill=tk.BOTH, expand=True)

        proc, _ = self._run_subprocess(cmd_list, tab_name, text_widget)
        if proc:
            self.custom_procs[proc.pid] = (proc, text_widget, tab_frame, tab_name)
            text_widget.insert(tk.END, f"\n>>> STARTED: {' '.join(cmd_list)}\n")
            text_widget.see(tk.END)
            threading.Thread(target=self._watch_custom, args=(proc, tab_frame, tab_name), daemon=True).start()

    def _watch_custom(self, proc, tab_frame, tab_name):
        proc.wait()
        self.root.after(0, lambda: self._remove_custom_tab(tab_frame, tab_name, proc.pid))

    def _remove_custom_tab(self, tab_frame, tab_name, pid):
        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == tab_name:
                self.notebook.forget(i)
                break
        self.custom_procs.pop(pid, None)

    def _run_subprocess(self, cmd, tab_name, text_widget=None):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        if text_widget is None:
            tab_frame = ttk.Frame(self.notebook)
            self.notebook.add(tab_frame, text=tab_name)
            text_widget = scrolledtext.ScrolledText(tab_frame, wrap=tk.WORD, font=("Consolas", 9))
            text_widget.pack(fill=tk.BOTH, expand=True)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
                env=env,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not start command:\n{' '.join(cmd)}\n{e}")
            return None, None

        def reader():
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                self.root.after(0, lambda l=line: self._append_output(text_widget, l))
            proc.wait()
            self.root.after(0, lambda: self._append_output(text_widget, f"\n>>> FINISHED (exit code {proc.returncode})\n"))
            for name, (start_btn, stop_btn) in self.script_buttons.items():
                if proc is self.processes.get(name):
                    self.root.after(0, lambda: start_btn.config(state=tk.NORMAL))
                    self.root.after(0, lambda: stop_btn.config(state=tk.DISABLED))
                    self.processes.pop(name, None)
                    self.output_tabs.pop(name, None)
                    break

        threading.Thread(target=reader, daemon=True).start()
        return proc, text_widget

    def _append_output(self, text_widget, line):
        text_widget.insert(tk.END, line)
        text_widget.see(tk.END)

    def _kill_process(self, proc, name=""):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as e:
            self._append_output(self.notebook.select(), f"Error stopping {name}: {e}\n")

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.apply_dark_theme()
            self.dark_toggle_btn.config(text="☀️ Light Mode")
        else:
            self.apply_light_theme()
            self.dark_toggle_btn.config(text="🌙 Dark Mode")

if __name__ == "__main__":
    if not os.path.exists(PYTHON_EXE):
        messagebox.showerror("Configuration Error",
                             f"Python executable not found:\n{PYTHON_EXE}\n\n"
                             "Please edit the PYTHON_EXE variable at the top of this script.")
        sys.exit(1)

    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()