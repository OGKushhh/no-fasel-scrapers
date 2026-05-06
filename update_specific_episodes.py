#!/usr/bin/env python3
"""
update_specific_episodes.py
Manually trigger episode update for one or more series/anime IDs.
Auto‑detects category by searching all JSON files.

Usage:
    python update_specific_episodes.py --ids 14506 14507
    python update_specific_episodes.py --file ids.txt
"""

import argparse
import json
import time
import sys
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, get_website_safe,
    extract_seasons_from_page, extract_episodes_from_season_page,
    get_seasons_url_from_detail, extract_status, extract_sources
)

# ---------- Configuration ----------
CATEGORIES = {
    "series": "./output/series.json",
    "tvshows": "./output/tvshows.json",
    "asian-series": "./output/asian-series.json",
    "anime": "./output/anime.json",
}

EPISODES_BASE = Path("./output/episodes")

# ---------- Helper functions (same as before) ----------
def load_episodes(category: str, series_id: str) -> dict:
    path = EPISODES_BASE / category / f"{series_id}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"content_id": series_id, "category": category, "seasons": {}}

def save_episodes(category: str, series_id: str, data: dict):
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    path = EPISODES_BASE / category / f"{series_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved episodes for {category}/{series_id}")

def update_main_json_status(category: str, series_id: str, new_status: str):
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

def get_season_episodes_with_sources(season_url: str) -> list:
    resp = get_website_safe(season_url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    episode_urls = extract_episodes_from_season_page(soup)
    episodes = []
    for url in episode_urls:
        ep_resp = get_website_safe(url)
        if ep_resp:
            ep_soup = BeautifulSoup(ep_resp.text, "html.parser")
            sources = extract_sources(ep_soup)
        else:
            sources = []
        episodes.append({"url": url, "sources": sources})
        time.sleep(REQUEST_DELAY / 2)
    return episodes

def check_and_update_episodes_for_id(category: str, series_id: str, detail_url: str) -> bool:
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

    existing = load_episodes(category, series_id)
    existing_seasons = existing.get("seasons", {})
    changed = False

    for season in seasons_list:
        season_num = season["number"]
        season_url = season["page_url"]
        poster = season.get("poster", "")

        current_episodes = get_season_episodes_with_sources(season_url)
        stored_season = existing_seasons.get(str(season_num), {})
        stored_episodes = stored_season.get("episodes", [])

        stored_urls = [ep["url"] if isinstance(ep, dict) else ep for ep in stored_episodes]
        new_episodes = [ep for ep in current_episodes if ep["url"] not in stored_urls]

        if new_episodes:
            print(f"  🆕 {category}/{series_id} Season {season_num}: +{len(new_episodes)} new episodes")
            if stored_episodes and isinstance(stored_episodes[0], str):
                stored_episodes = [{"url": u, "sources": []} for u in stored_episodes]
            all_episodes = stored_episodes + new_episodes
            existing_seasons[str(season_num)] = {"poster": poster, "episodes": all_episodes}
            changed = True
        elif not stored_episodes and current_episodes:
            print(f"  📦 {category}/{series_id} Season {season_num}: storing {len(current_episodes)} episodes")
            existing_seasons[str(season_num)] = {"poster": poster, "episodes": current_episodes}
            changed = True

    if changed:
        existing["seasons"] = existing_seasons
        save_episodes(category, series_id, existing)
        update_main_json_status(category, series_id, "مستمر")
        return True
    return False

def update_status_for_ongoing_series_id(category: str, series_id: str, detail_url: str):
    json_path = Path(CATEGORIES[category])
    if not json_path.exists():
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    current_status = data.get(series_id, {}).get("Status")
    if current_status != "مستمر":
        return

    resp = get_website_safe(detail_url)
    if not resp:
        return
    soup = BeautifulSoup(resp.text, "html.parser")
    new_status = extract_status(soup)
    if new_status and new_status != current_status:
        print(f"  🏁 {category}/{series_id} status changed: {current_status} → {new_status}")
        update_main_json_status(category, series_id, new_status)

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Update episodes for specific IDs (auto‑detect category)")
    parser.add_argument("--ids", nargs="+", help="Space‑separated list of IDs (e.g., 14506 14507)")
    parser.add_argument("--file", help="Text file with one ID per line")
    args = parser.parse_args()

    ids = []
    if args.ids:
        ids = args.ids
    if args.file:
        with open(args.file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ids.append(line)

    if not ids:
        print("❌ No IDs provided. Use --ids or --file")
        sys.exit(1)

    # Load all category JSONs into a map: id -> (category, detail_url, title)
    id_map = {}
    for cat, json_path in CATEGORIES.items():
        path = Path(json_path)
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item_id, info in data.items():
            if item_id not in id_map:
                id_map[item_id] = []
            detail_url = info.get("SeasonsUrl")
            if not detail_url:
                detail_url = f"{FASEL_BASE_URL}{cat}/{item_id}"
            id_map[item_id].append({
                "category": cat,
                "detail_url": detail_url,
                "title": info.get("Title", "Unknown")
            })

    for series_id in ids:
        if series_id not in id_map:
            print(f"⚠️ ID {series_id} not found in any category JSON.")
            continue

        entries = id_map[series_id]
        if len(entries) > 1:
            print(f"⚠️ ID {series_id} found in multiple categories: {[e['category'] for e in entries]}")
            print("   Updating all of them.")

        for entry in entries:
            cat = entry["category"]
            detail_url = entry["detail_url"]
            title = entry["title"]
            print(f"\n🔍 {cat}/{series_id}: {title}")
            check_and_update_episodes_for_id(cat, series_id, detail_url)
            update_status_for_ongoing_series_id(cat, series_id, detail_url)
            time.sleep(REQUEST_DELAY / 2)

    print("\n✅ Done.")

if __name__ == "__main__":
    main()