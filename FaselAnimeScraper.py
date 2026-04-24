import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, clean_iframe_source, get_content_format, get_genres,
    upload_image, remove_arabic_chars
)

# Load existing anime data
try:
    with open("./output/anime.json") as fp:
        old_anime_dict = json.load(fp)
except (FileNotFoundError, json.JSONDecodeError):
    old_anime_dict = {}


def fetch_detail_page(detail_url: str):
    """Fetch a single anime series detail page."""
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    return None, None


def scrape_all_anime():
    category_url = FASEL_BASE_URL + "anime"
    total_pages = get_number_of_pages(category_url)
    if DEBUG:
        print(f"Total anime pages: {total_pages}")

    all_anime = {}
    for page in range(1, total_pages + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)

        page_url = get_paginated_url(category_url, page)
        if DEBUG:
            print(f"Scraping anime page {page}/{total_pages}: {page_url}")

        main_resp = get_website_safe(page_url)
        if not main_resp:
            if DEBUG:
                print(f"Failed to fetch page {page}")
            continue

        soup = BeautifulSoup(main_resp.text, "html.parser")
        anime_divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3')
        if not anime_divs:
            anime_divs = soup.select('.blockMovie')
        if not anime_divs:
            continue

        # Collect detail URLs for all anime on this page
        detail_urls = []
        for anime in anime_divs:
            link = anime.select_one('a')
            if link and link.get('href'):
                detail_urls.append(link['href'])

        # Fetch all detail pages concurrently
        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(fetch_detail_page, url): url for url in detail_urls}
            for future in as_completed(future_to_url):
                url, html = future.result()
                if url and html:
                    detail_map[url] = html

        # Process each anime on this page
        page_anime = {}
        for anime in anime_divs:
            link = anime.select_one('a')
            if not link or not link.get('href'):
                continue
            detail_url = link['href']
            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            anime_id = get_content_id(detail_soup)
            if not anime_id or anime_id in old_anime_dict:
                continue

            # Extract episode list
            ep_all_div = detail_soup.find("div", class_="epAll")
            episodes_list = ep_all_div.find_all("a") if ep_all_div else []
            total_episodes = len(episodes_list)

            # Extract title from list page
            title_elem = anime.select_one('.h5') or anime.select_one('.h1')
            title = title_elem.text.strip() if title_elem else "Unknown Anime"
            img = anime.select_one('img')
            img_src = img.get('data-src') or img.get('src', '') if img else ""

            # Optional: extract episode sources (complicated – you can skip or implement later)
            # For now, store empty episodes dict; you can add a separate episode scraper.
            page_anime[anime_id] = {
                "Title": title,
                "Category": "anime",
                "Number Of Episodes": total_episodes,
                "Image Source": img_src,
                "Format": get_content_format(detail_soup),
                "Genres": get_genres(detail_soup),
                "Episodes": {}   # To be filled by a separate episode scraper if needed
            }
        all_anime.update(page_anime)
        if DEBUG:
            print(f"Page {page} done, new anime: {len(page_anime)}")

    # Merge and save
    old_anime_dict.update(all_anime)
    with open("./output/anime.json", "w") as fp:
        json.dump(old_anime_dict, fp, indent=4)
    if DEBUG:
        print(f"Total anime now: {len(old_anime_dict)}")


if __name__ == "__main__":
    scrape_all_anime()