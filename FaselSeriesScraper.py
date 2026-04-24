import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, get_content_format, get_genres, upload_image
)

PATHS_TO_SCRAPE = ["series", "tvshows", "asian-series"]


def fetch_detail_page(detail_url: str):
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    return None, None


def scrape_all_series(path: str):
    category_url = FASEL_BASE_URL + path
    total_pages = get_number_of_pages(category_url)
    if DEBUG:
        print(f"Total pages for {path}: {total_pages}")

    all_series = {}
    for page in range(1, total_pages + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)

        page_url = get_paginated_url(category_url, page)
        if DEBUG:
            print(f"Scraping {path} page {page}/{total_pages}: {page_url}")

        main_resp = get_website_safe(page_url)
        if not main_resp:
            continue

        soup = BeautifulSoup(main_resp.text, "html.parser")
        series_divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3')
        if not series_divs:
            series_divs = soup.select('.blockMovie')
        if not series_divs:
            continue

        detail_urls = []
        for s in series_divs:
            link = s.select_one('a')
            if link and link.get('href'):
                detail_urls.append(link['href'])

        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(fetch_detail_page, url): url for url in detail_urls}
            for future in as_completed(future_to_url):
                url, html = future.result()
                if url and html:
                    detail_map[url] = html

        page_series = {}
        for s in series_divs:
            link = s.select_one('a')
            if not link or not link.get('href'):
                continue
            detail_url = link['href']
            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            series_id = get_content_id(detail_soup)
            if not series_id:
                continue

            title_elem = s.select_one('.h5') or s.select_one('.h1')
            title = title_elem.text.strip() if title_elem else "Unknown Series"
            img = s.select_one('img')
            img_src = img.get('data-src') or img.get('src', '') if img else ""

            # Load existing data for this path
            file_path = f"./output/{path}.json"
            try:
                with open(file_path, "r") as fp:
                    existing = json.load(fp)
            except:
                existing = {}

            if series_id in existing:
                continue

            # Basic info (seasons and episodes can be added later)
            page_series[series_id] = {
                "Title": title,
                "Category": path,
                "Image Source": img_src,
                "Format": get_content_format(detail_soup),
                "Genres": get_genres(detail_soup),
                "Seasons": {}
            }
        all_series.update(page_series)
        if DEBUG:
            print(f"{path} page {page} done, new series: {len(page_series)}")

    # Merge and save
    file_path = f"./output/{path}.json"
    try:
        with open(file_path, "r") as fp:
            existing = json.load(fp)
    except:
        existing = {}
    existing.update(all_series)
    with open(file_path, "w") as fp:
        json.dump(existing, fp, indent=4)
    if DEBUG:
        print(f"Total {path} now: {len(existing)}")


def main():
    for path in PATHS_TO_SCRAPE:
        scrape_all_series(path)


if __name__ == "__main__":
    main()