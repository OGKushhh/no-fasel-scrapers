import json
import random
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, clean_iframe_source, get_content_format, get_genres_both,
    extract_country, extract_runtime, extract_description
)

def load_progress():
    progress_file = "./output/last_page_anime.txt"
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(page_num):
    os.makedirs("./output", exist_ok=True)
    with open("./output/last_page_anime.txt", "w") as f:
        f.write(str(page_num))

def extract_episodes_from_detail_page(soup: BeautifulSoup) -> list:
    episode_links = []
    ep_all = soup.select_one('#epAll, .epAll')
    if not ep_all:
        return episode_links
    for a in ep_all.find_all('a', href=True):
        href = a['href'].strip()
        if href and ('episodes' in href or '/?p=' in href):
            episode_links.append(href)
    return episode_links

def save_episodes_for_anime(anime_id: str, episodes: list):
    if not episodes:
        return
    episodes_dir = "./output/episodes/anime"
    os.makedirs(episodes_dir, exist_ok=True)
    file_path = os.path.join(episodes_dir, f"{anime_id}.json")
    output = {
        "content_id": anime_id,
        "category": "anime",
        "seasons": {1: episodes}
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved {len(episodes)} episodes for anime/{anime_id}")

try:
    with open("./output/anime.json", "r", encoding="utf-8") as f:
        existing_anime = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    existing_anime = {}

existing_ids = set(existing_anime.keys())
FAILED_DETAIL_URLS = set()

def fetch_detail(detail_url: str):
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    else:
        FAILED_DETAIL_URLS.add(detail_url)
        return None, None

def scrape_anime_resumable():
    category_url = FASEL_BASE_URL + "anime"
    total_pages = get_number_of_pages(category_url)
    start_page = load_progress() + 1
    if start_page > total_pages:
        print("All anime pages already completed.")
        return

    print(f"Total anime pages: {total_pages}")
    print(f"Resuming from page {start_page}")

    all_anime = existing_anime.copy()
    for page in range(start_page, total_pages + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)

        page_url = get_paginated_url(category_url, page)
        print(f"\nPage {page}/{total_pages}: {page_url}")
        main = get_website_safe(page_url)
        if not main:
            print("  Failed to fetch list page")
            continue

        soup = BeautifulSoup(main.text, "html.parser")
        divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or \
               soup.select('.blockMovie') or \
               soup.select('.postDiv')
        if not divs:
            print("  No anime containers found")
            continue

        page_ids = []
        for div in divs:
            link = div.find("a")
            if link and link.get("href"):
                anime_id = link["href"].split('/')[-2]
                page_ids.append(anime_id)

        if all(mid in existing_ids for mid in page_ids):
            print(f"  Page {page} contains only already scraped anime. Stopping.")
            save_progress(page)
            break

        detail_urls = []
        for div in divs:
            link = div.find("a")
            if link:
                detail_url = link["href"]
                anime_id = detail_url.split('/')[-2]
                if anime_id not in existing_ids:
                    detail_urls.append(detail_url)
        if not detail_urls:
            print("  No new anime on this page")
            save_progress(page)
            continue

        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fetch_detail, url): url for url in detail_urls}
            for fut in as_completed(futures):
                url, html = fut.result()
                if url and html:
                    detail_map[url] = html

        new_anime = {}
        for div in divs:
            link = div.find("a")
            if not link:
                continue
            detail_url = link["href"]
            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            dsoup = BeautifulSoup(detail_html, "html.parser")

            anime_id = get_content_id(dsoup)
            if not anime_id:
                match = re.search(r'-(\d+)$', detail_url.rstrip('/'))
                if match:
                    anime_id = match.group(1)
                else:
                    anime_id = detail_url.split('/')[-2]
            if not anime_id or anime_id in existing_ids:
                continue

            title_elem = div.find("div", class_="h5") or div.find("div", class_="h1")
            title = title_elem.text.strip() if title_elem else "Unknown"
            img = div.find("img")
            img_src = img.get("data-src") or img.get("src", "") if img else ""

            episode_urls = extract_episodes_from_detail_page(dsoup)
            episode_count = len(episode_urls)
            content_type = "Series" if episode_count > 0 else "Movie"

            if episode_urls:
                save_episodes_for_anime(anime_id, episode_urls)

            iframe = dsoup.find("iframe")
            source = ""
            if iframe and iframe.get("src"):
                source = clean_iframe_source(iframe["src"])

            genres_info = get_genres_both(dsoup)
            description = extract_description(dsoup)

            new_anime[anime_id] = {
                "Title": title,
                "Category": "anime",
                "Type": content_type,
                "Number Of Episodes": episode_count,
                "Image Source": img_src,
                "Source": source,
                "Genres": genres_info["en"],
                "GenresAr": genres_info["ar"],
                "Format": get_content_format(dsoup),
                "Runtime": extract_runtime(dsoup),
                "Country": extract_country(dsoup),
                "Description": description,
                "SeasonsUrl": detail_url
            }
            existing_ids.add(anime_id)

        all_anime.update(new_anime)
        print(f"  Page {page} done: added {len(new_anime)} anime, total {len(all_anime)}")

        os.makedirs("./output", exist_ok=True)
        with open("./output/anime.json", "w", encoding="utf-8") as f:
            json.dump(all_anime, f, indent=4, ensure_ascii=False)
        save_progress(page)
        print("  Saved progress and JSON")

    if FAILED_DETAIL_URLS:
        print(f"\nRetrying {len(FAILED_DETAIL_URLS)} failed detail URLs...")
        for url in FAILED_DETAIL_URLS:
            resp = get_website_safe(url)
            if resp:
                dsoup = BeautifulSoup(resp.text, "html.parser")
                anime_id = get_content_id(dsoup) or url.split('/')[-2]
                if anime_id not in existing_ids:
                    all_anime[anime_id] = {
                        "Title": "Unknown (retried)",
                        "Category": "anime",
                        "Type": "Movie",
                        "Number Of Episodes": 0,
                        "Image Source": "",
                        "Source": "",
                        "Genres": [],
                        "GenresAr": [],
                        "Format": get_content_format(dsoup),
                        "Runtime": extract_runtime(dsoup),
                        "Country": extract_country(dsoup),
                        "Description": extract_description(dsoup),
                        "SeasonsUrl": url
                    }
            sleep(1)
        with open("./output/anime.json", "w", encoding="utf-8") as f:
            json.dump(all_anime, f, indent=4, ensure_ascii=False)

    print(f"\nFinished. Total anime: {len(all_anime)}")

if __name__ == "__main__":
    scrape_anime_resumable()