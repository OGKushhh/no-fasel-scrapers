import json
import os
import re
import sys
import time
from Common import get_website_safe, FASEL_BASE_URL, REQUEST_DELAY
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

        seasons.append({
            'number': season_num,
            'page_url': season_url
        })
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

def save_episodes_for_id(category: str, content_id: str, seasons_data: dict):
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
def test_episodes(category: str, content_id: str, seasons_page_url: str):
    """
    category: 'series', 'tvshows', 'anime', 'asian-series'
    content_id: the ID as it appears in the main JSON (e.g., '4307')
    seasons_page_url: full URL to the /seasons/ page (e.g., https://www.fasel-hd.cam/seasons/the-walking-dead-all-seasons)
    """
    print(f"\n🔍 Testing {category} ID {content_id} - {seasons_page_url}")
    resp = get_website_safe(seasons_page_url)
    if not resp or resp.status_code != 200:
        print(f"  ❌ Failed to load page (status: {resp.status_code if resp else 'None'})")
        return

    soup = BeautifulSoup(resp.text, 'html.parser')
    seasons = extract_seasons_from_page(soup, FASEL_BASE_URL)
    print(f"  📺 Found {len(seasons)} season(s)")

    episodes_by_season = {}
    for season in seasons:
        season_num = season['number']
        season_url = season['page_url']
        print(f"    🎬 Season {season_num}: {season_url}")
        season_resp = get_website_safe(season_url)
        if season_resp and season_resp.status_code == 200:
            season_soup = BeautifulSoup(season_resp.text, 'html.parser')
            ep_list = extract_episodes_from_season_page(season_soup)
            if ep_list:
                episodes_by_season[season_num] = ep_list
                print(f"      ✅ {len(ep_list)} episodes found")
                print(f"      📄 First episode: {ep_list[0]}")
            else:
                print(f"      ⚠️ No episodes found on this page")
        else:
            print(f"      ❌ Failed to fetch season page")
        time.sleep(REQUEST_DELAY / 2)

    if episodes_by_season:
        save_episodes_for_id(category, content_id, episodes_by_season)
    else:
        print("  ❌ No episodes extracted.")

# ----------------------------------------------------------------------
# Example usage – replace the IDs and URLs with your own tests
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # You can call test_episodes() for any known ID and its seasons page URL
    # Example 1: The Walking Dead (series)
    test_episodes(
        category="series",
        content_id="4307",
        seasons_page_url="https://www.fasel-hd.cam/seasons/the-walking-dead-all-seasons"
    )

    # Example 2: Selling Sunset (tvshows)
    test_episodes(
        category="tvshows",
        content_id="283753",
        seasons_page_url="https://www.fasel-hd.cam/seasons/selling-sunset"
    )

    # Example 3: Avatar: The Last Airbender (anime – first season)
    test_episodes(
        category="anime",
        content_id="297027",
        seasons_page_url="https://www.fasel-hd.cam/seasons/avatar-the-last-airbender-season-1"
    )

    # Example 4: Filing for Love (asian-series)
    test_episodes(
        category="asian-series",
        content_id="298059",
        seasons_page_url="https://www.fasel-hd.cam/seasons/filing-for-love"
    )