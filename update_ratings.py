#!/usr/bin/env python3
"""
update_ratings.py - Fetch IMDb ratings and votes, maintain mapping, resumable.
Exits gracefully when daily API limit is reached (no null writes for skipped items).
"""

import sys
import json
import re
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from datetime import datetime, timezone

print("🚀 Starting update_ratings.py...", flush=True)

sys.path.insert(0, str(Path(__file__).parent))
from Common import get_imdb_details

print("✅ Imports complete", flush=True)

# ========== CONFIG ==========
OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
MAP_FILE = OUTPUT_DIR / "imdb_id_map.json"
PROGRESS_FILE = OUTPUT_DIR / "rating_update_progress.txt"
DAILY_LIMIT = 1000
REQUEST_SAFETY_MARGIN = 10

CONTENT_FILES = {
    "movies.json": "movies",
    "dubbed-movies.json": "movies",
    "hindi.json": "movies",
    "asian-movies.json": "movies",
    "anime-movies.json": "movies",
    "anime.json": "anime",
    "series.json": "series",
    "tvshows.json": "tvshows",
    "asian-series.json": "asian-series",
}
# ============================

api_calls_made = 0
cache: Dict[str, dict] = {}
imdb_map: Dict[str, str] = {}

def load_cache():
    global cache
    cache_file = RATINGS_DIR / "omdb_cache.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
            print(f"📦 Loaded {len(cache)} OMDb cache entries.", flush=True)
        except Exception as e:
            print(f"⚠️ Failed to load cache: {e}", flush=True)

def save_cache():
    cache_file = RATINGS_DIR / "omdb_cache.json"
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"💾 Saved cache ({len(cache)} entries).", flush=True)

def load_imdb_map():
    global imdb_map
    if MAP_FILE.exists():
        try:
            with open(MAP_FILE, "r") as f:
                imdb_map = json.load(f)
            print(f"🗺️ Loaded {len(imdb_map)} IMDb ID mappings.", flush=True)
        except Exception as e:
            print(f"⚠️ Failed to load map: {e}", flush=True)

def save_imdb_map():
    with open(MAP_FILE, "w") as f:
        json.dump(imdb_map, f, indent=2)
    print(f"💾 Saved {len(imdb_map)} mappings.", flush=True)

def load_progress() -> Set[Tuple[str, str]]:
    processed = set()
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        processed.add((parts[0], parts[1]))
    print(f"📋 Loaded {len(processed)} progress entries.", flush=True)
    return processed

def save_progress(category: str, content_id: str):
    with open(PROGRESS_FILE, "a") as f:
        f.write(f"{category}|{content_id}\n")

def clean_title(raw_title: str) -> str:
    arabic_stop = ["فيلم", "مسلسل", "مترجم", "اون لاين", "اونلاين", "مدبلج", "الحلقة", "الفيلم"]
    cleaned = raw_title
    for word in arabic_stop:
        cleaned = re.sub(rf'\b{word}\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[^A-Za-z0-9\s:\'\.-]', ' ', cleaned)
    cleaned = ' '.join(cleaned.split())
    return cleaned if cleaned else raw_title

def extract_year(title: str, release_date: Optional[str]) -> Optional[str]:
    if release_date:
        m = re.search(r'\b(19|20)\d{2}\b', release_date)
        if m:
            return m.group(0)
    m = re.search(r'\b(19|20)\d{2}\b', title)
    return m.group(0) if m else None

def get_rating_and_votes(category: str, content_id: str, title: str, year: Optional[str], content_type: str) -> tuple:
    global api_calls_made
    cleaned = clean_title(title)
    cache_key = f"{cleaned}|{year}|{content_type}"
    if cache_key in cache:
        rating = cache[cache_key].get("rating")
        votes = cache[cache_key].get("votes")
        print(f"  📦 Cache hit: {cleaned} -> rating={rating}", flush=True)
        return rating, votes

    # Check daily limit BEFORE making API call
    if api_calls_made >= DAILY_LIMIT:
        print(f"\n🔴 DAILY API LIMIT REACHED ({api_calls_made} calls). Stopping. No further ratings will be fetched.", flush=True)
        sys.exit(0)
    if api_calls_made + REQUEST_SAFETY_MARGIN >= DAILY_LIMIT:
        print(f"⚠️ Approaching daily limit ({api_calls_made}/{DAILY_LIMIT}) – will stop soon.", flush=True)

    known_id = imdb_map.get(content_id)
    # get_imdb_details now returns (rating, votes, imdb_id, limit_reached)
    rating, votes, found_id, limit_reached = get_imdb_details(cleaned, year, content_type, known_imdb_id=known_id)
    api_calls_made += 1

    if limit_reached:
        print("   🛑 API limit error from OMDb. Stopping immediately.", flush=True)
        sys.exit(0)

    print(f"  🌐 API #{api_calls_made}: {cleaned} ({year}) -> rating={rating}, votes={votes}, id={found_id}", flush=True)

    if found_id and found_id != known_id:
        imdb_map[content_id] = found_id
        save_imdb_map()
        print(f"  🆕 Mapped {content_id} -> {found_id}", flush=True)

    cache[cache_key] = {"rating": rating, "votes": votes}
    return rating, votes

def process_file(file_path: Path, category: str, processed_set: Set[Tuple[str, str]]):
    print(f"\n📁 Processing {file_path.name} (category: {category})", flush=True)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Cannot load: {e}", flush=True)
        return

    if not isinstance(data, dict):
        print("  ⚠️ Not a dictionary, skipping.", flush=True)
        return

    rating_dir = RATINGS_DIR / category
    rating_dir.mkdir(parents=True, exist_ok=True)

    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue
        if (category, content_id) in processed_set:
            continue

        title = item.get("Title")
        if not title:
            save_progress(category, content_id)
            continue

        content_type = "movie"
        if category in ["anime", "series", "tvshows", "asian-series"]:
            if item.get("Type") == "Movie":
                content_type = "movie"
            else:
                content_type = "series"

        year = extract_year(title, item.get("ReleaseDate"))

        rating_file = rating_dir / f"{content_id}.json"
        if rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    existing = json.load(rf)
                if existing.get("rating") not in (None, "N/A"):
                    print(f"  ⏭️ {category}/{content_id} already rated ({existing['rating']}) – skipping", flush=True)
                    save_progress(category, content_id)
                    continue
                else:
                    print(f"  🔄 {category}/{content_id} existing rating is null, re‑fetching...", flush=True)
            except:
                pass

        rating, votes = get_rating_and_votes(category, content_id, title, year, content_type)

        rating_data = {
            "content_id": content_id,
            "title": title,
            "year": year,
            "rating": rating,
            "votes": votes,
            "source": "omdb",
            "imdb_id": imdb_map.get(content_id),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(rating_data, f, indent=2, ensure_ascii=False)
        print(f"  💾 Saved rating for {category}/{content_id}", flush=True)

        save_progress(category, content_id)

        if api_calls_made % 20 == 0:
            save_cache()

def main():
    print("🔧 Loading data...", flush=True)
    load_cache()
    load_imdb_map()
    processed = load_progress()

    for filename, category in CONTENT_FILES.items():
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            process_file(file_path, category, processed)
        else:
            print(f"⚠️ {filename} not found, skipping.", flush=True)

    save_cache()
    save_imdb_map()
    print(f"\n✅ Finished. Total API calls: {api_calls_made}", flush=True)
    if api_calls_made >= DAILY_LIMIT:
        print("🔴 Daily limit was reached or exceeded. Some items may still need ratings – run again tomorrow.", flush=True)

if __name__ == "__main__":
    main()