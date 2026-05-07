#!/usr/bin/env python3
"""
AkwamArabicSeries.py – Arabic series scraper for akwam.com.co
- Extracts series metadata (title, year, rating, genres, dates, cast, etc.)
- Extracts episodes with direct go.akwam.com.co URLs (watch/download)
- Does NOT resolve to final MP4 – front‑end will handle that.
- Saves episodes separately to ./output/episodes/arabic-series/{id}.json
"""

import json
import os
import re
import time
import random
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from Common import (
    get_website_safe, AKWAM_BASE_URL,
    akwam_extract_series_list, akwam_extract_series_metadata
)

# ======== CONFIGURATION ========
REQUEST_DELAY = 1.5
JITTER = 0.3
PROGRESS_FILE = "./output/akwam_series_progress.json"
OUTPUT_FILE = "./output/arabic-series.json"
ARABIC_SECTION_ID = "29"
# =================================

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_progress(processed_ids):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(processed_ids), f, ensure_ascii=False)

def load_existing_series():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_series(all_series):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_series, f, indent=2, ensure_ascii=False)

def get_next_page_url(soup, base_url):
    """Extract next page URL from pagination."""
    next_link = soup.select_one('.pagination a[rel="next"]')
    if not next_link:
        next_link = soup.find('a', string='التالي')
    if next_link and next_link.get('href'):
        return urljoin(base_url, next_link['href'])
    return None

def extract_episode_sources(soup: BeautifulSoup) -> list:
    """
    Extract quality sources from an Akwam episode page.
    Returns go.akwam.com.co URLs (watch and download) without resolving.
    """
    quality_map = {
        'tab-5': '1080p',
        'tab-4': '720p',
        'tab-3': '480p'
    }
    sources = []
    for tab_id, quality_name in quality_map.items():
        tab_content = soup.select_one(f'#{tab_id}')
        if not tab_content:
            continue
        watch_link = tab_content.select_one('.link-show')
        download_link = tab_content.select_one('.link-download')
        if not download_link:
            continue
        # File size
        size_elem = download_link.select_one('.font-size-14')
        size_mb = None
        if size_elem:
            size_text = size_elem.get_text(strip=True)
            match = re.search(r'([\d.]+)\s*MB', size_text)
            if match:
                size_mb = float(match.group(1))
        sources.append({
            'quality': quality_name,
            'watch_url': watch_link.get('href') if watch_link else None,
            'download_url': download_link.get('href'),
            'size_mb': size_mb
        })
    return sources

def scrape_arabic_series():
    print("🚀 Starting Akwam Arabic Series Scraper (unresolved sources)")
    processed_ids = load_progress()
    all_series = load_existing_series()

    base_listing_url = f"{AKWAM_BASE_URL}/series?section={ARABIC_SECTION_ID}&category=0&rating=0&year=0&language=0&formats=0&quality=0"
    current_url = base_listing_url
    page_num = 1

    while True:
        print(f"\n📄 Page {page_num}: {current_url}")
        resp = get_website_safe(current_url)
        if not resp or resp.status_code != 200:
            print("  ❌ Failed to fetch page")
            break

        soup = BeautifulSoup(resp.text, 'html.parser')
        series_list = akwam_extract_series_list(soup, AKWAM_BASE_URL)
        if not series_list:
            print("  No series found, stopping.")
            break

        new_count = 0
        for series in series_list:
            series_id = series['id']
            if series_id in processed_ids:
                print(f"  ⏭️ Skipping already processed: {series['title']} ({series_id})")
                continue

            print(f"  🔍 Fetching details for: {series['title']} ({series_id})")
            detail_resp = get_website_safe(series['url'])
            if not detail_resp:
                print("    ❌ Failed to fetch detail page")
                continue
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            metadata = akwam_extract_series_metadata(detail_soup, AKWAM_BASE_URL)

            # Merge basic info
            metadata.update({
                'id': series_id,
                'title': series['title'],
                'year': metadata.get('year') or series.get('year'),
                'rating': series.get('rating') or metadata.get('rating'),
                'poster': series.get('image') or metadata.get('poster', ''),
                'url': series['url']
            })

            # Process episodes (extract sources without resolving)
            episodes_with_sources = []
            for ep in metadata.get('episodes', []):
                ep_url = ep['url']
                print(f"      Extracting sources from: {ep['title']}")
                ep_resp = get_website_safe(ep_url)
                if not ep_resp:
                    print(f"        ⚠️ Failed to fetch episode page")
                    continue
                ep_soup = BeautifulSoup(ep_resp.text, 'html.parser')
                sources = extract_episode_sources(ep_soup)
                # Extract episode number
                ep_num = None
                num_match = re.search(r'الحلقة\s+(\d+)', ep['title'])
                if num_match:
                    ep_num = int(num_match.group(1))
                episodes_with_sources.append({
                    'number': ep_num,
                    'title': ep['title'],
                    'url': ep_url,
                    'sources': sources
                })
                time.sleep(0.5)  # gentle delay

            metadata['episodes'] = episodes_with_sources
            metadata['episode_count'] = len(episodes_with_sources)

            all_series[series_id] = metadata
            processed_ids.add(series_id)
            new_count += 1

            # Incremental save
            save_series(all_series)
            save_progress(processed_ids)
            print(f"    ✅ Added {series['title']} (total {len(all_series)} series)")

        print(f"  Page {page_num} done, added {new_count} new series")

        next_url = get_next_page_url(soup, AKWAM_BASE_URL)
        if not next_url:
            print("  No next page link. Finished.")
            break
        current_url = next_url
        page_num += 1
        time.sleep(REQUEST_DELAY + random.uniform(-JITTER, JITTER))

    print(f"\n🏁 Done. Total series: {len(all_series)}")
    print(f"Output saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    scrape_arabic_series()