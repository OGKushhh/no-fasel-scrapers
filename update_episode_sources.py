#!/usr/bin/env python3
"""
update_episode_sources.py

Reads all episode JSON files, fetches each episode page, extracts server token URLs,
and stores them as a "Sources" array inside each episode entry.
Run after the main scrape to enrich episodes with direct player tokens.
"""

import json
import time
from pathlib import Path
from bs4 import BeautifulSoup
from Common import get_website_safe, extract_sources, REQUEST_DELAY

EPISODES_DIR = Path("./output/episodes")
CATEGORIES = ["series", "tvshows", "asian-series", "anime"]

def process_episode_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    changed = False
    seasons = data.get("seasons", {})
    for season_num, season_data in seasons.items():
        episodes = season_data.get("episodes", [])
        # If episodes are stored as strings (old format), convert to dicts
        if episodes and isinstance(episodes[0], str):
            new_episodes = []
            for url in episodes:
                resp = get_website_safe(url)
                if resp:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    sources = extract_sources(soup)
                    new_episodes.append({"url": url, "sources": sources})
                else:
                    new_episodes.append({"url": url, "sources": []})
                time.sleep(REQUEST_DELAY)
            season_data["episodes"] = new_episodes
            changed = True
        else:
            # Already dict format, update episodes missing sources
            for ep in episodes:
                if isinstance(ep, dict) and "sources" not in ep:
                    resp = get_website_safe(ep["url"])
                    if resp:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        ep["sources"] = extract_sources(soup)
                    else:
                        ep["sources"] = []
                    time.sleep(REQUEST_DELAY)
                    changed = True
    if changed:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Updated {file_path}")

def main():
    for cat in CATEGORIES:
        cat_dir = EPISODES_DIR / cat
        if not cat_dir.exists():
            continue
        for file_path in cat_dir.glob("*.json"):
            process_episode_file(file_path)

if __name__ == "__main__":
    main()