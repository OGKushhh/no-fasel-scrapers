#!/usr/bin/env python3
"""
AkwamArabicSeries.py – Arabic series scraper for akwam.com.co
- Extracts series metadata (no episodes inside main JSON)
- Saves episodes separately to ./output/episodes/arabic-series/{id}.json
- Progress stored as plain text (one ID per line)
"""

import json
import os
import sys
import re
import time
import random
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from Common import (
    DEBUG, get_website_safe, AKWAM_BASE_URL,
    akwam_extract_series_list, akwam_extract_series_metadata,
    akwam_extract_episode_sources
)

# ======== CONFIGURATION ========
REQUEST_DELAY = 2.0
JITTER = 0.3
PROGRESS_FILE = "./output/akwam_series_progress.txt"
OUTPUT_FILE = "./output/arabic-series.json"
EPISODES_BASE = Path("./output/episodes/arabic-series")
ARABIC_SECTION_ID = "29"
# =================================

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_progress(processed_ids):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        for pid in sorted(processed_ids):
            f.write(pid + '\n')

def load_existing_series():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_series(all_series):
    # Remove episodes from each series before saving main JSON
    clean_series = {}
    for sid, data in all_series.items():
        clean_data = {k: v for k, v in data.items() if k != 'episodes'}
        clean_series[sid] = clean_data
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(clean_series, f, indent=2, ensure_ascii=False)

def save_episodes(category: str, series_id: str, episodes_data: list):
    """Save episodes to separate JSON file."""
    EPISODES_BASE.mkdir(parents=True, exist_ok=True)
    file_path = EPISODES_BASE / f"{series_id}.json"
    output = {
        "content_id": series_id,
        "category": category,
        "episodes": episodes_data,
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    }
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    if DEBUG:
        print(f"  💾 Saved episodes to {file_path}")

def get_next_page_url(soup, base_url):
    next_link = soup.select_one('.pagination a[rel="next"]')
    if not next_link:
        next_link = soup.find('a', string='التالي')
    if next_link and next_link.get('href'):
        return urljoin(base_url, next_link['href'])
    return None

def extract_episode_number(title: str) -> int:
    """Extract episode number from title."""
    match = re.search(r'(\d+)', title)
    if match:
        return int(match.group(1))
    return None

def scrape_arabic_series():
    print("🚀 Starting Akwam Arabic Series Scraper (separate episodes)")
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
                if DEBUG:
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

            # Process episodes (extract sources, do NOT embed in main JSON)
            episodes_with_sources = []
            for ep in metadata.get('episodes', []):
                ep_url = ep['url']
                if DEBUG:
                    print(f"      Extracting sources from: {ep['title']}")
                ep_resp = get_website_safe(ep_url)
                if not ep_resp:
                    if DEBUG:
                        print(f"        ⚠️ Failed to fetch episode page")
                    continue
                ep_soup = BeautifulSoup(ep_resp.text, 'html.parser')
                sources = akwam_extract_episode_sources(ep_soup)
                ep_num = extract_episode_number(ep['title'])
                episodes_with_sources.append({
                    'number': ep_num,
                    'title': ep['title'],
                    'url': ep_url,
                    'sources': sources
                })
                time.sleep(0.5)

            # Save episodes to separate file
            if episodes_with_sources:
                save_episodes("arabic-series", series_id, episodes_with_sources)
            else:
                if DEBUG:
                    print(f"    ⚠️ No episodes found for {series_id}")

            # Update metadata with count (episodes removed before saving main JSON)
            metadata['episode_count'] = len(episodes_with_sources)
            # Remove the episodes list from metadata (will be saved separately)
            metadata.pop('episodes', None)

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
    print(f"Series metadata saved to {OUTPUT_FILE}")
    print(f"Episodes saved to {EPISODES_BASE}/")

if __name__ == "__main__":
    scrape_arabic_series()