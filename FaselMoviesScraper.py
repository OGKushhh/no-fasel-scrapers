import asyncio
import json
import random
from bs4 import BeautifulSoup
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, JITTER,
    get_paginated_url, get_number_of_pages_async, get_category_page_async,
    get_website_safe_async, get_content_id, upload_image, clean_iframe_source,
    get_content_format, get_genres
)

# Load existing movies
try:
    with open("./output/movies.json") as fp:
        old_movies_dict = json.load(fp)
except (FileNotFoundError, json.JSONDecodeError):
    old_movies_dict = {}


async def scrape_all_movies():
    """Scrape all movie pages using async helpers (Scrapling)."""
    category_url = FASEL_BASE_URL + "movies"
    total_pages = await get_number_of_pages_async(category_url)
    if DEBUG:
        print(f"Total movie pages: {total_pages}")

    all_movies = {}
    for page in range(1, total_pages + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        await asyncio.sleep(delay)

        page_url = get_paginated_url(category_url, page)
        if DEBUG:
            print(f"Scraping page {page}/{total_pages}: {page_url}")

        # Fetch page HTML using async helper
        html = await get_website_safe_async(page_url)
        if not html:
            if DEBUG:
                print(f"Failed to fetch page {page}")
            continue

        soup = BeautifulSoup(html, "html.parser")
        movie_divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or soup.select('.blockMovie')
        if not movie_divs:
            continue

        # Process each movie on this page
        page_movies = {}
        for movie in movie_divs:
            link = movie.select_one('a')
            if not link or not link.get('href'):
                continue
            detail_url = link['href']
            # Fetch detail page HTML
            detail_html = await get_website_safe_async(detail_url)
            if not detail_html:
                continue
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            # Extract movie ID
            movie_id = get_content_id(detail_soup)
            if not movie_id or movie_id in old_movies_dict:
                continue
            # Extract iframe source
            iframe = detail_soup.find('iframe')
            if not iframe or not iframe.get('src'):
                continue
            source = clean_iframe_source(iframe['src'])
            # Extract data from list page element
            title_elem = movie.select_one('.h5') or movie.select_one('.h1')
            title = title_elem.text.strip() if title_elem else "Unknown Movie"
            img = movie.select_one('img')
            img_src = img.get('data-src') or img.get('src', '') if img else ""
            # Assemble movie dict
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
    asyncio.run(scrape_all_movies())