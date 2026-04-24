import json
import random
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, clean_iframe_source, get_content_format, get_genres,
    extract_country, extract_runtime
)

PATHS = ["series", "tvshows", "asian-series"]
FAILED_DETAIL_URLS = set()

def fetch_detail(detail_url: str):
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    else:
        FAILED_DETAIL_URLS.add(detail_url)
        return None, None

def scrape_series_full(path: str):
    category_url = FASEL_BASE_URL + path
    total_pages = get_number_of_pages(category_url)
    print(f"[{path}] Total pages: {total_pages}")

    all_series = {}
    for page in range(1, total_pages + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)

        page_url = get_paginated_url(category_url, page)
        print(f"[{path}] Page {page}/{total_pages}: {page_url}")
        main = get_website_safe(page_url)
        if not main:
            continue

        soup = BeautifulSoup(main.text, "html.parser")
        divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or \
               soup.select('.blockMovie') or \
               soup.select('.postDiv')
        if not divs:
            continue

        detail_urls = [d.find("a")["href"] for d in divs if d.find("a")]
        if not detail_urls:
            continue

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
            if not series_id:
                continue

            title_elem = div.find("div", class_="h5") or div.find("div", class_="h1")
            title = title_elem.text.strip() if title_elem else "Unknown"
            img = div.find("img")
            img_src = img.get("data-src") or img.get("src", "") if img else ""

            # Optional iframe source (empty; will be fetched on‑demand)
            iframe = dsoup.find("iframe")
            source = ""
            if iframe and iframe.get("src"):
                source = clean_iframe_source(iframe["src"])

            new_series[series_id] = {
                "Title": title,
                "Category": path,
                "Image Source": img_src,
                "Source": source,
                "Format": get_content_format(dsoup),
                genres_info = get_genres_both(dsoup)
                "Runtime": extract_runtime(dsoup),
                "Country": extract_country(dsoup),
                "Seasons": {}
            }
            if DEBUG:
                print(f"    Added {series_id}: {title}")

        all_series.update(new_series)
        print(f"[{path}] Page {page} done: added {len(new_series)} series, total {len(all_series)}")
        os.makedirs("./output", exist_ok=True)
        with open(f"./output/{path}.json", "w", encoding="utf-8") as f:
            json.dump(all_series, f, indent=4, ensure_ascii=False)

    if FAILED_DETAIL_URLS:
        print(f"[{path}] Retrying {len(FAILED_DETAIL_URLS)} failed detail URLs...")
        for url in FAILED_DETAIL_URLS:
            resp = get_website_safe(url)
            if resp:
                dsoup = BeautifulSoup(resp.text, "html.parser")
                series_id = get_content_id(dsoup) or url.split('/')[-2]
                if series_id not in all_series:
                    all_series[series_id] = {
                        "Title": "Unknown (retried)",
                        "Category": path,
                        "Image Source": "",
                        "Source": "",
                        "Format": get_content_format(dsoup),
                        genres_info = get_genres_both(dsoup)
                        "Runtime": extract_runtime(dsoup),
                        "Country": extract_country(dsoup),
                        "Seasons": {}
                    }
        with open(f"./output/{path}.json", "w", encoding="utf-8") as f:
            json.dump(all_series, f, indent=4, ensure_ascii=False)

    print(f"[{path}] Finished. Total: {len(all_series)}")

def main():
    for path in PATHS:
        scrape_series_full(path)

if __name__ == "__main__":
    main()