#!/usr/bin/env python3
"""
backfill_movies_only.py
One‑pass backfill for movies: fetches each movie page once and adds:
- Description
- Sources (player token URLs)
- last_scraped timestamp

Run:
    python backfill_movies_only.py
"""

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
from Common import get_website_safe, extract_description, extract_sources, REQUEST_DELAY

# ---------- Signal handling for Ctrl+C ----------
def _exit_gracefully(signum, frame):
    print("\n⚠️ Interrupted. Exiting now...")
    sys.exit(0)

signal.signal(signal.SIGINT, _exit_gracefully)
signal.signal(signal.SIGTERM, _exit_gracefully)

# ---------- Configuration ----------
MOVIE_FILES = [
    "movies.json",
    "dubbed-movies.json",
    "hindi.json",
    "asian-movies.json",
    "anime-movies.json",
]
MAX_WORKERS = 6
SAVE_INTERVAL = 50
BATCH_DELAY = 2

# ---------- Progress helpers ----------
def load_progress(progress_file: str) -> int:
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(progress_file: str, index: int):
    with open(progress_file, "w") as f:
        f.write(str(index))

# ---------- Fetch movie data (description + sources) ----------
def fetch_movie_data(item_id: str) -> tuple:
    """Returns (description, sources_list) for a given numeric movie ID."""
    url = f"https://www.fasel-hd.cam/?p={item_id}"
    resp = get_website_safe(url)
    if not resp or resp.status_code != 200:
        return ("", [])
    soup = BeautifulSoup(resp.text, "html.parser")

    # Get description
    description = extract_description(soup)

    # Get sources – try standard extract_sources first (for .tabs-ul onclick)
    sources = extract_sources(soup)

    # If empty, try to find the player iframe's data-src
    if not sources:
        iframe = soup.find("iframe", {"name": "player_iframe"})
        if iframe:
            src = iframe.get("data-src") or iframe.get("src")
            if src and "video_player" in src:
                sources = [src]

    # If still empty, look for any iframe with video_player in src
    if not sources:
        for iframe in soup.find_all("iframe"):
            src = iframe.get("data-src") or iframe.get("src")
            if src and "video_player" in src:
                sources = [src]
                break

    return (description, sources)

# ---------- Process one movie JSON file ----------
def process_movie_file(json_path: Path):
    print(f"\n🎬 Processing {json_path.name}")

    if not json_path.exists():
        print("  File not found, skipping.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = list(data.items())
    total = len(items)
    progress_file = str(json_path).replace(".json", "_movie_progress.txt")
    start = load_progress(progress_file)
    print(f"  Resuming from index {start} / {total}")

    updated_count = 0
    lock = Lock()
    now_iso = datetime.now(timezone.utc).isoformat()
    completed = set()
    max_contiguous = start

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(start, total, MAX_WORKERS):
            batch = items[i:i+MAX_WORKERS]
            futures = {}
            for idx, (item_id, item_data) in enumerate(batch, start=i):
                # Skip only if all three fields are already present and non‑empty
                if (item_data.get("Description") and
                    item_data.get("last_scraped") and
                    item_data.get("Sources") and len(item_data.get("Sources", [])) > 0):
                    continue
                futures[executor.submit(fetch_movie_data, item_id)] = (idx, item_id, item_data)

            for future in as_completed(futures):
                idx, item_id, item_data = futures[future]
                description, sources = future.result()
                with lock:
                    changed = False
                    if description and not item_data.get("Description"):
                        item_data["Description"] = description
                        updated_count += 1
                        print(f"  [{idx+1}/{total}] ✅ Added description for {item_id}")
                        changed = True
                    elif not description and not item_data.get("Description"):
                        item_data["Description"] = ""
                        changed = True

                    if sources and (not item_data.get("Sources") or len(item_data.get("Sources", [])) == 0):
                        item_data["Sources"] = sources
                        print(f"  [{idx+1}/{total}] ✅ Added {len(sources)} source(s) for {item_id}")
                        changed = True
                    elif not sources and not item_data.get("Sources"):
                        item_data["Sources"] = []
                        changed = True

                    if not item_data.get("last_scraped"):
                        item_data["last_scraped"] = now_iso
                        print(f"  [{idx+1}/{total}] 🕒 Added last_scraped")
                        changed = True

                    if changed:
                        completed.add(idx+1)
                        while max_contiguous+1 in completed:
                            max_contiguous += 1
                        save_progress(progress_file, max_contiguous)

                        if updated_count % SAVE_INTERVAL == 0:
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=4, ensure_ascii=False)
                            print(f"  💾 Saved progress (updated {updated_count} items)")

            time.sleep(BATCH_DELAY)

    # Final save
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    if os.path.exists(progress_file):
        os.remove(progress_file)

    print(f"  ✅ Finished {json_path.name}: updated {updated_count} movies.")

# ---------- Main ----------
def main():
    print("="*60)
    print("🎬 Starting ONE‑PASS movie backfill (description + sources + last_scraped)")
    print("="*60)

    for fname in MOVIE_FILES:
        process_movie_file(Path("./output") / fname)

    print("\n✅ All movie files processed.")

if __name__ == "__main__":
    main()