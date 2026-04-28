# backfill_descriptions_resumable.py
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from Common import get_website_safe, extract_description, REQUEST_DELAY
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
JSON_FILE = "./output/movies.json"          # change to series.json, anime.json, etc.
PROGRESS_FILE = "./output/backfill_progress.txt"
MAX_WORKERS = 6
SAVE_INTERVAL = 50                          # save after every N successful updates
REQUEST_DELAY_BATCH = 2                     # seconds to wait between batches (optional)
# ----------------------------------------------------------------------

def load_progress():
    """Return the last processed item index (0-indexed) from progress file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except:
                return 0
    return 0

def save_progress(index):
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(index))

def fetch_description(item_id, detail_url=None):
    """Fetch description for a single item using its ID or URL."""
    if not detail_url:
        detail_url = f"https://www.fasel-hd.cam/?p={item_id}"
    resp = get_website_safe(detail_url)
    if resp and resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        return extract_description(soup)
    return ""

def backfill_descriptions(json_file, progress_file, max_workers=8, save_interval=50):
    # Load existing data
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Get list of items (id, data)
    items = list(data.items())
    total = len(items)
    
    start_index = load_progress()
    print(f"Resuming from index {start_index} / {total}")
    
    updated_count = 0
    lock = Lock()
    
    # Process items in batches to allow progress saving
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i in range(start_index, total, max_workers):
            batch = items[i:i+max_workers]
            futures = {}
            for idx, (item_id, item_data) in enumerate(batch, start=i):
                # Skip if already has description
                if item_data.get("Description"):
                    continue
                future = executor.submit(fetch_description, item_id)
                futures[future] = (idx, item_id, item_data)
            
            # Process completed futures
            for future in as_completed(futures):
                idx, item_id, item_data = futures[future]
                desc = future.result()
                with lock:
                    if desc:
                        item_data["Description"] = desc
                        updated_count += 1
                        print(f"[{idx+1}/{total}] ✅ Added description for {item_id} ({len(desc)} chars)")
                    else:
                        item_data["Description"] = ""
                        print(f"[{idx+1}/{total}] ⚠️ No description for {item_id}")
                    
                    # Save progress after each item or after save_interval updates
                    save_progress(idx + 1)  # next index to process
                    
                    # Save the whole JSON periodically
                    if updated_count % save_interval == 0:
                        with open(json_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4, ensure_ascii=False)
                        print(f"  💾 Saved progress (updated {updated_count} items)")
            
            # Small delay between batches to be polite
            time.sleep(REQUEST_DELAY_BATCH)
    
    # Final save
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    
    # Clear progress file when done
    if os.path.exists(progress_file):
        os.remove(progress_file)
    
    print(f"\n✅ Finished. Updated {updated_count} items out of {total}.")

if __name__ == "__main__":
    # For movies.json
    backfill_descriptions(
        json_file="./output/movies.json",
        progress_file="./output/backfill_movies_progress.txt",
        max_workers=8,
        save_interval=50
    )
    
    # Uncomment to run for other files
    # backfill_descriptions("./output/series.json", "./output/backfill_series_progress.txt", 8, 50)
    # backfill_descriptions("./output/tvshows.json", "./output/backfill_tvshows_progress.txt", 8, 50)
    # backfill_descriptions("./output/asian-series.json", "./output/backfill_asian_progress.txt", 8, 50)
    # backfill_descriptions("./output/anime.json", "./output/backfill_anime_progress.txt", 8, 50)