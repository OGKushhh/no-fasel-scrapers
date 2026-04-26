#!/usr/bin/env python3
"""
Test episode extraction for a given content ID in a specific category.
Usage:
    python test_episodes_extraction.py series 4307
    python test_episodes_extraction.py tvshows 131775
    python test_episodes_extraction.py asian-series 63030
"""

import json
import os
import sys
import time
import re
from Common import get_website_safe, REQUEST_DELAY, FASEL_BASE_URL
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Extraction functions (copied from FaselSeriesScraper.py)
# ----------------------------------------------------------------------
def extract_seasons_from_page(soup: BeautifulSoup, base_url: str) -> list:
    seasons = []
    season_list_div = soup.select_one('#seasonList')
    if not season_list_div:
        return seasons
    for season_div in season_list_div.select('.seasonDiv'):
        title_elem = season_div.select_one('.title')
        if not title_elem:
            continue
        title_text = title_elem.get_text(strip=True)
        match = re.search(r'(\d+)', title_text)
        if not match:
            continue
        season_num = int(match.group(1))
        onclick = season_div.get('onclick')
        if not onclick:
            continue
        url_match = re.search(r'[\'"]([^\'"]+)[\'"]', onclick)
        if not url_match:
            continue
        season_url = url_match.group(1)
        if season_url.startswith('?'):
            season_url = base_url.rstrip('/') + season_url
        elif season_url.startswith('/'):
            season_url = base_url.rstrip('/') + season_url
        else:
            season_url = season_url
        seasons.append({'number': season_num, 'page_url': season_url})
    return seasons

def extract_episodes_from_season_page(soup: BeautifulSoup) -> list:
    episode_links = []
    ep_all = soup.select_one('#epAll, .epAll')
    if not ep_all:
        return episode_links
    for a in ep_all.find_all('a', href=True):
        href = a['href'].strip()
        if href and ('episodes' in href or '/?p=' in href):
            episode_links.append(href)
    return episode_links

def save_episodes_for_series(category: str, content_id: str, seasons_data: dict):
    if not seasons_data:
        return
    episodes_dir = f"./output/episodes/{category}"
    os.makedirs(episodes_dir, exist_ok=True)
    file_path = os.path.join(episodes_dir, f"{content_id}.json")
    output = {
        "content_id": content_id,
        "category": category,
        "seasons": seasons_data
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)
    print(f"💾 Saved episodes to {file_path}")

# ----------------------------------------------------------------------
# Main test function
# ----------------------------------------------------------------------
def test_episodes(category: str, content_id: str):
    """
    Extracts episodes for a given content ID using the stored SeasonsUrl.
    """
    json_file = f"./output/{category}.json"
    if not os.path.exists(json_file):
        print(f"❌ JSON file not found: {json_file}")
        print("   Please run FaselSeriesScraper.py first to populate the data.")
        return

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if content_id not in data:
        print(f"❌ Content ID {content_id} not found in {json_file}")
        return

    item = data[content_id]
    seasons_url = item.get('SeasonsUrl')
    if not seasons_url:
        print(f"⚠️ No 'SeasonsUrl' field for {content_id}. Please re-run FaselSeriesScraper.py to add it.")
        print("   Using detail URL as fallback...")
        # Fallback: construct a guess – but better to just exit.
        return

    print(f"\n🔍 Testing {category} ID {content_id}")
    print(f"   Seasons URL: {seasons_url}")

    resp = get_website_safe(seasons_url)
    if not resp or resp.status_code != 200:
        print(f"❌ Failed to load seasons page (HTTP {resp.status_code if resp else 'None'})")
        return

    soup = BeautifulSoup(resp.text, 'html.parser')
    seasons = extract_seasons_from_page(soup, FASEL_BASE_URL)
    print(f"   Found {len(seasons)} season(s)")

    episodes_by_season = {}
    for season in seasons:
        season_num = season['number']
        season_url = season['page_url']
        print(f"   Season {season_num}: {season_url}")
        season_resp = get_website_safe(season_url)
        if season_resp and season_resp.status_code == 200:
            season_soup = BeautifulSoup(season_resp.text, 'html.parser')
            ep_list = extract_episodes_from_season_page(season_soup)
            if ep_list:
                episodes_by_season[season_num] = ep_list
                print(f"      ✅ {len(ep_list)} episodes found")
                print(f"      First episode: {ep_list[0]}")
            else:
                print(f"      ⚠️ No episodes found on this page")
        else:
            print(f"      ❌ Failed to fetch season page")
        time.sleep(REQUEST_DELAY / 2)

    if episodes_by_season:
        save_episodes_for_series(category, content_id, episodes_by_season)
    else:
        print("   ❌ No episodes extracted.")

# ----------------------------------------------------------------------
# Command line entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_episodes_extraction.py <category> <content_id>")
        print("Example: python test_episodes_extraction.py series 4307")
        print("         python test_episodes_extraction.py tvshows 131775")
        print("         python test_episodes_extraction.py asian-series 63030")
        sys.exit(1)

    category = sys.argv[1]
    content_id = sys.argv[2]

    if category not in ["series", "tvshows", "asian-series"]:
        print(f"❌ Invalid category. Use one of: series, tvshows, asian-series")
        sys.exit(1)

    test_episodes(category, content_id)