#!/usr/bin/env python3
"""
Simple GUI that runs scrapers and displays their output.
- Each scraper runs in a separate process.
- Output appears in a single log area (coloured by script, but simple).
- Start/Stop buttons for each scraper.
- No external dependencies (only tkinter).
"""

import subprocess
import sys
import os
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox

# ----------------------------------------------------------------------
# List your scrapers here (name, command list)
# ----------------------------------------------------------------------
SCRIPTS = {
    "Fasel Series (all)": ["python", "-u", "FaselSeriesScraper.py"],
    "Fasel Series (asian-only)": ["python", "-u", "FaselSeriesScraper.py", "asian-series"],
    "Fasel Series (tvshows)": ["python", "-u", "FaselSeriesScraper.py", "tvshows"],
    "Fasel Movies": ["python", "-u", "FaselMoviesScraper.py"],
    "Fasel Anime": ["python", "-u", "FaselAnimeScraper.py"],
    "Akwam Arabic Series": ["python", "-u", "AkwamArabicSeries.py"],
    "Update Episodes (all)": ["python", "-u", "update_episodes.py"],
    "Update Specific Episodes": ["python", "-u", "update_specific_episodes.py"],
    "Check New Episodes": ["python", "-u", "check_new_episodes.py"],
}

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        root.title("Scraper Control")
        root.geometry("900x600")

        # Notebook for separate tabs (each scraper has its own tab)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.processes = {}   # name -> subprocess.Popen
        self.tab_frames = {}  # name -> frame (for storing buttons/log)

        for name, cmd in SCRIPTS.items():
            self.add_scraper_tab(name, cmd)

    def add_scraper_tab(self, name, cmd):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=name)
        self.tab_frames[name] = frame

        # Control buttons
        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        start_btn = tk.Button(btn_frame, text="Start", command=lambda: self.start_scraper(name, cmd))
        start_btn.pack(side=tk.LEFT, padx=5)

        stop_btn = tk.Button(btn_frame, text="Stop", command=lambda: self.stop_scraper(name), bg="red", fg="white")
        stop_btn.pack(side=tk.LEFT, padx=5)

        # Store buttons to enable/disable later
        frame.start_btn = start_btn
        frame.stop_btn = stop_btn

        # Output area
        log_area = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=("Consolas", 9), height=30)
        log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        frame.log_area = log_area

        # Special handling for Update Specific Episodes
        frame.special = (name == "Update Specific Episodes")

    def start_scraper(self, name, cmd):
        if name in self.processes and self.processes[name].poll() is None:
            messagebox.showwarning("Already Running", f"{name} is already running.")
            return

        extra_args = []
        if name == "Update Specific Episodes":
            ids = tk.simpledialog.askstring(
                "Series IDs",
                "Enter series IDs (space‑separated):\nExample: 14506 14507\nOr prefixed: arabic-series:4799"
            )
            if not ids:
                return
            extra_args = ["--ids"] + ids.split()

        full_cmd = cmd + extra_args

        # Set environment for UTF-8 and unbuffered output
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        try:
            proc = subprocess.Popen(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=creationflags,
                env=env,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not start {name}:\n{e}")
            return

        self.processes[name] = proc
        frame = self.tab_frames[name]
        frame.start_btn.config(state=tk.DISABLED)
        frame.stop_btn.config(state=tk.NORMAL)
        frame.log_area.insert(tk.END, f"\n>>> STARTED: {name}\n")
        frame.log_area.see(tk.END)

        # Start reading output in a separate thread (but update GUI via after)
        def read_output():
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                # Schedule GUI update
                self.root.after(0, lambda l=line: self.append_output(name, l))
            proc.wait()
            self.root.after(0, lambda: self.on_finish(name, proc.returncode))

        import threading
        threading.Thread(target=read_output, daemon=True).start()

    def append_output(self, name, line):
        frame = self.tab_frames.get(name)
        if frame:
            frame.log_area.insert(tk.END, line)
            frame.log_area.see(tk.END)

    def on_finish(self, name, retcode):
        frame = self.tab_frames.get(name)
        if frame:
            frame.log_area.insert(tk.END, f"\n>>> FINISHED (exit code {retcode})\n")
            frame.log_area.see(tk.END)
            frame.start_btn.config(state=tk.NORMAL)
            frame.stop_btn.config(state=tk.DISABLED)
        if name in self.processes:
            del self.processes[name]

    def stop_scraper(self, name):
        proc = self.processes.get(name)
        if not proc or proc.poll() is not None:
            return
        # Kill the process (and children on Windows)
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
            self.append_output(name, f"Error stopping: {e}\n")
        else:
            self.append_output(name, "\n>>> STOPPED by user\n")
        # Clean up
        if name in self.processes:
            del self.processes[name]
        frame = self.tab_frames.get(name)
        if frame:
            frame.start_btn.config(state=tk.NORMAL)
            frame.stop_btn.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperGUI(root)
    root.mainloop()