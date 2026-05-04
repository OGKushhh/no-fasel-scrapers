#!/usr/bin/env python3
"""
one_time_fetch_14506.py
Fetches series ID 14506 (the "%3" series) and its episodes.
Run once to add it to your database.
"""

import json
import re
import time
from pathlib import Path
from bs4 import BeautifulSoup
import Common  # import the whole module

SERIES_ID = "14506"
DETAIL_URL = f"{Common.FASEL_BASE_URL}?p={SERIES_ID}"

def fetch_with_retry(url, retries=3):
    for attempt in range(retries):
        resp = Common.get_website_safe(url)
        if resp and resp.status_code == 200:
            return resp
        print(f"Attempt {attempt+1} failed, retrying...")
        time.sleep(5)
    return None

def main():
    print(f"Fetching series ID {SERIES_ID} from {DETAIL_URL}...")
    resp = fetch_with_retry(DETAIL_URL)
    if not resp:
        print("Failed to fetch the page. The site may be down (502). Try again later.")
        return
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract metadata using Common functions
    title_elem = soup.select_one('.h1.title')
    title = title_elem.text.strip() if title_elem else "Unknown"
    img_elem = soup.select_one('.posterImg img')
    image = img_elem.get('src', '') if img_elem else ""
    description_elem = soup.select_one('.singleDesc p')
    description = description_elem.text.strip() if description_elem else ""
    status = Common.extract_status(soup)
    viewing_level = Common.extract_viewing_level(soup)
    language = Common.extract_language(soup)
    release_date = Common.extract_release_date(soup)
    episode_duration = Common.extract_episode_duration(soup)
    episode_count_text = Common.extract_episode_count_text(soup)
    genres_info = Common.get_genres_both(soup)
    sources = Common.extract_sources(soup)

    metadata = {
        "Title": title,
        "Category": "series",
        "Image Source": image,
        "Source": "",
        "Sources": sources,
        "Genres": genres_info["en"],
        "GenresAr": genres_info["ar"],
        "Format": Common.get_content_format(soup),
        "Runtime": Common.extract_runtime(soup),
        "Country": Common.extract_country(soup),
        "Description": description,
        "SeasonsUrl": DETAIL_URL,
        "Status": status,
        "ViewingLevel": viewing_level,
        "Language": language,
        "ReleaseDate": release_date,
        "EpisodeDuration": episode_duration,
        "Number Of Episodes Text": episode_count_text,
        "last_scraped": __import__("datetime").datetime.now().isoformat()
    }

    # Load existing series.json
    series_file = Path("./output/series.json")
    if series_file.exists():
        with open(series_file, "r", encoding="utf-8") as f:
            all_series = json.load(f)
    else:
        all_series = {}
    all_series[SERIES_ID] = metadata
    with open(series_file, "w", encoding="utf-8") as f:
        json.dump(all_series, f, indent=4, ensure_ascii=False)
    print(f"Added series {SERIES_ID} to series.json")

    # Extract episodes
    seasons_hub_url = Common.get_seasons_url_from_detail(DETAIL_URL)
    if seasons_hub_url:
        resp = Common.get_website_safe(seasons_hub_url)
        if resp:
            hub_soup = BeautifulSoup(resp.text, "html.parser")
            seasons_list = Common.extract_seasons_from_page(hub_soup, Common.FASEL_BASE_URL)
            if seasons_list:
                seasons_with_episodes = {}
                for season in seasons_list:
                    season_num = season['number']
                    season_url = season['page_url']
                    poster = season.get('poster', '')
                    season_resp = Common.get_website_safe(season_url)
                    if season_resp:
                        season_soup = BeautifulSoup(season_resp.text, 'html.parser')
                        episode_urls = Common.extract_episodes_from_season_page(season_soup)
                        episodes = []
                        for ep_url in episode_urls:
                            ep_resp = Common.get_website_safe(ep_url)
                            if ep_resp:
                                ep_soup = BeautifulSoup(ep_resp.text, 'html.parser')
                                sources = Common.extract_sources(ep_soup)
                            else:
                                sources = []
                            episodes.append({"url": ep_url, "sources": sources})
                            time.sleep(Common.REQUEST_DELAY / 2)
                        seasons_with_episodes[season_num] = {"poster": poster, "episodes": episodes}
                # Save episodes file
                episodes_dir = Path("./output/episodes/series")
                episodes_dir.mkdir(parents=True, exist_ok=True)
                episodes_file = episodes_dir / f"{SERIES_ID}.json"
                with open(episodes_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "content_id": SERIES_ID,
                        "category": "series",
                        "seasons": seasons_with_episodes,
                        "last_updated": __import__("datetime").datetime.now().isoformat()
                    }, f, indent=4, ensure_ascii=False)
                print(f"Saved episodes to {episodes_file}")
            else:
                print("No seasons found.")
        else:
            print("Failed to fetch seasons hub.")
    else:
        print("No seasons hub URL found.")

    print("Done.")

if __name__ == "__main__":
    main()