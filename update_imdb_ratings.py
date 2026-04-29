#!/usr/bin/env python3
"""
update_imdb_ratings.py

Reads all content JSON files (movies, anime, series, etc.),
fetches IMDb ratings from OMDb API (using cleaned title + year),
and writes each rating to a separate JSON file in ./output/ratings/{category}/{id}.json

Does NOT modify the original content JSONs.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Common import get_imdb_rating

# ========== CONFIG ==========
OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
DAILY_LIMIT = 1000
REQUEST_SAFETY_MARGIN = 10
PROGRESS_FILE = OUTPUT_DIR / "rating_update_progress.txt"

# Files to process (map filename -> category folder name)
CONTENT_FILES = {
    "movies.json": "movies",
    "anime.json": "anime",
    "series.json": "series",
    "tvshows.json": "tvshows",
    "asian-series.json": "asian-series",
    "anime-movies.json": "anime-movies",
}
# ============================

api_calls_made = 0
cache: Dict[str, Optional[str]] = {}  # key -> rating or None

def load_cache():
    global cache
    cache_file = RATINGS_DIR / "omdb_cache.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"Loaded {len(cache)} cached OMDb results.")
        except:
            cache = {}

def save_cache():
    cache_file = RATINGS_DIR / "omdb_cache.json"
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def load_progress() -> Set[Tuple[str, str]]:
    processed = set()
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        processed.add((parts[0], parts[1]))
    return processed

def save_progress(category: str, content_id: str):
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{category}|{content_id}\n")

def extract_english_title(raw_title: str) -> str:
    """Convert 'فيلم Ambulance 2022 مترجم' -> 'Ambulance'."""
    words = re.findall(r'[A-Za-z][A-Za-z0-9]*', raw_title)
    for w in words:
        if not (len(w) == 4 and w.isdigit()):
            return w
    return words[0] if words else raw_title.strip()

def extract_year_from_release_date(release_date: Any) -> Optional[str]:
    if not release_date or not isinstance(release_date, str):
        return None
    match = re.search(r'\b(19|20)\d{2}\b', release_date)
    return match.group(0) if match else None

def get_rating_for_item(category: str, content_id: str, title: str, release_date: Any, content_type: str) -> Optional[str]:
    global api_calls_made

    year = extract_year_from_release_date(release_date)
    clean_title = extract_english_title(title)
    cache_key = f"{clean_title}|{year}|{content_type}"

    if cache_key in cache:
        return cache[cache_key]

    if api_calls_made + REQUEST_SAFETY_MARGIN >= DAILY_LIMIT:
        print(f"⚠️ Daily limit approaching ({api_calls_made} calls). Stopping.")
        sys.exit(0)

    try:
        rating = get_imdb_rating(clean_title, year, content_type, known_imdb_id=None)
        api_calls_made += 1
        print(f"  🔵 {category}/{content_id}: '{clean_title}' -> {rating} (call #{api_calls_made})")
        cache[cache_key] = rating
        return rating
    except Exception as e:
        print(f"  ❌ Error for {clean_title}: {e}")
        cache[cache_key] = None
        return None

def process_file(file_path: Path, category: str, processed_set: Set[Tuple[str, str]]):
    global api_calls_made

    print(f"\n📁 Processing {file_path.name} (category: {category})")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Cannot load: {e}")
        return

    if not isinstance(data, dict):
        print(f"  ⚠️ Not a dictionary, skipping.")
        return

    rating_category_dir = RATINGS_DIR / category
    rating_category_dir.mkdir(parents=True, exist_ok=True)

    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue
        if (category, content_id) in processed_set:
            continue

        title = item.get("Title")
        if not title:
            save_progress(category, content_id)
            continue

        release_date = item.get("ReleaseDate")
        # Determine content type for OMDb: movie or series
        content_type = "movie"
        if "series" in category or "anime" in category:
            # For anime, check if it's a movie or series (use 'Type' field if present)
            if item.get("Type") == "Movie":
                content_type = "movie"
            else:
                content_type = "series"

        rating = get_rating_for_item(category, content_id, title, release_date, content_type)

        # Write rating file
        rating_file = rating_category_dir / f"{content_id}.json"
        rating_data = {
            "content_id": content_id,
            "title": title,
            "year": extract_year_from_release_date(release_date),
            "rating": rating,
            "source": "omdb",
            "last_updated": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
        }
        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(rating_data, f, indent=2, ensure_ascii=False)

        save_progress(category, content_id)

    # Save cache periodically
    if api_calls_made % 20 == 0:
        save_cache()

def main():
    load_cache()
    processed = load_progress()

    for filename, category in CONTENT_FILES.items():
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            process_file(file_path, category, processed)
        else:
            print(f"⚠️ {filename} not found, skipping.")

    save_cache()
    print(f"\n✅ Done. Total API calls: {api_calls_made}")
    if api_calls_made + REQUEST_SAFETY_MARGIN >= DAILY_LIMIT:
        print("⚠️ Approached daily limit. Run again tomorrow for remaining items.")

if __name__ == "__main__":
    main()