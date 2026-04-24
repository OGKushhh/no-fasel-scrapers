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
    get_content_id, clean_iframe_source, get_content_format, get_genres_both,
    extract_country, extract_runtime
)

# ----------------------------------------------------------------------
#  Progress helpers
# ----------------------------------------------------------------------
def load_progress():
    progress_file = "./output/last_page_movies.txt"
    if os.path.exists(progress_file):
        with open(progress_file, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(page_num):
    os.makedirs("./output", exist_ok=True)
    with open("./output/last_page_movies.txt", "w") as f:
        f.write(str(page_num))

# Load existing movies
try:
    with open("./output/movies.json", "r", encoding="utf-8") as f:
        existing_movies = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    existing_movies = {}
existing_ids = set(existing_movies.keys())

FAILED_DETAIL_URLS = set()

def fetch_detail(detail_url: str):
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    else:
        FAILED_DETAIL_URLS.add(detail_url)
        return None, None

def scrape_movies_resumable():
    category_url = FASEL_BASE_URL + "movies"
    total_pages = get_number_of_pages(category_url)
    start_page = load_progress() + 1
    if start_page > total_pages:
        print("All pages already completed.")
        return

    print(f"Total movie pages: {total_pages}")
    print(f"Resuming from page {start_page}")

    all_movies = existing_movies.copy()
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
            print("  No movie containers found")
            continue

        # Extract IDs from the page (without detail fetch)
        page_ids = []
        for div in divs:
            link = div.find("a")
            if link and link.get("href"):
                movie_id = link["href"].split('/')[-2]
                page_ids.append(movie_id)

        # If all IDs are already known, stop incremental
        if all(mid in existing_ids for mid in page_ids):
            print(f"  Page {page} contains only already scraped movies. Stopping.")
            save_progress(page)
            break

        # Collect detail URLs only for new movies
        detail_urls = []
        for div in divs:
            link = div.find("a")
            if link:
                detail_url = link["href"]
                movie_id = detail_url.split('/')[-2]
                if movie_id not in existing_ids:
                    detail_urls.append(detail_url)
        if not detail_urls:
            print("  No new movies on this page")
            save_progress(page)
            continue

        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fetch_detail, url): url for url in detail_urls}
            for fut in as_completed(futures):
                url, html = fut.result()
                if url and html:
                    detail_map[url] = html

        new_movies = {}
        for div in divs:
            link = div.find("a")
            if not link:
                continue
            detail_url = link["href"]
            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            dsoup = BeautifulSoup(detail_html, "html.parser")

            movie_id = get_content_id(dsoup)
            if not movie_id:
                match = re.search(r'-(\d+)$', detail_url.rstrip('/'))
                if match:
                    movie_id = match.group(1)
                else:
                    movie_id = detail_url.split('/')[-2]
            if not movie_id or movie_id in existing_ids:
                continue

            iframe = dsoup.find("iframe")
            source = ""
            if iframe and iframe.get("src"):
                source = clean_iframe_source(iframe["src"])

            title_elem = div.find("div", class_="h5") or div.find("div", class_="h1")
            title = title_elem.text.strip() if title_elem else "Unknown"
            img = div.find("img")
            img_src = img.get("data-src") or img.get("src", "") if img else ""

            genres_info = get_genres_both(dsoup)

            new_movies[movie_id] = {
                "Title": title,
                "Category": "movies",
                "Image Source": img_src,
                "Source": source,
                "Genres": genres_info["en"],
                "GenresAr": genres_info["ar"],
                "Format": get_content_format(dsoup),
                "Runtime": extract_runtime(dsoup),
                "Country": extract_country(dsoup),
            }
            existing_ids.add(movie_id)

        all_movies.update(new_movies)
        print(f"  Page {page} done: added {len(new_movies)} movies, total {len(all_movies)}")

        os.makedirs("./output", exist_ok=True)
        with open("./output/movies.json", "w", encoding="utf-8") as f:
            json.dump(all_movies, f, indent=4, ensure_ascii=False)
        save_progress(page)
        print("  Saved progress and JSON")

    if FAILED_DETAIL_URLS:
        print(f"\nRetrying {len(FAILED_DETAIL_URLS)} failed detail URLs...")
        for url in FAILED_DETAIL_URLS:
            resp = get_website_safe(url)
            if resp:
                dsoup = BeautifulSoup(resp.text, "html.parser")
                movie_id = get_content_id(dsoup) or url.split('/')[-2]
                if movie_id not in existing_ids:
                    all_movies[movie_id] = {
                        "Title": "Unknown (retried)",
                        "Category": "movies",
                        "Image Source": "",
                        "Source": "",
                        "Genres": [],
                        "GenresAr": [],
                        "Format": get_content_format(dsoup),
                        "Runtime": extract_runtime(dsoup),
                        "Country": extract_country(dsoup),
                    }
            sleep(1)
        with open("./output/movies.json", "w", encoding="utf-8") as f:
            json.dump(all_movies, f, indent=4, ensure_ascii=False)

    print(f"\nFinished. Total movies: {len(all_movies)}")

if __name__ == "__main__":
    scrape_movies_resumable()