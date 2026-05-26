#!/usr/bin/env python3
"""
update_ratings.py – Flexible rating fetcher.
If an IMDb ID exists in the rating file, it directly fetches from IMDbAPI (upgrade).
Otherwise uses the source order (--sources).
Supports --category to process only one JSON file.
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from Common import (
    get_tmdb_details, get_imdb_details, search_imdbapi_dev, get_tmdb_imdb_id,
    fetch_imdbapi_by_id
)

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
PROGRESS_FILE = OUTPUT_DIR / "rating_update_progress.txt"

# Delays (seconds) per source
DELAYS = {
    "imdbapi": 1.5,
    "tmdb": 0.04,
    "omdb": 0.5,
}
OMDB_DAILY_LIMIT = 1000
CURRENT_YEAR = datetime.now().year

CONTENT_FILES = {
    "movies.json": "movie",
    "dubbed-movies.json": "movie",
    "hindi.json": "movie",
    "asian-movies.json": "movie",
    "anime-movies.json": "movie",
    "anime.json": "tv",
    "series.json": "tv",
    "tvshows.json": "tv",
    "asian-series.json": "tv",
}

tmdb_cache: Dict[str, tuple] = {}
imdbapi_cache: Dict[str, tuple] = {}
omdb_calls_today = 0

def load_caches():
    global tmdb_cache, imdbapi_cache
    cache_dir = RATINGS_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmdb_cache_file = cache_dir / "tmdb_cache.json"
    if tmdb_cache_file.exists():
        with open(tmdb_cache_file, "r") as f:
            tmdb_cache = {k: tuple(v) for k, v in json.load(f).items()}
        print(f"[INFO] Loaded {len(tmdb_cache)} TMDb cache entries.")
    imdbapi_cache_file = cache_dir / "imdbapi_cache.json"
    if imdbapi_cache_file.exists():
        with open(imdbapi_cache_file, "r") as f:
            imdbapi_cache = {k: tuple(v) for k, v in json.load(f).items()}
        print(f"[INFO] Loaded {len(imdbapi_cache)} IMDbAPI cache entries.")

def save_caches():
    serializable_tmdb = {k: list(v) for k, v in tmdb_cache.items()}
    with open(RATINGS_DIR / "tmdb_cache.json", "w") as f:
        json.dump(serializable_tmdb, f, indent=2)
    serializable_imdbapi = {k: list(v) for k, v in imdbapi_cache.items()}
    with open(RATINGS_DIR / "imdbapi_cache.json", "w") as f:
        json.dump(serializable_imdbapi, f, indent=2)

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
    return processed

def save_progress(category: str, content_id: str):
    with open(PROGRESS_FILE, "a") as f:
        f.write(f"{category}|{content_id}\n")

def clean_title(raw_title: str) -> str:
    arabic_stop = ["فيلم", "مسلسل", "مترجم", "اون لاين", "اونلاين", "مدبلج", "الحلقة", "الفيلم"]
    cleaned = raw_title
    for word in arabic_stop:
        cleaned = re.sub(rf'\b{word}\b', '', cleaned, flags=re.IGNORECASE)
    # Keep letters, numbers, spaces, colon, apostrophe, dot, dash, and comma
    cleaned = re.sub(r'[^A-Za-z0-9\s:\'\.\-,]', ' ', cleaned)
    cleaned = ' '.join(cleaned.split())
    return cleaned if cleaned else raw_title

def extract_year(title: str, release_date: Optional[str]) -> Optional[str]:
    if release_date:
        m = re.search(r'\b(19|20)\d{2}\b', release_date)
        if m:
            return m.group(0)
    m = re.search(r'\b(19|20)\d{2}\b', title)
    return m.group(0) if m else None

# ---- Source functions ----
def fetch_tmdb(cleaned: str, year: Optional[str], content_type: str) -> tuple:
    cache_key = f"{cleaned}|{year}|{content_type}"
    if cache_key in tmdb_cache:
        rating, votes, imdb_id = tmdb_cache[cache_key]
        if rating is not None:
            print(f"  [TMDb CACHE] '{cleaned}' -> rating={rating}, votes={votes}")
            return rating, votes, imdb_id, "tmdb"
    rating, votes = get_tmdb_details(cleaned, year, content_type)
    imdb_id = get_tmdb_imdb_id(cleaned, year, content_type)
    tmdb_cache[cache_key] = (rating, votes, imdb_id)
    if rating is not None:
        print(f"  [TMDb] '{cleaned}' -> rating={rating}, votes={votes}")
    else:
        print(f"  [TMDb] No rating found for '{cleaned}'")
    return rating, votes, imdb_id, "tmdb"

def fetch_imdbapi(cleaned: str, year: Optional[str]) -> tuple:
    cache_key = f"{cleaned}|{year}"
    if cache_key in imdbapi_cache:
        rating, votes, imdb_id = imdbapi_cache[cache_key]
        if rating is not None:
            print(f"  [IMDbAPI CACHE] '{cleaned}' -> rating={rating}, votes={votes}")
            return rating, votes, imdb_id, "imdbapi"
    time.sleep(DELAYS["imdbapi"])
    rating, votes, imdb_id = search_imdbapi_dev(cleaned, year)
    imdbapi_cache[cache_key] = (rating, votes, imdb_id)
    if rating is not None:
        print(f"  [IMDbAPI] '{cleaned}' -> rating={rating}, votes={votes}")
    else:
        print(f"  [IMDbAPI] No rating found for '{cleaned}'")
    return rating, votes, imdb_id, "imdbapi"

def fetch_omdb(cleaned: str, year: Optional[str], content_type: str) -> tuple:
    global omdb_calls_today
    if omdb_calls_today >= OMDB_DAILY_LIMIT:
        print(f"  [OMDb] Daily limit reached ({omdb_calls_today}) – skipping.")
        return None, 0, None, "omdb"
    time.sleep(DELAYS["omdb"])
    rating, votes, imdb_id, limit_reached = get_imdb_details(cleaned, year, content_type, known_imdb_id=None)
    omdb_calls_today += 1
    if limit_reached:
        print(f"  [OMDb] API limit reached – stopping further OMDb calls.")
        sys.exit(1)
    if rating is not None:
        print(f"  [OMDb] '{cleaned}' -> rating={rating}, votes={votes}")
    else:
        print(f"  [OMDb] No rating found for '{cleaned}'")
    return rating, votes, imdb_id, "omdb"

def get_rating_from_sources(cleaned: str, year: Optional[str], content_type: str, sources: list) -> tuple:
    for src in sources:
        if src == "imdbapi":
            rating, votes, imdb_id, used = fetch_imdbapi(cleaned, year)
        elif src == "tmdb":
            rating, votes, imdb_id, used = fetch_tmdb(cleaned, year, content_type)
        elif src == "omdb":
            rating, votes, imdb_id, used = fetch_omdb(cleaned, year, content_type)
        else:
            raise ValueError(f"Unknown source: {src}")
        if rating is not None:
            return rating, votes, imdb_id, used
        time.sleep(0.5)
    return None, 0, None, "none"

def process_file(file_path: Path, content_type: str, processed_set: Set[Tuple[str, str]], sources: list):
    print(f"\n[FILE] Processing {file_path.name} (type: {content_type}) - sources: {sources}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ERROR: Cannot load {file_path}: {e}")
        return

    if not isinstance(data, dict):
        print("  WARNING: Not a dictionary, skipping.")
        return

    rating_dir = RATINGS_DIR / file_path.stem.split('.')[0]
    rating_dir.mkdir(parents=True, exist_ok=True)

    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue
        if (file_path.name, content_id) in processed_set:
            continue

        title = item.get("Title")
        if not title:
            save_progress(file_path.name, content_id)
            continue

        year = extract_year(title, item.get("ReleaseDate"))
        rating_file = rating_dir / f"{content_id}.json"

        # Load existing rating file (if any)
        existing_imdb_id = None
        existing_source = None
        existing_rating = None
        if rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    existing = json.load(rf)
                existing_rating = existing.get("rating")
                existing_source = existing.get("source")
                existing_imdb_id = existing.get("imdb_id")
            except:
                pass

        # If we already have a rating and it's from IMDbAPI, skip
        if existing_rating is not None and existing_rating not in (None, "N/A") and existing_source == "imdbapi":
            print(f"  SKIP {content_id}: already rated from IMDbAPI ({existing_rating})")
            save_progress(file_path.name, content_id)
            continue

        # If we have an IMDb ID, use it directly (upgrade path)
        if existing_imdb_id and existing_imdb_id.startswith("tt"):
            print(f"  [UPGRADE] {content_id}: using stored IMDb ID {existing_imdb_id} to fetch IMDb rating")
            rating, votes = fetch_imdbapi_by_id(existing_imdb_id)
            if rating is not None:
                rating_data = {
                    "content_id": content_id,
                    "title": title,
                    "year": year,
                    "rating": rating,
                    "votes": votes,
                    "source": "imdbapi",
                    "imdb_id": existing_imdb_id,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                with open(rating_file, "w", encoding="utf-8") as f:
                    json.dump(rating_data, f, indent=2, ensure_ascii=False)
                print(f"  SUCCESS (upgraded) {content_id}: rating={rating}, votes={votes}, source=imdbapi")
                save_progress(file_path.name, content_id)
                continue
            else:
                print(f"  [UPGRADE] Failed to fetch from IMDb ID {existing_imdb_id}, falling back to sources")

        # If we already have a numeric rating from other source (tmdb/omdb) but no IMDb ID, we could skip? We'll let sources run.
        # But we skip if rating exists and is not null (unless we want to upgrade? The upgrade already handled above if ID existed).
        if existing_rating is not None and existing_rating not in (None, "N/A"):
            print(f"  SKIP {content_id}: already rated {existing_rating} (source: {existing_source}) – no IMDb ID to upgrade")
            save_progress(file_path.name, content_id)
            continue

        cleaned = clean_title(title)

        if year and int(year) > CURRENT_YEAR:
            print(f"  SKIP {content_id}: future year {year}")
            save_progress(file_path.name, content_id)
            continue

        rating, votes, imdb_id, source_used = get_rating_from_sources(cleaned, year, content_type, sources)

        if rating is None:
            print(f"  FAILED {content_id}: no rating from any source")
            continue

        rating_data = {
            "content_id": content_id,
            "title": title,
            "year": year,
            "rating": rating,
            "votes": votes,
            "source": source_used,
            "imdb_id": imdb_id,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(rating_data, f, indent=2, ensure_ascii=False)
        print(f"  SUCCESS {content_id}: rating={rating}, votes={votes}, source={source_used}")

        save_progress(file_path.name, content_id)
        time.sleep(0.2)

def main():
    parser = argparse.ArgumentParser(description="Flexible rating fetcher")
    parser.add_argument("--sources", type=str, default="imdbapi,tmdb,omdb",
                        help="Comma-separated list of sources (imdbapi,tmdb,omdb). Default: imdbapi,tmdb,omdb")
    parser.add_argument("--category", type=str, help="Process only a specific category file (e.g., movies.json)")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",")]
    valid_sources = {"imdbapi", "tmdb", "omdb"}
    for s in sources:
        if s not in valid_sources:
            print(f"ERROR: Invalid source '{s}'. Choose from {valid_sources}")
            sys.exit(1)

    print(f"Starting rating update with source order: {sources}")
    load_caches()
    processed = load_progress()

    for filename, media_type in CONTENT_FILES.items():
        if args.category and filename != args.category:
            continue
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            process_file(file_path, media_type, processed, sources)
        else:
            print(f"WARNING: {filename} not found, skipping.")

    save_caches()
    print(f"\nFinished. OMDb calls used today: {omdb_calls_today} / {OMDB_DAILY_LIMIT}")

if __name__ == "__main__":
    main()