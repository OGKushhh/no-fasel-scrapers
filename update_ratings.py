#!/usr/bin/env python3
"""
update_ratings.py – Multi‑source rating fetcher with clear logging.
Supports:
  --primary tmdb      (TMDb, unlimited, ~25/sec)
  --primary imdbapi   (IMDbAPI.dev, set delay to avoid 429)
  --fallback          (use OMDb if primary fails, daily limit 1000)
Output: ./output/ratings/{category}/{id}.json (includes imdb_id if found)
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
from Common import get_tmdb_details, get_imdb_details, search_imdbapi_dev, get_tmdb_imdb_id

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
PROGRESS_FILE = OUTPUT_DIR / "rating_update_progress.txt"
TMDB_DELAY = 0.04               # 25 requests per second
IMDBAPI_DELAY = 3.0             # seconds between IMDbAPI calls to avoid 429
OMDB_DELAY = 0.5                # OMDb is slower but has daily limit anyway
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

def get_rating_and_votes_tmdb(cleaned: str, year: Optional[str], content_type: str) -> tuple:
    """Return (rating, votes, imdb_id) from TMDb."""
    cache_key = f"{cleaned}|{year}|{content_type}"
    if cache_key in tmdb_cache:
        rating, votes, imdb_id = tmdb_cache[cache_key]
        if rating is not None:
            print(f"  [TMDb CACHE] '{cleaned}' -> rating={rating}, votes={votes}, imdb_id={imdb_id}")
            return rating, votes, imdb_id
    rating, votes = get_tmdb_details(cleaned, year, content_type)
    imdb_id = get_tmdb_imdb_id(cleaned, year, content_type)
    tmdb_cache[cache_key] = (rating, votes, imdb_id)
    if rating is not None:
        print(f"  [TMDb] '{cleaned}' -> rating={rating}, votes={votes}, imdb_id={imdb_id}")
    else:
        print(f"  [TMDb] No rating found for '{cleaned}'")
    return rating, votes, imdb_id

def get_rating_and_votes_imdbapi(cleaned: str, year: Optional[str]) -> tuple:
    """Return (rating, votes, imdb_id) from IMDbAPI.dev with delay."""
    global imdbapi_cache
    cache_key = f"{cleaned}|{year}"
    if cache_key in imdbapi_cache:
        rating, votes, imdb_id = imdbapi_cache[cache_key]
        if rating is not None:
            print(f"  [IMDbAPI CACHE] '{cleaned}' -> rating={rating}, votes={votes}, imdb_id={imdb_id}")
            return rating, votes, imdb_id
    # Respect rate limit: wait before calling
    time.sleep(IMDBAPI_DELAY)
    rating, votes, imdb_id = search_imdbapi_dev(cleaned, year)
    imdbapi_cache[cache_key] = (rating, votes, imdb_id)
    if rating is not None:
        print(f"  [IMDbAPI] '{cleaned}' -> rating={rating}, votes={votes}, imdb_id={imdb_id}")
    else:
        print(f"  [IMDbAPI] No rating found for '{cleaned}'")
    return rating, votes, imdb_id

def get_rating_and_votes_omdb(cleaned: str, year: Optional[str], content_type: str) -> tuple:
    """Return (rating, votes, imdb_id) from OMDb (fallback)."""
    global omdb_calls_today
    if omdb_calls_today >= OMDB_DAILY_LIMIT:
        print(f"  [OMDb] Daily limit reached ({omdb_calls_today}) – skipping.")
        return None, 0, None
    time.sleep(OMDB_DELAY)
    rating, votes, imdb_id, limit_reached = get_imdb_details(cleaned, year, content_type, known_imdb_id=None)
    omdb_calls_today += 1
    if limit_reached:
        print(f"  [OMDb] API limit reached – stopping further OMDb calls.")
        sys.exit(1)
    if rating is not None:
        print(f"  [OMDb] '{cleaned}' -> rating={rating}, votes={votes}, imdb_id={imdb_id}")
    else:
        print(f"  [OMDb] No rating found for '{cleaned}'")
    return rating, votes, imdb_id

def process_file(file_path: Path, content_type: str, processed_set: Set[Tuple[str, str]], args):
    print(f"\n[FILE] Processing {file_path.name} (type: {content_type})")
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

        # If a valid rating already exists (numeric), skip this item
        if rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    existing = json.load(rf)
                existing_rating = existing.get("rating")
                if existing_rating not in (None, "N/A"):
                    print(f"  SKIP {content_id}: already rated {existing_rating} (source: {existing.get('source')})")
                    save_progress(file_path.name, content_id)
                    continue
                else:
                    print(f"  UPDATE {content_id}: existing rating is null, re-fetching...")
            except:
                pass

        cleaned = clean_title(title)

        # Skip future years – no ratings exist
        if year and int(year) > CURRENT_YEAR:
            print(f"  SKIP {content_id}: future year {year}, no rating available")
            # Do NOT save progress; item will be retried later (but it will always be future, so maybe skip permanently)
            # However, we can mark progress to avoid re-checking every time. For future years, it's fine to mark as done.
            save_progress(file_path.name, content_id)
            continue

        rating = None
        votes = 0
        imdb_id = None
        source = None

        # Primary source
        if args.primary == "tmdb":
            rating, votes, imdb_id = get_rating_and_votes_tmdb(cleaned, year, content_type)
            source = "tmdb"
        elif args.primary == "imdbapi":
            rating, votes, imdb_id = get_rating_and_votes_imdbapi(cleaned, year)
            source = "imdbapi"
        else:
            raise ValueError(f"Unknown primary source: {args.primary}")

        # Fallback to OMDb if primary failed and fallback enabled
        if args.fallback and rating is None:
            print(f"  FALLBACK: Primary {args.primary} failed, trying OMDb...")
            rating, votes, imdb_id = get_rating_and_votes_omdb(cleaned, year, content_type)
            if rating is not None:
                source = "omdb"

        # If still no rating, skip saving and do NOT mark progress
        if rating is None:
            print(f"  FAILED {content_id}: no rating found from any source. Will retry later.")
            continue   # no file saved, no progress mark

        # We have a valid rating – save it
        rating_data = {
            "content_id": content_id,
            "title": title,
            "year": year,
            "rating": rating,
            "votes": votes,
            "source": source,
            "imdb_id": imdb_id,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(rating_data, f, indent=2, ensure_ascii=False)
        print(f"  SUCCESS {content_id}: rating={rating}, votes={votes}, source={source}")

        save_progress(file_path.name, content_id)
        time.sleep(0.1)   # tiny filesystem delay

def main():
    parser = argparse.ArgumentParser(description="Update ratings for all content")
    parser.add_argument("--primary", choices=["tmdb", "imdbapi"], default="tmdb",
                        help="Primary rating source (default: tmdb)")
    parser.add_argument("--fallback", action="store_true",
                        help="Use OMDb as fallback when primary fails (daily limit 1000)")
    args = parser.parse_args()

    print(f"Starting rating update: primary={args.primary}, fallback={args.fallback}")
    load_caches()
    processed = load_progress()

    for filename, media_type in CONTENT_FILES.items():
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            process_file(file_path, media_type, processed, args)
        else:
            print(f"WARNING: {filename} not found, skipping.")

    save_caches()
    print(f"\nFinished. OMDb calls used today: {omdb_calls_today} / {OMDB_DAILY_LIMIT}")

if __name__ == "__main__":
    main()