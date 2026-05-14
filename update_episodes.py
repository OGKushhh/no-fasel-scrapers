#!/usr/bin/env python3
"""
update_episodes.py – Efficient episode updater for Fasel and Akwam series.
- ALWAYS uses the episode JSON file as the reference for stored count.
- Compares with current site episode count.
- If counts match, fixes the main JSON (if it was wrong) and skips deep fetch.
- Only deep‑fetches when counts differ.
"""

import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    DEBUG, REQUEST_DELAY, get_website_safe,
    extract_seasons_from_page, extract_episodes_from_season_page,
    get_seasons_url_from_detail, extract_status,
    FASEL_BASE_URL, AKWAM_BASE_URL,
    akwam_extract_series_metadata, akwam_extract_episode_sources,
    _parse_akwam_date as parse_akwam_date
)

# ========== CONFIGURATION ==========
FASEL_CATEGORIES = {
    "series": "./output/series.json",
    "tvshows": "./output/tvshows.json",
    "asian-series": "./output/asian-series.json",
    "anime": "./output/anime.json",
}

AKWAM_CATEGORIES = {
    "arabic-series": "./output/arabic-series.json",
}

DAILY_LIMIT = 50
PROGRESS_FILE = "./output/episode_update_progress.txt"
EPISODES_BASE = Path("./output/episodes")
# ===================================

def load_progress() -> set:
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

def get_stored_episode_count_from_file(category: str, series_id: str) -> int:
    """Return the actual number of episodes stored in the episode JSON file."""
    if category in FASEL_CATEGORIES:
        ep_file = EPISODES_BASE / category / f"{series_id}.json"
        if ep_file.exists():
            with open(ep_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            seasons = data.get("seasons", {})
            total = 0
            for season in seasons.values():
                total += len(season.get("episodes", []))
            return total
    elif category in AKWAM_CATEGORIES:
        ep_file = EPISODES_BASE / category / f"{series_id}.json"
        if ep_file.exists():
            with open(ep_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data.get("episodes", []))
    return 0

def update_main_json_episode_count(category: str, series_id: str, new_count: int):
    """Write the correct episode count into the main JSON."""
    json_path = Path(FASEL_CATEGORIES.get(category) or AKWAM_CATEGORIES.get(category))
    if not json_path.exists():
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if series_id not in data:
        return
    if category in FASEL_CATEGORIES:
        data[series_id]["Number Of Episodes"] = new_count
    else:
        data[series_id]["episode_count"] = new_count
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def update_status_in_main_json(category: str, series_id: str, new_status: str):
    json_path = Path(FASEL_CATEGORIES.get(category) or AKWAM_CATEGORIES.get(category))
    if not json_path.exists():
        return
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if series_id in data and data[series_id].get("Status") != new_status:
        data[series_id]["Status"] = new_status
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  📝 Updated status to '{new_status}' for {category}/{series_id}")

# ================= Fasel Helpers =================
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

def get_fasel_season_episodes(season_url: str) -> list:
    """Return list of episode dicts with URL only – no source fetching."""
    resp = get_website_safe(season_url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    episode_urls = extract_episodes_from_season_page(soup)
    return [{"url": url} for url in episode_urls]

def update_fasel_series(category: str, series_id: str, detail_url: str) -> bool:
    # Get current total from site
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

    total_current_episodes = 0
    for season in seasons_list:
        season_url = season["page_url"]
        season_resp = get_website_safe(season_url)
        if season_resp:
            season_soup = BeautifulSoup(season_resp.text, "html.parser")
            ep_urls = extract_episodes_from_season_page(season_soup)
            total_current_episodes += len(ep_urls)
        time.sleep(REQUEST_DELAY / 2)

    # Get stored count from episode file (NOT from main JSON)
    stored_count = get_stored_episode_count_from_file(category, series_id)

    # If stored count matches current, just update main JSON and skip deep fetch
    if stored_count == total_current_episodes and stored_count > 0:
        print(f"  ⏭️ Episode count unchanged ({total_current_episodes}), syncing main JSON")
        update_main_json_episode_count(category, series_id, total_current_episodes)
        return False

    print(f"  🔄 Episode count changed: {stored_count} → {total_current_episodes}, updating...")
    update_main_json_episode_count(category, series_id, total_current_episodes)

    # Deep update (new episodes added)
    existing = load_fasel_episodes(category, series_id)
    existing_seasons = existing.get("seasons", {})
    changed = False

    for season in seasons_list:
        season_num = season["number"]
        season_url = season["page_url"]
        poster = season.get("poster", "")

        current_episodes = get_fasel_season_episodes(season_url)
        stored_season = existing_seasons.get(str(season_num), {})
        stored_episodes = stored_season.get("episodes", [])

        stored_urls = [ep["url"] if isinstance(ep, dict) else ep for ep in stored_episodes]
        new_episodes = [ep for ep in current_episodes if ep["url"] not in stored_urls]

        if new_episodes:
            print(f"  🆕 Season {season_num}: +{len(new_episodes)} new episodes")
            if stored_episodes and isinstance(stored_episodes[0], str):
                stored_episodes = [{"url": u} for u in stored_episodes]
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
        update_status_in_main_json(category, series_id, "مستمر")
        return True
    return False

def update_fasel_status(category: str, series_id: str, detail_url: str):
    json_path = Path(FASEL_CATEGORIES[category])
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
        print(f"  🏁 Status changed: {current_status} → {new_status}")
        update_status_in_main_json(category, series_id, new_status)

# ================= Akwam Helpers =================
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

def update_akwam_series(category: str, series_id: str, detail_url: str) -> bool:
    resp = get_website_safe(detail_url)
    if not resp:
        return False
    soup = BeautifulSoup(resp.text, "html.parser")
    metadata = akwam_extract_series_metadata(soup, AKWAM_BASE_URL)
    total_current_episodes = metadata.get("episode_count", 0)

    stored_count = get_stored_episode_count_from_file(category, series_id)

    if stored_count == total_current_episodes and stored_count > 0:
        print(f"  ⏭️ Episode count unchanged ({total_current_episodes}), syncing main JSON")
        update_main_json_episode_count(category, series_id, total_current_episodes)
        return False

    print(f"  🔄 Episode count changed: {stored_count} → {total_current_episodes}, updating...")
    update_main_json_episode_count(category, series_id, total_current_episodes)

    existing = load_akwam_episodes(category, series_id)
    existing_episodes = existing.get("episodes", [])
    existing_urls = {ep["url"] for ep in existing_episodes}
    new_episodes = []

    for ep in metadata.get("episodes", []):
        if ep["url"] in existing_urls:
            continue
        ep_resp = get_website_safe(ep["url"])
        if ep_resp:
            ep_soup = BeautifulSoup(ep_resp.text, "html.parser")
            sources = akwam_extract_episode_sources(ep_soup)
        else:
            sources = []
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

# ================= Main Dispatcher =================
def process_category(category: str, json_path: str, processed_set: set, daily_limit: int, is_fasel: bool):
    print(f"\n📺 Processing {category}...")
    if not Path(json_path).exists():
        print(f"  ⚠️ {json_path} not found, skipping")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    processed_count = 0
    for series_id, info in data.items():
        if (category, series_id) in processed_set:
            continue
        if daily_limit > 0 and processed_count >= daily_limit:
            print(f"  ⏸️ Daily limit of {daily_limit} reached, stopping.")
            break

        detail_url = info.get("SeasonsUrl") or info.get("url")
        if not detail_url:
            if is_fasel:
                detail_url = f"{FASEL_BASE_URL}{category}/{series_id}"
            else:
                detail_url = f"{AKWAM_BASE_URL}/series/{series_id}"
        if not detail_url:
            save_progress(category, series_id)
            processed_count += 1
            continue

        title = info.get("Title", "Unknown")
        print(f"\n🔍 {category}/{series_id}: {title}")

        if is_fasel:
            update_fasel_series(category, series_id, detail_url)
            update_fasel_status(category, series_id, detail_url)
        else:
            update_akwam_series(category, series_id, detail_url)

        time.sleep(REQUEST_DELAY / 2)
        save_progress(category, series_id)
        processed_count += 1

def main():
    # Optional: clear progress to re‑scan everything once
    # if Path(PROGRESS_FILE).exists():
    #     Path(PROGRESS_FILE).unlink()

    processed = load_progress()

    for category, json_path in FASEL_CATEGORIES.items():
        process_category(category, json_path, processed, DAILY_LIMIT, is_fasel=True)
        if DAILY_LIMIT > 0 and len(processed) >= DAILY_LIMIT:
            break

    for category, json_path in AKWAM_CATEGORIES.items():
        process_category(category, json_path, processed, DAILY_LIMIT - len(processed), is_fasel=False)
        if DAILY_LIMIT > 0 and len(processed) >= DAILY_LIMIT:
            break

    print("\n✅ Episode update completed.")

if __name__ == "__main__":
    main()