#!/usr/bin/env python3
"""
Scrape only the first page of missing FaselHD categories (anime, series, tvshows, asian-series).
Useful for quickly populating your API with sample data.
"""

import os
import json
from time import sleep
from Common import (
    DEBUG, FASEL_BASE_URL, REQUEST_DELAY, get_website_safe,
    get_paginated_url, get_content_id, clean_iframe_source,
    get_content_format, get_genres_both, extract_country, extract_runtime
)
from bs4 import BeautifulSoup

# Enable debug to see progress
DEBUG = True

# Categories to scrape (movies already done)
CATEGORIES = [
    ("anime", "anime.json"),
    ("series", "series.json"),
    ("tvshows", "tvshows.json"),
    ("asian-series", "asian-series.json"),
]

def scrape_page_1(category, output_file):
    """Fetch page 1 of a category and save only items from that page."""
    print(f"\n=== Scraping {category} page 1 ===")
    page_url = get_paginated_url(FASEL_BASE_URL + category, 1)
    print(f"Fetching: {page_url}")
    resp = get_website_safe(page_url)
    if not resp:
        print(f"Failed to fetch {page_url}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    # Find all item containers
    divs = soup.select('.col-xl-2.col-lg-2.col-md-3.col-sm-3') or \
           soup.select('.blockMovie') or \
           soup.select('.postDiv')
    if not divs:
        print(f"No containers found for {category}")
        return

    result = {}
    for idx, div in enumerate(divs, 1):
        link_tag = div.find('a')
        if not link_tag:
            continue
        detail_url = link_tag['href']
        print(f"  [{idx}/{len(divs)}] Fetching {detail_url}")
        detail_resp = get_website_safe(detail_url)
        if not detail_resp:
            continue
        dsoup = BeautifulSoup(detail_resp.text, "html.parser")
        item_id = get_content_id(dsoup)
        if not item_id:
            # fallback to URL segment
            item_id = detail_url.split('/')[-2]
        # Basic fields
        title_elem = div.find('div', class_='h5') or div.find('div', class_='h1')
        title = title_elem.text.strip() if title_elem else "Unknown"
        img = div.find('img')
        img_src = img.get('data-src') or img.get('src', '') if img else ""
        iframe = dsoup.find('iframe')
        source = clean_iframe_source(iframe['src']) if iframe and iframe.get('src') else ""
        genres = get_genres_both(dsoup)
        quality = dsoup.find('span', class_='quality') or div.find('span', class_='quality')
        quality = quality.text.strip() if quality else ""
        runtime = extract_runtime(dsoup)
        country = extract_country(dsoup)

        result[item_id] = {
            "Title": title,
            "Category": category,
            "Image Source": img_src,
            "Source": source,
            "Genres": genres["en"],
            "GenresAr": genres["ar"],
            "Format": quality,
            "Runtime": runtime,
            "Country": country
        }

        # Category‑specific fields
        if category == "anime":
            ep_div = dsoup.find('div', class_='epAll')
            result[item_id]["Number Of Episodes"] = len(ep_div.find_all('a')) if ep_div else 0
            result[item_id]["Episodes"] = {}
        elif category in ["series", "tvshows", "asian-series"]:
            result[item_id]["Seasons"] = {}

        sleep(0.5)  # small delay between detail fetches

    # Save to output folder
    os.makedirs("./output", exist_ok=True)
    out_path = f"./output/{output_file}"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(result)} items to {out_path}")

def main():
    for category, out_file in CATEGORIES:
        scrape_page_1(category, out_file)
        print(f"Waiting {REQUEST_DELAY} seconds before next category...")
        sleep(REQUEST_DELAY)
    print("\nAll first pages scraped. You now have initial JSON files for anime, series, tvshows, asian-series in ./output/")

if __name__ == "__main__":
    main()