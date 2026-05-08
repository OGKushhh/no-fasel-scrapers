#!/usr/bin/env python3
"""
AkwamArabicSeries.py – Parallel Arabic series scraper
- Saves progress (series ID) to text file immediately after each series.
- Thread‑safe using a lock.
"""

import json
import os
import sys
import re
import time
import random
import threading
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
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
MAX_WORKERS = 7
PROGRESS_FILE = "./output/akwam_series_progress.txt"
OUTPUT_FILE = "./output/arabic-series.json"
EPISODES_BASE = Path("./output/episodes/arabic-series")
ARABIC_SECTION_ID = "29"
# =================================

progress_lock = threading.Lock()
series_lock = threading.Lock()   # for updating all_series dict

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_progress_immediate(series_id):
    """Thread‑safe append of a single series ID."""
    with progress_lock:
        with open(PROGRESS_FILE, 'a', encoding='utf-8') as f:
            f.write(series_id + '\n')

def load_existing_series():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_series(all_series):
    # Remove episodes before saving main JSON
    clean_series = {}
    for sid, data in all_series.items():
        clean_data = {k: v for k, v in data.items() if k != 'episodes'}
        clean_series[sid] = clean_data
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(clean_series, f, indent=2, ensure_ascii=False)

def save_episodes(category: str, series_id: str, episodes_data: list):
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
    match = re.search(r'(\d+)', title)
    return int(match.group(1)) if match else None

def fetch_episode_page(url: str):
    for attempt_url in (url, url.replace('/%20', '/')):
        try:
            resp = get_website_safe(attempt_url)
            if resp and resp.status_code == 200:
                return resp
        except:
            continue
    return None

def process_series(series, all_series):
    """Process one series. Returns True if successful, False otherwise."""
    series_id = series['id']
    print(f"  🔍 Fetching details for: {series['title']} ({series_id})")
    detail_resp = get_website_safe(series['url'])
    if not detail_resp:
        print(f"    ❌ Failed to fetch detail page for {series['title']}")
        return False

    detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
    metadata = akwam_extract_series_metadata(detail_soup, AKWAM_BASE_URL)

    metadata.update({
        'id': series_id,
        'title': series['title'],
        'year': metadata.get('year') or series.get('year'),
        'rating': series.get('rating') or metadata.get('rating'),
        'poster': series.get('image') or metadata.get('poster', ''),
        'url': series['url']
    })

    # Process episodes sequentially
    episodes_with_sources = []
    for ep in metadata.get('episodes', []):
        ep_url = ep['url']
        if DEBUG:
            print(f"      Fetching: {ep['title'][:50]}...")
        ep_resp = fetch_episode_page(ep_url)
        if not ep_resp:
            print(f"      ⚠️ Episode not accessible: {ep['title'][:50]}... – skipping")
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

    episodes_with_sources.sort(key=lambda x: x['number'] if x['number'] is not None else 999999)

    if episodes_with_sources:
        save_episodes("arabic-series", series_id, episodes_with_sources)
    else:
        if DEBUG:
            print(f"    ⚠️ No episodes saved for {series_id}")

    metadata['episode_count'] = len(episodes_with_sources)
    metadata.pop('episodes', None)

    # Thread‑safe update of all_series
    with series_lock:
        all_series[series_id] = metadata
        save_series(all_series)   # Save all after each series (could be slow but safe)
    # Save progress immediately
    save_progress_immediate(series_id)
    print(f"    ✅ Added {series['title']} (total {len(all_series)} series)")
    return True

def scrape_arabic_series():
    print("🚀 Starting Akwam Arabic Series Scraper (parallel, per‑series progress)")
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

        # Series that are not yet processed
        new_series = [s for s in series_list if s['id'] not in processed_ids]
        if not new_series:
            print("  No new series on this page.")
        else:
            print(f"  Found {len(new_series)} new series. Fetching in parallel (max {MAX_WORKERS} workers)...")
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(process_series, s, all_series): s for s in new_series}
                for future in as_completed(futures):
                    s = futures[future]
                    try:
                        success = future.result()
                        if not success:
                            # If failed, we still mark as processed to avoid infinite retry
                            save_progress_immediate(s['id'])
                    except Exception as e:
                        print(f"  ❌ Exception for {s['title']}: {e}")
                        save_progress_immediate(s['id'])

        # Move to next page
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