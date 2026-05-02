#!/usr/bin/env python3
"""
update_episodes.py

Unified script that:
- Checks all known series (from JSON files) for new episodes.
- If new episodes are found, updates the episodes JSON (adds a `last_updated` timestamp)
  and ensures status is 'مستمر'.
- Then, for series marked 'مستمر', re-fetches the detail page and updates status
  to 'مكتمل' if Fasel indicates completion (and no new episodes were found today).

Run this daily/weekly via cron-job.org.
"""

import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, get_website_safe,
    extract_seasons_from_page, extract_episodes_from_season_page,
    get_seasons_url_from_detail, extract_status
)

# ========== CONFIGURATION ==========
# Categories that have episodes (and status)
CATEGORIES = {
    "series": "./output/series.json",
    "tvshows": "./output/tvshows.json",
    "asian-series": "./output/asian-series.json",
    "anime": "./output/anime.json",
}

# Progress file (to resume if interrupted)
PROGRESS_FILE = "./output/episode_update_progress.txt"
# ===================================

def load_progress() -> set:
    """Return set of (category, series_id) already processed in this run."""
    processed = set()
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        processed.add((parts[0], parts[1]))
    return processed

def save_progress(category: str, series_id: str):
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{category}|{series_id}\n")

def load_episodes(category: str, series_id: str) -> dict:
    """Load existing episodes data."""
    path = Path(f"./output/episodes/{category}/{series_id}.json")
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"content_id": series_id, "category": category, "seasons": {}}

def save_episodes(category: str, series_id: str, data: dict):
    """
    Save episodes JSON with a `last_updated` timestamp (UTC ISO format).
    """
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    path = Path(f"./output/episodes/{category}/{series_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved episodes for {category}/{series_id} (last_updated: {data['last_updated']})")

def update_main_json_status(category: str, series_id: str, new_status: str):
    """Update the Status field in the main JSON file."""
    json_path = Path(CATEGORIES[category])
    if not json_path.exists():
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if series_id in data and data[series_id].get("Status") != new_status:
        data[series_id]["Status"] = new_status
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  📝 Updated status to '{new_status}' for {category}/{series_id}")

def get_season_episodes(season_url: str) -> list:
    """Fetch a season page and return list of episode URLs."""
    resp = get_website_safe(season_url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return extract_episodes_from_season_page(soup)

def check_and_update_episodes(category: str, series_id: str, detail_url: str) -> bool:
    """
    Check for new episodes. Returns True if new episodes were found (and saved).
    Also ensures status is set to 'مستمر' if new episodes are added.
    """
    # Get the seasons hub URL
    seasons_hub_url = get_seasons_url_from_detail(detail_url)
    if not seasons_hub_url:
        return False

    resp = get_website_safe(seasons_hub_url)
    if not resp:
        return False
    hub_soup = BeautifulSoup(resp.text, "html.parser")
    seasons_list = extract_seasons_from_page(hub_soup, FASEL_BASE_URL)
    if not seasons_list:
        return False

    # Load existing episodes
    existing = load_episodes(category, series_id)
    existing_seasons = existing.get("seasons", {})
    changed = False

    for season in seasons_list:
        season_num = season["number"]
        season_url = season["page_url"]
        poster = season.get("poster", "")

        current_episodes = get_season_episodes(season_url)
        stored_season = existing_seasons.get(str(season_num), {})
        stored_episodes = stored_season.get("episodes", [])

        # Find new episodes (URLs not in stored)
        new_episodes = [ep for ep in current_episodes if ep not in stored_episodes]

        if new_episodes:
            print(f"  🆕 {category}/{series_id} Season {season_num}: +{len(new_episodes)} new episodes")
            all_episodes = stored_episodes + new_episodes
            existing_seasons[str(season_num)] = {
                "poster": poster,
                "episodes": all_episodes
            }
            changed = True
        elif not stored_episodes and current_episodes:
            # First time seeing this season – store all
            print(f"  📦 {category}/{series_id} Season {season_num}: storing {len(current_episodes)} episodes")
            existing_seasons[str(season_num)] = {
                "poster": poster,
                "episodes": current_episodes
            }
            changed = True

    if changed:
        existing["seasons"] = existing_seasons
        save_episodes(category, series_id, existing)   # ← this adds last_updated
        # New episodes found → ensure status is 'مستمر' (ongoing)
        update_main_json_status(category, series_id, "مستمر")
        return True
    return False

def update_status_for_ongoing_series(category: str, series_id: str, detail_url: str):
    """
    After episode check, update status based on Fasel's detail page.
    Only called if the series is still marked 'مستمر' in the main JSON.
    """
    json_path = Path(CATEGORIES[category])
    if not json_path.exists():
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    current_status = data.get(series_id, {}).get("Status")
    if current_status != "مستمر":
        return  # Already completed or unknown, skip

    resp = get_website_safe(detail_url)
    if not resp:
        return
    soup = BeautifulSoup(resp.text, "html.parser")
    new_status = extract_status(soup)
    if new_status and new_status != current_status:
        print(f"  🏁 {category}/{series_id} status changed: {current_status} → {new_status}")
        update_main_json_status(category, series_id, new_status)

def process_category(category: str, json_path: str, processed_set: set):
    print(f"\n📺 Processing {category}...")
    if not Path(json_path).exists():
        print(f"  ⚠️ {json_path} not found, skipping")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for series_id, info in data.items():
        if (category, series_id) in processed_set:
            continue

        detail_url = info.get("SeasonsUrl")
        if not detail_url:
            # Try to construct from ID (anime sometimes stores it differently)
            detail_url = f"{FASEL_BASE_URL}{category}/{series_id}"
        if not detail_url:
            save_progress(category, series_id)
            continue

        print(f"\n🔍 {category}/{series_id}: {info.get('Title', 'Unknown')}")

        # Step 1: Check for new episodes
        check_and_update_episodes(category, series_id, detail_url)

        # Step 2: Update status (if still ongoing)
        update_status_for_ongoing_series(category, series_id, detail_url)

        # Polite delay between series
        time.sleep(REQUEST_DELAY / 2)

        save_progress(category, series_id)

def main():
    # Clear progress file at the start of each full run (optional)
    # Comment out if you want resumable across multiple runs.
    if Path(PROGRESS_FILE).exists():
        Path(PROGRESS_FILE).unlink()

    processed = load_progress()  # will be empty if we just deleted it

    for category, json_path in CATEGORIES.items():
        process_category(category, json_path, processed)

    print("\n✅ Episode and status update completed.")

if __name__ == "__main__":
    main()