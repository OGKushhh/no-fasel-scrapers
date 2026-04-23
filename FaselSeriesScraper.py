import asyncio
import json
import random
from scrapling.fetchers import StealthySession
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER, upload_image,
    get_paginated_url, get_number_of_pages, remove_arabic_chars
)

PATHS_TO_SCRAPE = ["series", "tvshows", "asian-series"]


async def fetch_series_details(session: StealthySession, detail_url: str) -> tuple:
    try:
        resp = await session.fetch_async(detail_url, headless=True)
        return (detail_url, resp.html, resp.status) if resp and resp.status == 200 else (None, None, None)
    except Exception as e:
        if DEBUG:
            print(f"Error fetching {detail_url}: {e}")
        return None, None, None


async def scrape_all_series(path: str):
    category_url = FASEL_BASE_URL + path
    total_pages = get_number_of_pages(category_url)

    if DEBUG:
        print(f"Total pages for {path}: {total_pages}")

    all_series = {}
    async with StealthySession(headless=True, network_idle=True) as session:
        for page in range(1, total_pages + 1):
            delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
            if delay < 0.5:
                delay = 0.5
            await asyncio.sleep(delay)

            page_url = get_paginated_url(category_url, page)
            if DEBUG:
                print(f"Scraping {path} page {page}/{total_pages}: {page_url}")

            main_resp = await session.fetch_async(page_url, headless=True)
            if not main_resp or main_resp.status != 200:
                continue

            series_divs = main_resp.css('.col-xl-2.col-lg-2.col-md-3.col-sm-3')
            if not series_divs:
                series_divs = main_resp.css('.blockMovie')
            if not series_divs:
                continue

            detail_urls = [div.css('a').first.attrs.get('href') for div in series_divs if div.css('a').first]
            tasks = [fetch_series_details(session, url) for url in detail_urls]
            detail_pages = await asyncio.gather(*tasks)
            html_map = {url: html for url, html, _ in detail_pages if url and html}

            for series in series_divs:
                link = series.css('a').first
                if not link:
                    continue
                detail_url = link.attrs.get('href')
                detail_html = html_map.get(detail_url)
                if not detail_html:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(detail_html, "html.parser")
                series_id = soup.find('span', id='liskSh')
                series_id = series_id.text.split('=')[-1] if series_id else None
                if not series_id:
                    continue

                title_elem = series.css('.h5').first or series.css('.h1').first
                title = title_elem.text.strip() if title_elem else "Unknown Series"
                img = series.css('img').first
                img_src = img.attrs.get('data-src') or img.attrs.get('src', '') if img else ""

                # Load existing data if present
                file_path = f"./output/{path}.json"
                try:
                    with open(file_path, "r") as fp:
                        old_series = json.load(fp)
                except:
                    old_series = {}

                if series_id in old_series:
                    # Skip if already scraped
                    continue

                all_series[series_id] = {
                    "Title": title,
                    "Category": path,
                    "Image Source": img_src,
                }

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
        print(f"Finished {path}, total: {len(existing)}")


async def main():
    for path in PATHS_TO_SCRAPE:
        await scrape_all_series(path)


if __name__ == "__main__":
    asyncio.run(main())