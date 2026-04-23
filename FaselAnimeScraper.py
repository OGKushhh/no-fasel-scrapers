import asyncio
import json
import random
from scrapling.fetchers import StealthySession
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER, upload_image,
    get_content_format, get_paginated_url, get_number_of_pages,
    remove_arabic_chars, remove_year
)

try:
    with open("./output/anime.json") as fp:
        old_animes = json.load(fp)
except (FileNotFoundError, json.JSONDecodeError):
    old_animes = {}


async def fetch_anime_details(session: StealthySession, detail_url: str) -> tuple:
    """Fetch an anime series detail page."""
    try:
        resp = await session.fetch_async(detail_url, headless=True)
        return (detail_url, resp.html, resp.status) if resp and resp.status == 200 else (None, None, None)
    except Exception as e:
        if DEBUG:
            print(f"Error fetching {detail_url}: {e}")
        return None, None, None


async def scrape_all_anime():
    category_url = FASEL_BASE_URL + "anime"
    total_pages = get_number_of_pages(category_url)

    if DEBUG:
        print(f"Total anime pages: {total_pages}")

    all_anime = {}
    async with StealthySession(headless=True, network_idle=True) as session:
        for page in range(1, total_pages + 1):
            delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
            if delay < 0.5:
                delay = 0.5
            await asyncio.sleep(delay)

            page_url = get_paginated_url(category_url, page)
            if DEBUG:
                print(f"Scraping anime page {page}/{total_pages}: {page_url}")

            main_resp = await session.fetch_async(page_url, headless=True)
            if not main_resp or main_resp.status != 200:
                continue

            anime_divs = main_resp.css('.col-xl-2.col-lg-2.col-md-3.col-sm-3')
            if not anime_divs:
                continue

            # Collect all detail URLs
            detail_urls = [div.css('a').first.attrs.get('href') for div in anime_divs if div.css('a').first]
            tasks = [fetch_anime_details(session, url) for url in detail_urls]
            detail_pages = await asyncio.gather(*tasks)
            html_map = {url: html for url, html, _ in detail_pages if url and html}

            for anime in anime_divs:
                link = anime.css('a').first
                if not link:
                    continue
                detail_url = link.attrs.get('href')
                detail_html = html_map.get(detail_url)
                if not detail_html:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(detail_html, "html.parser")
                anime_id = soup.find('span', id='liskSh')
                anime_id = anime_id.text.split('=')[-1] if anime_id else None
                if not anime_id or anime_id in old_animes:
                    continue

                title_elem = anime.css('.h5').first or anime.css('.h1').first
                title = title_elem.text.strip() if title_elem else "Unknown Anime"
                img = anime.css('img').first
                img_src = img.attrs.get('data-src') or img.attrs.get('src', '') if img else ""

                # Extract episode list
                ep_all = soup.find('div', class_='epAll')
                episodes_list = ep_all.find_all('a') if ep_all else []
                current_episodes = len(episodes_list)

                all_anime[anime_id] = {
                    "Title": title,
                    "Category": "anime",
                    "Number Of Episodes": current_episodes,
                    "Format": soup.find('div', class_='format') or "N/A",
                    "Image Source": img_src,
                    "Episodes": {}  # You can later add episode scraping logic
                }

    old_animes.update(all_anime)
    with open("./output/anime.json", "w") as fp:
        json.dump(old_animes, fp, indent=4)

    if DEBUG:
        print(f"Finished scraping anime, total: {len(old_animes)}")


if __name__ == "__main__":
    asyncio.run(scrape_all_anime())