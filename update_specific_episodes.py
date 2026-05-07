#!/usr/bin/env python3
"""
update_specific_episodes.py
Manually trigger episode update for one or more series/anime IDs.
Auto‑detects category by searching all JSON files (Fasel + Akwam).
Uses episode count comparison to avoid unnecessary deep fetching.
If no episode numbers exist, scans page and compares URLs.

Usage:
    python update_specific_episodes.py --ids 14506 14507
    python update_specific_episodes.py --file ids.txt
    python update_specific_episodes.py --ids arabic-series:4799
"""

import argparse
import json
import time
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    DEBUG, REQUEST_DELAY, get_website_safe,
    extract_seasons_from_page, extract_episodes_from_season_page,
    get_seasons_url_from_detail, extract_status, extract_sources,
    FASEL_BASE_URL, AKWAM_BASE_URL,
    akwam_extract_series_metadata, akwam_extract_episode_sources,
    parse_akwam_date
)

# ---------- Configuration ----------
FASEL_CATEGORIES = {
    "series": "./output/series.json",
    "tvshows": "./output/tvshows.json",
    "asian-series": "./output/asian-series.json",
    "anime": "./output/anime.json",
}

AKWAM_CATEGORIES = {
    "arabic-series": "./output/arabic-series.json",
}

EPISODES_BASE = Path("./output/episodes")

# ---------- Helper functions (Fasel) ----------
def load_fasel_episodes(category: str, series_id: str) -> dict:
    path = EPISODES_BASE / category / f"{series_id}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"content_id": series_id, "category": category, "seasons": {}}

def save_fasel_episodes(category: str, series_id: str, data: dict):
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    path = EPISODES_BASE / category / f"{series_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved Fasel episodes for {category}/{series_id}")

def update_fasel_status(category: str, series_id: str, detail_url: str):
    json_path = Path(FASEL_CATEGORIES[category])
    if not json_path.exists():
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if series_id not in data:
        return
    current_status = data[series_id].get("Status")
    if current_status != "مستمر":
        return
    resp = get_website_safe(detail_url)
    if not resp:
        return
    soup = BeautifulSoup(resp.text, "html.parser")
    new_status = extract_status(soup)
    if new_status and new_status != current_status:
        print(f"  🏁 Status changed: {current_status} → {new_status}")
        data[series_id]["Status"] = new_status
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  📝 Updated status in {category}/{series_id}")

def get_fasel_season_episodes_with_sources(season_url: str) -> list:
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

def update_fasel_series_by_id(category: str, series_id: str, detail_url: str) -> bool:
    # Get seasons hub URL
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

    # Calculate current total episodes
    total_current_episodes = 0
    for season in seasons_list:
        season_url = season["page_url"]
        season_resp = get_website_safe(season_url)
        if season_resp:
            season_soup = BeautifulSoup(season_resp.text, "html.parser")
            ep_urls = extract_episodes_from_season_page(season_soup)
            total_current_episodes += len(ep_urls)
        time.sleep(REQUEST_DELAY / 2)

    # Try to get stored episode count from main JSON
    json_path = Path(FASEL_CATEGORIES[category])
    stored_episode_count = 0
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            stored_episode_count = data.get(series_id, {}).get("Number Of Episodes", 0)

    if stored_episode_count == total_current_episodes and stored_episode_count > 0:
        print(f"  ⏭️ Episode count unchanged ({total_current_episodes}), skipping deep update")
        return False

    print(f"  🔄 Episode count changed: {stored_episode_count} → {total_current_episodes}, updating...")
    # Update main JSON with new count
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if series_id in data:
            data[series_id]["Number Of Episodes"] = total_current_episodes
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    # Deep fetch with sources
    existing = load_fasel_episodes(category, series_id)
    existing_seasons = existing.get("seasons", {})
    changed = False

    for season in seasons_list:
        season_num = season["number"]
        season_url = season["page_url"]
        poster = season.get("poster", "")

        current_episodes = get_fasel_season_episodes_with_sources(season_url)
        stored_season = existing_seasons.get(str(season_num), {})
        stored_episodes = stored_season.get("episodes", [])

        # Normalise stored episodes to dict format
        stored_urls = [ep["url"] if isinstance(ep, dict) else ep for ep in stored_episodes]
        new_episodes = [ep for ep in current_episodes if ep["url"] not in stored_urls]

        if new_episodes:
            print(f"  🆕 Season {season_num}: +{len(new_episodes)} new episodes")
            if stored_episodes and isinstance(stored_episodes[0], str):
                stored_episodes = [{"url": u, "sources": []} for u in stored_episodes]
            all_episodes = stored_episodes + new_episodes
            existing_seasons[str(season_num)] = {"poster": poster, "episodes": all_episodes}
            changed = True
        elif not stored_episodes and current_episodes:
            print(f"  📦 Season {season_num}: storing {len(current_episodes)} episodes")
            existing_seasons[str(season_num)] = {"poster": poster, "episodes": current_episodes}
            changed = True

    if changed:
        existing["seasons"] = existing_seasons
        save_fasel_episodes(category, series_id, existing)
        update_fasel_status(category, series_id, detail_url)
        return True
    return False

# ---------- Helper functions (Akwam) ----------
def load_akwam_episodes(category: str, series_id: str) -> dict:
    path = EPISODES_BASE / category / f"{series_id}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"content_id": series_id, "category": category, "episodes": []}

def save_akwam_episodes(category: str, series_id: str, data: dict):
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    path = EPISODES_BASE / category / f"{series_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved Akwam episodes for {category}/{series_id}")

def update_akwam_series_by_id(category: str, series_id: str, detail_url: str) -> bool:
    # Get current metadata (including episode list and count)
    resp = get_website_safe(detail_url)
    if not resp:
        return False
    soup = BeautifulSoup(resp.text, "html.parser")
    metadata = akwam_extract_series_metadata(soup, AKWAM_BASE_URL)
    total_episodes = len(metadata.get("episodes", []))
    if total_episodes == 0:
        print("  ℹ️ No episodes found on this series page.")
        return False

    # Get stored episode count from main JSON
    json_path = Path(AKWAM_CATEGORIES[category])
    stored_episode_count = 0
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            stored_episode_count = data.get(series_id, {}).get("episode_count", 0)

    if stored_episode_count == total_episodes and stored_episode_count > 0:
        print(f"  ⏭️ Episode count unchanged ({total_episodes}), skipping deep update")
        return False

    print(f"  🔄 Episode count changed: {stored_episode_count} → {total_episodes}, updating...")
    # Update main JSON with new count
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if series_id in data:
            data[series_id]["episode_count"] = total_episodes
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    # Deep fetch episodes with sources
    existing = load_akwam_episodes(category, series_id)
    existing_episodes = existing.get("episodes", [])
    existing_urls = {ep["url"] for ep in existing_episodes}
    new_episodes = []

    for ep in metadata.get("episodes", []):
        if ep["url"] in existing_urls:
            continue
        # Fetch episode page for sources
        ep_resp = get_website_safe(ep["url"])
        if ep_resp:
            ep_soup = BeautifulSoup(ep_resp.text, "html.parser")
            sources = akwam_extract_episode_sources(ep_soup)
        else:
            sources = []
        # Try to extract episode number from title (if available)
        ep_num = None
        num_match = re.search(r'الحلقة\s+(\d+)', ep["title"])
        if num_match:
            ep_num = int(num_match.group(1))
        new_episodes.append({
            "number": ep_num,
            "title": ep["title"],
            "url": ep["url"],
            "sources": sources
        })
        time.sleep(REQUEST_DELAY / 2)

    if new_episodes:
        print(f"  🆕 Found {len(new_episodes)} new episodes")
        existing["episodes"] = existing_episodes + new_episodes
        save_akwam_episodes(category, series_id, existing)
        return True
    return False

# ---------- Main dispatcher ----------
def main():
    parser = argparse.ArgumentParser(description="Update episodes for specific IDs (auto‑detect category)")
    parser.add_argument("--ids", nargs="+", help="Space‑separated list of IDs (e.g., 14506 14507). For Akwam, prefix with category: e.g., arabic-series:4799")
    parser.add_argument("--file", help="Text file with one ID per line (same format)")
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

    # Build a map from ID to list of possible categories and details
    id_map = {}  # id -> list of dicts {category, detail_url, title, source_type}

    # First, load Fasel categories
    for cat, json_path in FASEL_CATEGORIES.items():
        path = Path(json_path)
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item_id, info in data.items():
            detail_url = info.get("SeasonsUrl")
            if not detail_url:
                detail_url = f"{FASEL_BASE_URL}{cat}/{item_id}"
            id_map.setdefault(item_id, []).append({
                "category": cat,
                "detail_url": detail_url,
                "title": info.get("Title", "Unknown"),
                "source_type": "fasel"
            })

    # Then, load Akwam categories
    for cat, json_path in AKWAM_CATEGORIES.items():
        path = Path(json_path)
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item_id, info in data.items():
            detail_url = info.get("url")
            if not detail_url:
                detail_url = f"{AKWAM_BASE_URL}/series/{item_id}"
            id_map.setdefault(item_id, []).append({
                "category": cat,
                "detail_url": detail_url,
                "title": info.get("title", "Unknown"),
                "source_type": "akwam"
            })

    # Process each requested ID
    for raw_id in ids:
        # Allow explicit category prefix: e.g., "arabic-series:4799"
        if ":" in raw_id:
            parts = raw_id.split(":", 1)
            category_prefix = parts[0]
            series_id = parts[1]
            # Look for that specific category
            matched = False
            for entry in id_map.get(series_id, []):
                if entry["category"] == category_prefix:
                    print(f"\n🔍 {entry['category']}/{series_id}: {entry['title']}")
                    if entry["source_type"] == "fasel":
                        update_fasel_series_by_id(entry["category"], series_id, entry["detail_url"])
                    else:
                        update_akwam_series_by_id(entry["category"], series_id, entry["detail_url"])
                    matched = True
                    break
            if not matched:
                print(f"⚠️ ID {series_id} not found in category '{category_prefix}'.")
            continue

        # Otherwise, treat as numeric ID and try all matches
        if raw_id not in id_map:
            print(f"⚠️ ID {raw_id} not found in any category JSON.")
            continue

        entries = id_map[raw_id]
        if len(entries) > 1:
            print(f"⚠️ ID {raw_id} found in multiple categories: {[e['category'] for e in entries]}")
            print("   Updating all of them.")

        for entry in entries:
            print(f"\n🔍 {entry['category']}/{raw_id}: {entry['title']}")
            if entry["source_type"] == "fasel":
                update_fasel_series_by_id(entry["category"], raw_id, entry["detail_url"])
            else:
                update_akwam_series_by_id(entry["category"], raw_id, entry["detail_url"])
            time.sleep(REQUEST_DELAY / 2)

    print("\n✅ Done.")

if __name__ == "__main__":
    main()