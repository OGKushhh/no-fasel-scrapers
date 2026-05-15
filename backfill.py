#!/usr/bin/env python3
"""
backfill.py – Unified backfill script.

Tasks:
1. descriptions – fills missing 'Description' fields and adds 'last_scraped' (for all categories except movies, because movies have their own combined task)
2. movies      – ONE‑PASS backfill for movies: fetches each movie page once and extracts Description and last_scraped.
3. all         – runs descriptions (non‑movie) and movies.

Run with:
    python backfill.py --descriptions   (only descriptions for series/anime etc.)
    python backfill.py --movies         (only movies: description + last_scraped in one pass)
    python backfill.py --all            (all tasks, default)
"""

import argparse
import json
import os
import time
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    get_website_safe, extract_description,
    REQUEST_DELAY
)

# ========== SIGNAL HANDLER – force exit on Ctrl+C ==========
def _exit_gracefully(signum, frame):
    print("\n⚠️ Interrupted. Exiting now...")
    sys.exit(0)

signal.signal(signal.SIGINT, _exit_gracefully)
signal.signal(signal.SIGTERM, _exit_gracefully)
# ===========================================================

# ========== CONFIGURATION ==========
# Files for description backfill (series, anime, etc. – NOT movies)
DESCRIPTION_FILES = {
    "anime.json": "anime",
    "series.json": "series",
    "tvshows.json": "tvshows",
    "asian-series.json": "asian-series",
}

# Only movie categories for the combined movie task
MOVIE_FILES = {
    "movies.json": "movies",
    "dubbed-movies.json": "movies",
    "hindi.json": "movies",
    "asian-movies.json": "movies",
    "anime-movies.json": "movies",
}

# Backfill settings
MAX_WORKERS = 6
SAVE_INTERVAL = 50          # save main JSON after this many updates
BATCH_DELAY = 2             # seconds between batches
# ===================================

def load_progress(progress_file: str) -> set:
    """Load the set of already-completed item IDs from a JSON progress file."""
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
        except Exception:
            pass
    return set()

def save_progress(progress_file: str, done_ids: set):
    """Atomically write completed item IDs to the progress file."""
    tmp = progress_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(list(done_ids), f)
    os.replace(tmp, progress_file)

def fetch_description(item_id: str, detail_url: str = None) -> str:
    if not detail_url:
        detail_url = f"https://www.fasel-hd.cam/?p={item_id}"
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        return extract_description(soup)
    return ""

def fetch_movie_data(item_id: str, detail_url: str) -> str:
    """Fetch a movie page and return its description."""
    if not detail_url:
        return ""
    resp = get_website_safe(detail_url)
    if not resp or resp.status_code != 200:
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    return extract_description(soup)

# ----------------------------------------------------------------------
# Description backfill (for non‑movie categories)
# ----------------------------------------------------------------------
def backfill_descriptions_for_file(json_path: Path, category: str):
    print(f"\n📖 Backfilling descriptions & last_scraped for {json_path.name}")
    if not json_path.exists():
        print(f"  File not found, skipping.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = list(data.items())
    total = len(items)

    progress_file = str(json_path).replace(".json", "_desc_progress.json")
    done_ids = load_progress(progress_file)

    # Also consider items already complete in the JSON itself as done
    already_done = {
        item_id for item_id, item_data in items
        if item_data.get("Description") is not None and item_data.get("last_scraped")
    }
    done_ids |= already_done

    remaining = [(item_id, item_data) for item_id, item_data in items if item_id not in done_ids]
    print(f"  {len(already_done)} already complete, {len(remaining)} remaining / {total} total")

    if not remaining:
        print(f"  ✅ Nothing to do for {json_path.name}")
        if os.path.exists(progress_file):
            os.remove(progress_file)
        return

    updated_count = 0
    lock = Lock()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _save_json():
        tmp = str(json_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, str(json_path))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(0, len(remaining), MAX_WORKERS):
            batch = remaining[i:i + MAX_WORKERS]
            futures = {
                executor.submit(fetch_description, item_id): (item_id, item_data)
                for item_id, item_data in batch
            }

            for future in as_completed(futures):
                item_id, item_data = futures[future]
                desc = future.result()
                with lock:
                    changed = False

                    if desc and not item_data.get("Description"):
                        item_data["Description"] = desc
                        updated_count += 1
                        print(f"  [{i+1}/{len(remaining)}] ✅ {item_id} ({len(desc)} chars)")
                        changed = True
                    elif not desc and item_data.get("Description") is None:
                        item_data["Description"] = ""
                        print(f"  [{i+1}/{len(remaining)}] ⚠️  No description for {item_id}")
                        changed = True

                    if not item_data.get("last_scraped"):
                        item_data["last_scraped"] = now_iso
                        changed = True

                    # Always mark done so we don't retry this ID on next run
                    done_ids.add(item_id)
                    save_progress(progress_file, done_ids)

                    if changed and updated_count > 0 and updated_count % SAVE_INTERVAL == 0:
                        _save_json()
                        print(f"  💾 Saved JSON (updated {updated_count} items so far)")

            time.sleep(BATCH_DELAY)

    _save_json()

    if os.path.exists(progress_file):
        os.remove(progress_file)

    print(f"  ✅ Finished {json_path.name}: updated {updated_count} items.")

def backfill_all_descriptions():
    for filename, category in DESCRIPTION_FILES.items():
        file_path = Path("./output") / filename
        backfill_descriptions_for_file(file_path, category)

# ----------------------------------------------------------------------
# COMBINED MOVIE BACKFILL (description + last_scraped in one pass)
# ----------------------------------------------------------------------
def backfill_movies_combined(json_path: Path, category: str):
    print(f"\n🎬 Combined movie backfill (desc + last_scraped) for {json_path.name}")
    if not json_path.exists():
        print(f"  File not found, skipping.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = list(data.items())
    total = len(items)

    progress_file = str(json_path).replace(".json", "_movie_progress.json")
    done_ids = load_progress(progress_file)

    already_done = {
        item_id for item_id, item_data in items
        if item_data.get("Description") is not None and item_data.get("last_scraped")
    }
    done_ids |= already_done

    remaining = [(item_id, item_data) for item_id, item_data in items if item_id not in done_ids]
    print(f"  {len(already_done)} already complete, {len(remaining)} remaining / {total} total")

    if not remaining:
        print(f"  ✅ Nothing to do for {json_path.name}")
        if os.path.exists(progress_file):
            os.remove(progress_file)
        return

    updated_count = 0
    lock = Lock()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _save_json():
        tmp = str(json_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, str(json_path))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(0, len(remaining), MAX_WORKERS):
            batch = remaining[i:i + MAX_WORKERS]
            futures = {
                executor.submit(fetch_movie_data, item_id, f"https://www.fasel-hd.cam/?p={item_id}"): (item_id, item_data)
                for item_id, item_data in batch
            }

            for future in as_completed(futures):
                item_id, item_data = futures[future]
                description = future.result()
                with lock:
                    changed = False

                    if description and not item_data.get("Description"):
                        item_data["Description"] = description
                        updated_count += 1
                        print(f"  [{i+1}/{len(remaining)}] ✅ {item_id} ({len(description)} chars)")
                        changed = True
                    elif not description and item_data.get("Description") is None:
                        item_data["Description"] = ""
                        print(f"  [{i+1}/{len(remaining)}] ⚠️  No description for {item_id}")
                        changed = True

                    if not item_data.get("last_scraped"):
                        item_data["last_scraped"] = now_iso
                        changed = True

                    done_ids.add(item_id)
                    save_progress(progress_file, done_ids)

                    if changed and updated_count > 0 and updated_count % SAVE_INTERVAL == 0:
                        _save_json()
                        print(f"  💾 Saved JSON (updated {updated_count} items so far)")

            time.sleep(BATCH_DELAY)

    _save_json()

    if os.path.exists(progress_file):
        os.remove(progress_file)

    print(f"  ✅ Finished {json_path.name}: updated {updated_count} movies (description, last_scraped).")

def backfill_all_movies():
    print("\n🎬 Starting combined movie backfill (description + last_scraped)...")
    for filename, category in MOVIE_FILES.items():
        file_path = Path("./output") / filename
        backfill_movies_combined(file_path, category)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Unified backfill script")
    parser.add_argument(
        "--task",
        choices=["descriptions", "movies", "all"],
        default="all",
        help="Which backfill task to run. Default: all"
    )
    args = parser.parse_args()

    if args.task in ("descriptions", "all"):
        print("="*60)
        print("📖 Running description + last_scraped backfill (non‑movie categories)...")
        print("="*60)
        backfill_all_descriptions()

    if args.task in ("movies", "all"):
        print("\n" + "="*60)
        print("🎬 Running combined movie backfill (description + last_scraped)...")
        print("="*60)
        backfill_all_movies()

    print("\n✅ All requested backfill tasks completed.")

if __name__ == "__main__":
    main()