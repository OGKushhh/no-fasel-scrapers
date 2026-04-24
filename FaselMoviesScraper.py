import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_website_safe, get_number_of_pages, get_paginated_url,
    get_content_id, clean_iframe_source, get_content_format, get_genres,
    upload_image
)

# Load existing movies
try:
    with open("./output/movies.json") as fp:
        old_movies_dict = json.load(fp)
except (FileNotFoundError, json.JSONDecodeError):
    old_movies_dict = {}


def fetch_detail_page(detail_url: str):
    """Fetch a single detail page using Common.get_website_safe."""
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        return detail_url, resp.text
    return None, None


def scrape_all_movies():
    category_url = FASEL_BASE_URL + "movies"
    total_pages = get_number_of_pages(category_url)
    if DEBUG:
        print(f"Total movie pages: {total_pages}")

    all_movies = {}
    for page in range(1, total_pages + 1):
        # Rate limiting delay with jitter
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)

        page_url = get_paginated_url(category_url, page)
        if DEBUG:
            print(f"Scraping page {page}/{total_pages}: {page_url}")

        # Fetch the category page
        main_resp = get_website_safe(page_url)
        if not main_resp:
            if DEBUG:
                print(f"Failed to fetch page {page}")
            continue

        soup = BeautifulSoup(main_resp.text, "html.parser")
        movie_divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or soup.select('.blockMovie')
        if not movie_divs:
            if DEBUG:
                print(f"No movie containers on page {page}")
            continue

        # Collect detail URLs
        detail_urls = []
        for movie in movie_divs:
            link = movie.select_one('a')
            if link and link.get('href'):
                detail_urls.append(link['href'])

        # Fetch all detail pages concurrently (threads)
        detail_map = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(fetch_detail_page, url): url for url in detail_urls}
            for future in as_completed(future_to_url):
                url, html = future.result()
                if url and html:
                    detail_map[url] = html

        # Process each movie
        page_movies = {}
        for movie in movie_divs:
            link = movie.select_one('a')
            if not link or not link.get('href'):
                continue
            detail_url = link['href']
            detail_html = detail_map.get(detail_url)
            if not detail_html:
                continue
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            movie_id = get_content_id(detail_soup)
            if not movie_id or movie_id in old_movies_dict:
                continue
            iframe = detail_soup.find('iframe')
            if not iframe or not iframe.get('src'):
                continue
            source = clean_iframe_source(iframe['src'])
            title_elem = movie.select_one('.h5') or movie.select_one('.h1')
            title = title_elem.text.strip() if title_elem else "Unknown Movie"
            img = movie.select_one('img')
            img_src = img.get('data-src') or img.get('src', '') if img else ""

            page_movies[movie_id] = {
                "Title": title,
                "Category": "movies",
                "Image Source": img_src,
                "Source": source,
                "Genres": get_genres(detail_soup),
                "Format": get_content_format(detail_soup),
            }
        all_movies.update(page_movies)
        if DEBUG:
            print(f"Page {page} done, new movies: {len(page_movies)}")

    # Merge and save
    old_movies_dict.update(all_movies)
    with open("./output/movies.json", "w") as fp:
        json.dump(old_movies_dict, fp, indent=4)
    if DEBUG:
        print(f"Total movies now: {len(old_movies_dict)}")


if __name__ == "__main__":
    scrape_all_movies()