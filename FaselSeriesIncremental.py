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

PATHS = ["series", "tvshows", "asian-series"]
FAILED_DETAIL_URLS = set()

# ----------------------------------------------------------------------
# Season & episode extraction functions
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

def save_episodes_for_series(category: str, series_id: str, seasons_data: dict):
    if not seasons_data:
        return
    episodes_dir = f"./output/episodes/{category}"
    os.makedirs(episodes_dir, exist_ok=True)
    file_path = os.path.join(episodes_dir, f"{series_id}.json")
    output = {
        "content_id": series_id,
        "category": category,
        "seasons": seasons_data
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved episodes for {category}/{series_id} ({len(seasons_data)} seasons)")

def get_seasons_url_from_detail(detail_url: str) -> str:
    if any(prefix in detail_url for prefix in ['/seasons/', '/tvseasons/', '/asian_seasons/']):
        return detail_url
    resp = get_website_safe(detail_url)
    if not resp:
        return detail_url
    soup = BeautifulSoup(resp.text, 'html.parser')
    season_div = soup.select_one('#seasonList .seasonDiv')
    if not season_div:
        return detail_url
    onclick = season_div.get('onclick')
    if not onclick:
        return detail_url
    match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
    if match:
        season_url = match.group(1)
        if season_url.startswith('?'):
            return FASEL_BASE_URL.rstrip('/') + season_url
        elif season_url.startswith('/'):
            return FASEL_BASE_URL.rstrip('/') + season_url
        else:
            return season_url
    return detail_url

# ----------------------------------------------------------------------
# Incremental scraper
# ----------------------------------------------------------------------
def fetch_detail(detail_url: str):
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    else:
        FAILED_DETAIL_URLS.add(detail_url)
        return None, None

def scrape_series_incremental(path: str):
    category_url = FASEL_BASE_URL + path
    total_pages = get_number_of_pages(category_url)
    print(f"\n[{path}] Total pages: {total_pages}")

    # Load existing series
    try:
        with open(f"./output/{path}.json", "r", encoding="utf-8") as f:
            existing_series = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing_series = {}

    existing_ids = set(existing_series.keys())
    all_series = existing_series.copy()
    stop = False
    page = 1

    while not stop and page <= total_pages:
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)

        page_url = get_paginated_url(category_url, page)
        print(f"[{path}] Page {page}/{total_pages}: {page_url}")
        main = get_website_safe(page_url)
        if not main:
            print("  Failed to fetch list page")
            page += 1
            continue

        soup = BeautifulSoup(main.text, "html.parser")
        divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or \
               soup.select('.blockMovie') or \
               soup.select('.postDiv')
        if not divs:
            print("  No series containers found")
            page += 1
            continue

        # Extract IDs from the page
        page_ids = []
        for div in divs:
            link = div.find("a")
            if link and link.get("href"):
                series_id = link["href"].split('/')[-2]
                page_ids.append(series_id)

        # If all IDs on this page are already known → stop
        if all(mid in existing_ids for mid in page_ids):
            print(f"  Page {page} contains only already scraped series. Stopping.")
            stop = True
            break

        # Collect detail URLs only for new series
        detail_urls = []
        for div in divs:
            link = div.find("a")
            if link:
                detail_url = link["href"]
                series_id = detail_url.split('/')[-2]
                if series_id not in existing_ids:
                    detail_urls.append(detail_url)
        if not detail_urls:
            print("  No new series on this page")
            page += 1
            continue

        # Fetch new detail pages concurrently
        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fetch_detail, url): url for url in detail_urls}
            for fut in as_completed(futures):
                url, html = fut.result()
                if url and html:
                    detail_map[url] = html

        new_series = {}
        for div in divs:
            link = div.find("a")
            if not link:
                continue
            detail_url = link["href"]
            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            dsoup = BeautifulSoup(detail_html, "html.parser")

            series_id = get_content_id(dsoup)
            if not series_id:
                match = re.search(r'-(\d+)$', detail_url.rstrip('/'))
                if match:
                    series_id = match.group(1)
                else:
                    series_id = detail_url.split('/')[-2]
            if not series_id or series_id in existing_ids:
                continue

            # Basic metadata
            title_elem = div.find("div", class_="h5") or div.find("div", class_="h1")
            title = title_elem.text.strip() if title_elem else "Unknown"
            img = div.find("img")
            img_src = img.get("data-src") or img.get("src", "") if img else ""

            iframe = dsoup.find("iframe")
            source = ""
            if iframe and iframe.get("src"):
                source = clean_iframe_source(iframe["src"])

            genres_info = get_genres_both(dsoup)
            description = extract_description(dsoup)

            # Get seasons hub URL and extract episodes
            seasons_hub_url = get_seasons_url_from_detail(detail_url)
            seasons_with_episodes = {}
            if seasons_hub_url:
                if seasons_hub_url == detail_url:
                    hub_soup = dsoup
                else:
                    hub_resp = get_website_safe(seasons_hub_url)
                    hub_soup = BeautifulSoup(hub_resp.text, 'html.parser') if hub_resp else None
                if hub_soup:
                    seasons_list = extract_seasons_from_page(hub_soup, FASEL_BASE_URL)
                    for season in seasons_list:
                        season_num = season['number']
                        season_url = season['page_url']
                        season_resp = get_website_safe(season_url)
                        if season_resp:
                            season_soup = BeautifulSoup(season_resp.text, 'html.parser')
                            episode_urls = extract_episodes_from_season_page(season_soup)
                            if episode_urls:
                                seasons_with_episodes[season_num] = episode_urls
                        time.sleep(REQUEST_DELAY / 2)

            # Save episodes separately
            if seasons_with_episodes:
                save_episodes_for_series(path, series_id, seasons_with_episodes)

            # Main series entry
            new_series[series_id] = {
                "Title": title,
                "Category": path,
                "Image Source": img_src,
                "Source": source,
                "Genres": genres_info["en"],
                "GenresAr": genres_info["ar"],
                "Format": get_content_format(dsoup),
                "Runtime": extract_runtime(dsoup),
                "Country": extract_country(dsoup),
                "Description": description,
                "SeasonsUrl": seasons_hub_url
            }
            existing_ids.add(series_id)

        all_series.update(new_series)
        print(f"  Page {page} done: added {len(new_series)} series, total {len(all_series)}")

        os.makedirs("./output", exist_ok=True)
        with open(f"./output/{path}.json", "w", encoding="utf-8") as f:
            json.dump(all_series, f, indent=4, ensure_ascii=False)
        print(f"  Saved {path}.json")

        page += 1

    # Retry failed detail URLs
    if FAILED_DETAIL_URLS:
        print(f"\n[{path}] Retrying {len(FAILED_DETAIL_URLS)} failed detail URLs...")
        for url in list(FAILED_DETAIL_URLS):
            resp = get_website_safe(url)
            if resp:
                dsoup = BeautifulSoup(resp.text, "html.parser")
                series_id = get_content_id(dsoup) or url.split('/')[-2]
                if series_id not in existing_ids:
                    all_series[series_id] = {
                        "Title": "Unknown (retried)",
                        "Category": path,
                        "Image Source": "",
                        "Source": "",
                        "Genres": [],
                        "GenresAr": [],
                        "Format": get_content_format(dsoup),
                        "Runtime": extract_runtime(dsoup),
                        "Country": extract_country(dsoup),
                        "Description": extract_description(dsoup),
                        "SeasonsUrl": get_seasons_url_from_detail(url)
                    }
            sleep(1)
        with open(f"./output/{path}.json", "w", encoding="utf-8") as f:
            json.dump(all_series, f, indent=4, ensure_ascii=False)
        FAILED_DETAIL_URLS.clear()

    print(f"[{path}] Finished. Total: {len(all_series)}")

def main():
    for path in PATHS:
        scrape_series_incremental(path)

if __name__ == "__main__":
    main()