#!/usr/bin/env python3
"""
ScrapeAll.py – Full pipeline: scrape FaselHD → clean (with genre translation) → sort → sync & push.
Run daily (cron / Task Scheduler) to keep data fresh.

Steps:
  1. FaselMoviesScraper.py   – all movie categories
  2. FaselAnimeScraper.py    – anime series
  3. FaselSeriesScraper.py   – series, tvshows, asian-series
  4. clean_metadata.py --translate-genres  – clean + fill Arabic genre translations
  5. sort_output.py          – convert dicts to sorted arrays for the app
  6. sync_to_abdobest.py     – copy changed files to AbdoBest/data + git push
"""

import os
import subprocess
from time import perf_counter
from datetime import datetime

start_time = perf_counter()
os.makedirs("./output", exist_ok=True)

def run_script(script_name, args=None, description=""):
    """Run a Python script with optional args. Return True if success."""
    cmd = ["python", script_name]
    if args:
        cmd.extend(args)
    print(f"\n▶️ Running: {' '.join(cmd)} ... {description}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"❌ {script_name} failed (exit code {result.returncode})")
        with open("./output/failed_scripts.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - {script_name} failed\n")
        return False
    print(f"✅ {script_name} finished successfully")
    return True

print("=" * 60)
print("🚀 Pipeline: Scrape FaselHD → Clean (translate) → Sort → Sync")
print("=" * 60)

failures = []

# ── Phase 1: Scrape all FaselHD content ──────────────────────────────
print("\n[Phase 1] Scraping fresh metadata from FaselHD")
for script in [
    "FaselMoviesScraper.py",
    "FaselAnimeScraper.py",
    "FaselSeriesScraper.py",
]:
    if not run_script(script):
        failures.append(script)

# ── Phase 2: Clean metadata AND translate missing Arabic genres ──────
print("\n[Phase 2] Cleaning metadata + translating Arabic genres")
if os.path.exists("clean_metadata.py"):
    if not run_script("clean_metadata.py", ["--translate-genres"], description="(cleaning + genre translation)"):
        failures.append("clean_metadata.py")
else:
    print("⚠️ clean_metadata.py not found – skipping")

# ── Phase 3: Sort output (dict → array, newest first) ────────────────
print("\n[Phase 3] Sorting output JSONs")
if os.path.exists("sort_output.py"):
    if not run_script("sort_output.py", description="(all categories)"):
        failures.append("sort_output.py")
else:
    print("⚠️ sort_output.py not found – skipping")

# ── Phase 4: Sync to AbdoBest and Git push ────────────────────────────
print("\n[Phase 4] Syncing changed files to AbdoBest/data and pushing to git")
if os.path.exists("sync_to_abdobest.py"):
    if not run_script("sync_to_abdobest.py", description="(copy + git add/commit/push)"):
        failures.append("sync_to_abdobest.py")
else:
    print("⚠️ sync_to_abdobest.py not found – skipping")

# ── Finalise ────────────────────────────────────────────────────────────
end_time = perf_counter()

with open("./output/last-scraped.txt", "w") as fp:
    fp.write(datetime.now().strftime("%Y-%m-%d"))

print("\n" + "=" * 60)
if failures:
    print(f"⚠️ Some scripts failed: {', '.join(failures)}")
    print(f"Check ./output/failed_scripts.log for details.")
else:
    print("✅ All scripts completed successfully.")
print(f"Total time: {round((end_time - start_time) / 60)} minutes")