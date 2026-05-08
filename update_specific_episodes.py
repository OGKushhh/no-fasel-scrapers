#!/usr/bin/env python3
"""
update_specific_episodes.py
Manually trigger episode update for one or more series/anime IDs.
Auto‑detects category by searching all JSON files (Fasel + Akwam).
Uses episode file as source of truth (not main JSON) to avoid unnecessary deep fetches.
Optimized:
- Parallel fetching of season pages (ThreadPoolExecutor)
- Parallel fetching of new episode sources
- In‑memory caching of episode data
- Configurable max_workers

Supports --dry-run to simulate.

Usage:
    python update_specific_episodes.py --ids 14506 14507
    python update_specific_episodes.py --file ids.txt
    python update_specific_episodes.py --ids arabic-series:4799 --dry-run
    python update_specific_episodes.py --ids 14506 --workers 8
"""

import argparse
import json
import time
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from Common import (
    DEBUG, REQUEST_DELAY, get_website_safe,
    extract_seasons_from_page, extract_episodes_from_season_page,
    get_seasons_url_from_detail, extract_status, extract_sources,
    FASEL_BASE_URL, AKWAM_BASE_URL,
    akwam_extract_series_metadata, akwam_extract_episode_sources,
    _parse_akwam_date as parse_akwam_date
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
DEFAULT_WORKERS = 5

# ---------- In‑memory caching for episode files ----------
_episode_cache = {}  # key: (source_type, category, series_id) -> data dict

def get_cached_episodes(source_type: str, category: str, series_id: str) -> dict:
    key = (source_type, category, series_id)
    if key not in _episode_cache:
        if source_type == "fasel":
            _episode_cache[key] = load_fasel_episodes(category, series_id)
        else:
            _episode_cache[key] = load_akwam_episodes(category, series_id)
    return _episode_cache[key]

def set_cached_episodes(source_type: str, category: str, series_id: str, data: dict):
    key = (source_type, category, series_id)
    _episode_cache[key] = data

def clear_cache():
    _episode_cache.clear()

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

def get_stored_count_fasel(category: str, series_id: str) -> int:
    ep_file = EPISODES_BASE / category / f"{series_id}.json"
    if not ep_file.exists():
        return 0
    with open(ep_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    seasons = data.get("seasons", {})
    total = 0
    for season in seasons.values():
        episodes = season.get("episodes", [])
        total += len(episodes)
    return total

def fetch_season_page(season):
    """Fetch a single season page and return (season_num, ep_urls, poster)."""
    season_num = season["number"]
    season_url = season["page_url"]
    poster = season.get("poster", "")
    season_resp = get_website_safe(season_url)
    if not season_resp:
        return season_num, [], poster
    season_soup = BeautifulSoup(season_resp.text, "html.parser")
    ep_urls = extract_episodes_from_season_page(season_soup)
    time.sleep(REQUEST_DELAY / 2)  # be gentle
    return season_num, ep_urls, poster

def fetch_episode_sources(url):
    """Fetch a single episode page and return its sources."""
    ep_resp = get_website_safe(url)
    if ep_resp:
        ep_soup = BeautifulSoup(ep_resp.text, "html.parser")
        return extract_sources(ep_soup)
    return []

# ---------- Optimized Fasel update with parallelism ----------
def update_fasel_series_by_id(category: str, series_id: str, detail_url: str, dry_run=False, workers=DEFAULT_WORKERS) -> bool:
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

    # ---- Parallel fetch of all season pages ----
    season_data = {}
    total_current_episodes = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_season_page, season) for season in seasons_list]
        for future in as_completed(futures):
            season_num, ep_urls, poster = future.result()
            season_data[season_num] = {'urls': ep_urls, 'poster': poster}
            total_current_episodes += len(ep_urls)

    # Get stored count from cached episode file
    stored_episode_count = get_stored_count_fasel(category, series_id)

    if stored_episode_count == total_current_episodes and stored_episode_count > 0:
        print(f"  ⏭️ Episode count unchanged ({total_current_episodes}), syncing main JSON")
        # Update main JSON count
        json_path = Path(FASEL_CATEGORIES[category])
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if series_id in data:
                data[series_id]["Number Of Episodes"] = total_current_episodes
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        return False

    print(f"  🔄 Episode count changed: {stored_episode_count} → {total_current_episodes}, updating...")
    if dry_run:
        print("  [DRY RUN] Would update episodes and main JSON")
        return True

    # Update main JSON count
    json_path = Path(FASEL_CATEGORIES[category])
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if series_id in data:
            data[series_id]["Number Of Episodes"] = total_current_episodes
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    # Get existing episodes from cache
    existing = get_cached_episodes("fasel", category, series_id)
    existing_seasons = existing.get("seasons", {})
    changed = False

    for season_num, data in season_data.items():
        current_urls = data['urls']
        poster = data['poster']
        stored_season = existing_seasons.get(str(season_num), {})
        stored_episodes = stored_season.get("episodes", [])
        stored_urls = [ep["url"] if isinstance(ep, dict) else ep for ep in stored_episodes]

        new_urls = [url for url in current_urls if url not in stored_urls]
        if not new_urls and stored_urls:
            continue

        # Normalise stored episodes
        if stored_episodes and isinstance(stored_episodes[0], str):
            stored_episodes = [{"url": u, "sources": []} for u in stored_episodes]

        if new_urls:
            print(f"  🆕 Season {season_num}: +{len(new_urls)} new episodes")
            # Parallel fetch sources for new episodes
            with ThreadPoolExecutor(max_workers=workers) as ex:
                source_futures = {ex.submit(fetch_episode_sources, url): url for url in new_urls}
                new_episodes = []
                for future in as_completed(source_futures):
                    url = source_futures[future]
                    sources = future.result()
                    new_episodes.append({"url": url, "sources": sources})
            # Preserve order (optional)
            new_episodes.sort(key=lambda x: new_urls.index(x["url"]))
            all_episodes = stored_episodes + new_episodes
        else:
            # Entirely new season
            print(f"  📦 Season {season_num}: storing {len(current_urls)} episodes")
            # Parallel fetch all episodes in this new season
            with ThreadPoolExecutor(max_workers=workers) as ex:
                source_futures = {ex.submit(fetch_episode_sources, url): url for url in current_urls}
                all_episodes = []
                for future in as_completed(source_futures):
                    url = source_futures[future]
                    sources = future.result()
                    all_episodes.append({"url": url, "sources": sources})
            all_episodes.sort(key=lambda x: current_urls.index(x["url"]))

        existing_seasons[str(season_num)] = {"poster": poster, "episodes": all_episodes}
        changed = True

    if changed:
        existing["seasons"] = existing_seasons
        save_fasel_episodes(category, series_id, existing)
        set_cached_episodes("fasel", category, series_id, existing)
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

def get_stored_count_akwam(category: str, series_id: str) -> int:
    ep_file = EPISODES_BASE / category / f"{series_id}.json"
    if not ep_file.exists():
        return 0
    with open(ep_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        return len(data.get("episodes", []))

def update_akwam_series_by_id(category: str, series_id: str, detail_url: str, dry_run=False, workers=DEFAULT_WORKERS) -> bool:
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

    stored_episode_count = get_stored_count_akwam(category, series_id)

    if stored_episode_count == total_episodes and stored_episode_count > 0:
        print(f"  ⏭️ Episode count unchanged ({total_episodes}), syncing main JSON")
        json_path = Path(AKWAM_CATEGORIES[category])
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if series_id in data:
                data[series_id]["episode_count"] = total_episodes
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        return False

    print(f"  🔄 Episode count changed: {stored_episode_count} → {total_episodes}, updating...")
    if dry_run:
        print("  [DRY RUN] Would update episodes and main JSON")
        return True

    # Update main JSON count
    json_path = Path(AKWAM_CATEGORIES[category])
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if series_id in data:
            data[series_id]["episode_count"] = total_episodes
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    existing = get_cached_episodes("akwam", category, series_id)
    existing_episodes = existing.get("episodes", [])
    existing_urls = {ep["url"] for ep in existing_episodes}
    new_episodes = []

    # Prepare list of episode pages to fetch
    episodes_to_fetch = [ep for ep in metadata.get("episodes", []) if ep["url"] not in existing_urls]
    if episodes_to_fetch:
        print(f"  🆕 Found {len(episodes_to_fetch)} new episodes")
        # Parallel fetch episode sources
        def fetch_episode_source(ep):
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
            return {
                "number": ep_num,
                "title": ep["title"],
                "url": ep["url"],
                "sources": sources
            }

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(fetch_episode_source, ep) for ep in episodes_to_fetch]
            for future in as_completed(futures):
                new_episodes.append(future.result())
        # Restore original order (by episode number or position)
        new_episodes.sort(key=lambda x: (x["number"] is None, x["number"] if x["number"] else 999999))

        existing["episodes"] = existing_episodes + new_episodes
        save_akwam_episodes(category, series_id, existing)
        set_cached_episodes("akwam", category, series_id, existing)
        return True
    return False

# ---------- Main dispatcher ----------
def main():
    parser = argparse.ArgumentParser(description="Update episodes for specific IDs (auto‑detect category)")
    parser.add_argument("--ids", nargs="+", help="Space‑separated list of IDs. For Akwam, prefix with category: e.g., arabic-series:4799")
    parser.add_argument("--file", help="Text file with one ID per line (same format)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without making any changes")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"Number of parallel workers (default {DEFAULT_WORKERS})")
    args = parser.parse_args()

    if args.dry_run:
        print("🔍 DRY RUN MODE – no files will be modified\n")

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

    # Clear cache at start of run
    clear_cache()

    # Build a map from ID to list of possible categories and details
    id_map = {}

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

    for raw_id in ids:
        if ":" in raw_id:
            parts = raw_id.split(":", 1)
            category_prefix = parts[0]
            series_id = parts[1]
            matched = False
            for entry in id_map.get(series_id, []):
                if entry["category"] == category_prefix:
                    print(f"\n🔍 {entry['category']}/{series_id}: {entry['title']}")
                    if entry["source_type"] == "fasel":
                        update_fasel_series_by_id(entry["category"], series_id, entry["detail_url"], args.dry_run, args.workers)
                    else:
                        update_akwam_series_by_id(entry["category"], series_id, entry["detail_url"], args.dry_run, args.workers)
                    matched = True
                    break
            if not matched:
                print(f"⚠️ ID {series_id} not found in category '{category_prefix}'.")
            continue

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
                update_fasel_series_by_id(entry["category"], raw_id, entry["detail_url"], args.dry_run, args.workers)
            else:
                update_akwam_series_by_id(entry["category"], raw_id, entry["detail_url"], args.dry_run, args.workers)
            time.sleep(REQUEST_DELAY / 2)

    print("\n✅ Done.")

if __name__ == "__main__":
    main()