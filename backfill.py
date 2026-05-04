#!/usr/bin/env python3
"""
backfill.py – Unified backfill script.

Tasks:
1. descriptions – fills missing 'Description' fields and adds 'last_scraped' if missing
2. episodes    – upgrades episode JSON files to include 'sources' (player token URLs)

Run with:
    python backfill.py --descriptions   (only descriptions + last_scraped)
    python backfill.py --episodes       (only episodes)
    python backfill.py --all            (both, default)

Improvements:
- Contiguous progress tracking: ensures no items are skipped even if threads complete out of order.
- Thread‑safe max index calculation.
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    get_website_safe, extract_description, extract_sources,
    REQUEST_DELAY
)

# ========== CONFIGURATION ==========
# Files for description backfill (main metadata JSONs)
DESCRIPTION_FILES = {
    "movies.json": "movies",
    "dubbed-movies.json": "movies",
    "hindi.json": "movies",
    "asian-movies.json": "movies",
    "anime-movies.json": "movies",
    "anime.json": "anime",
    "series.json": "series",
    "tvshows.json": "tvshows",
    "asian-series.json": "asian-series",
}

# Directories for episode backfill
EPISODE_CATEGORIES = ["series", "tvshows", "asian-series", "anime"]
EPISODES_BASE = Path("./output/episodes")

# Backfill settings
MAX_WORKERS = 6
SAVE_INTERVAL = 50          # save main JSON after this many updates
BATCH_DELAY = 2             # seconds between batches (descriptions)
REQUEST_DELAY_EPISODE = REQUEST_DELAY  # seconds between episode page requests
# ===================================

def load_progress(progress_file: str) -> int:
    """Load the last contiguous completed index (0-indexed) for a description backfill."""
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(progress_file: str, index: int):
    """Save the current contiguous completed index."""
    with open(progress_file, "w") as f:
        f.write(str(index))

def fetch_description(item_id: str, detail_url: str = None) -> str:
    """Fetch description for a single item using its ID or URL."""
    if not detail_url:
        detail_url = f"https://www.fasel-hd.cam/?p={item_id}"
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        return extract_description(soup)
    return ""

def backfill_descriptions_for_file(json_path: Path, category: str):
    """Backfill missing Description fields and add last_scraped if missing.
    Uses contiguous progress tracking to avoid skipping items on resume.
    """
    print(f"\n📖 Backfilling descriptions & last_scraped for {json_path.name}")
    if not json_path.exists():
        print(f"  File not found, skipping.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = list(data.items())
    total = len(items)

    progress_file = str(json_path).replace(".json", "_desc_progress.txt")
    start_contiguous = load_progress(progress_file)
    print(f"  Resuming from contiguous index {start_contiguous} / {total}")

    updated_count = 0
    lock = Lock()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Track completed indices (1‑based) for contiguous max calculation
    completed = set()
    max_contiguous = start_contiguous  # the last fully completed index (0‑based)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # We need to iterate from max_contiguous to end
        for i in range(max_contiguous, total, MAX_WORKERS):
            batch = items[i:i+MAX_WORKERS]
            futures = {}
            for idx, (item_id, item_data) in enumerate(batch, start=i):
                # Skip if already has description and already has last_scraped
                if item_data.get("Description") and item_data.get("last_scraped"):
                    continue
                future = executor.submit(fetch_description, item_id)
                futures[future] = (idx, item_id, item_data)

            for future in as_completed(futures):
                idx, item_id, item_data = futures[future]
                desc = future.result()
                with lock:
                    changed = False
                    if desc and not item_data.get("Description"):
                        item_data["Description"] = desc
                        updated_count += 1
                        print(f"  [{idx+1}/{total}] ✅ Added description for {item_id} ({len(desc)} chars)")
                        changed = True
                    elif not desc and not item_data.get("Description"):
                        item_data["Description"] = ""
                        print(f"  [{idx+1}/{total}] ⚠️ No description for {item_id}")

                    # Add last_scraped if missing
                    if not item_data.get("last_scraped"):
                        item_data["last_scraped"] = now_iso
                        print(f"  [{idx+1}/{total}] 🕒 Added last_scraped for {item_id}")
                        changed = True

                    if changed:
                        # Mark this index as completed (1‑based for easier comparison)
                        completed.add(idx + 1)
                        # Update the contiguous max index
                        while max_contiguous + 1 in completed:
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

    # Clean up progress file
    if os.path.exists(progress_file):
        os.remove(progress_file)

    print(f"  ✅ Finished {json_path.name}: added {updated_count} descriptions and last_scraped timestamps.")

def backfill_all_descriptions():
    """Run description backfill on all main JSON files."""
    for filename, category in DESCRIPTION_FILES.items():
        file_path = Path("./output") / filename
        backfill_descriptions_for_file(file_path, category)

# ----------------------------------------------------------------------
# Episode Sources Backfill (unchanged, already correct)
# ----------------------------------------------------------------------
def upgrade_episode_file(episode_file: Path):
    """
    Convert old episode file (list of URL strings) to new format
    (list of {"url": ..., "sources": [...]}) and fetch missing sources.
    Also ensures file-level last_updated is present.
    """
    print(f"\n🎬 Processing episode file: {episode_file}")
    try:
        with open(episode_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Cannot load: {e}")
        return

    changed = False
    seasons = data.get("seasons", {})
    for season_num, season_data in seasons.items():
        episodes = season_data.get("episodes", [])
        if not episodes:
            continue
        # If episodes are stored as strings (old format)
        if isinstance(episodes[0], str):
            new_episodes = []
            for url in episodes:
                resp = get_website_safe(url)
                if resp:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    sources = extract_sources(soup)
                    new_episodes.append({"url": url, "sources": sources})
                else:
                    new_episodes.append({"url": url, "sources": []})
                time.sleep(REQUEST_DELAY_EPISODE)
            season_data["episodes"] = new_episodes
            changed = True
            print(f"  🔄 Season {season_num}: converted {len(episodes)} episodes")
        else:
            # Already dict format – add sources if missing
            for ep in episodes:
                if isinstance(ep, dict) and "sources" not in ep:
                    url = ep.get("url")
                    if url:
                        resp = get_website_safe(url)
                        if resp:
                            soup = BeautifulSoup(resp.text, "html.parser")
                            ep["sources"] = extract_sources(soup)
                        else:
                            ep["sources"] = []
                        time.sleep(REQUEST_DELAY_EPISODE)
                        changed = True
                        print(f"  🔄 Added sources for {url}")

    if changed:
        # Add or update last_updated timestamp
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(episode_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  💾 Saved {episode_file}")
    else:
        # Ensure last_updated exists even if no other change
        if "last_updated" not in data:
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            with open(episode_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"  🕒 Added last_updated to {episode_file}")
        else:
            print(f"  ✅ No changes needed for {episode_file}")

def backfill_all_episodes():
    """Run episode sources backfill on all episode files."""
    for category in EPISODE_CATEGORIES:
        cat_dir = EPISODES_BASE / category
        if not cat_dir.exists():
            print(f"⚠️ Episodes directory not found: {cat_dir}")
            continue
        episode_files = list(cat_dir.glob("*.json"))
        if not episode_files:
            print(f"⚠️ No episode files in {cat_dir}")
            continue
        print(f"\n📺 Processing {category} episodes ({len(episode_files)} files)")
        for ep_file in episode_files:
            upgrade_episode_file(ep_file)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Unified backfill script")
    parser.add_argument(
        "--task",
        choices=["descriptions", "episodes", "all"],
        default="all",
        help="Which backfill task to run. Default: all"
    )
    args = parser.parse_args()

    if args.task in ("descriptions", "all"):
        print("="*60)
        print("📖 Running description + last_scraped backfill (with contiguous progress)...")
        print("="*60)
        backfill_all_descriptions()

    if args.task in ("episodes", "all"):
        print("\n" + "="*60)
        print("🎬 Running episode sources backfill...")
        print("="*60)
        backfill_all_episodes()

    print("\n✅ All requested backfill tasks completed.")

if __name__ == "__main__":
    main()