#!/usr/bin/env python3
"""
update_ratings.py – Two‑tier rating fetcher.
Primary:   TMDb (unlimited, ~25 req/sec)
Secondary: OMDb (1000/day, last resort)
Output: ./output/ratings/{category}/{id}.json
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from Common import get_tmdb_details, get_imdb_details

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
PROGRESS_FILE = OUTPUT_DIR / "rating_update_progress.txt"
TMDB_DELAY = 0.04               # 25 requests per second
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
omdb_calls_today = 0

def load_tmdb_cache():
    global tmdb_cache
    cache_file = RATINGS_DIR / "tmdb_cache.json"
    if cache_file.exists():
        with open(cache_file, "r") as f:
            tmdb_cache = {k: tuple(v) for k, v in json.load(f).items()}
        print(f"📦 Loaded {len(tmdb_cache)} TMDb cache entries.")

def save_tmdb_cache():
    cache_file = RATINGS_DIR / "tmdb_cache.json"
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    serializable = {k: list(v) for k, v in tmdb_cache.items()}
    with open(cache_file, "w") as f:
        json.dump(serializable, f, indent=2)

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

def get_rating_and_votes(category: str, content_id: str, title: str, year: Optional[str], content_type: str) -> tuple:
    global omdb_calls_today
    cleaned = clean_title(title)

    # Skip future years – no ratings exist
    if year and int(year) > CURRENT_YEAR:
        print(f"  ⏭️ Future year {year}, skipping API calls.")
        return None, 0, "none"

    # ----- 1. TMDb (primary) -----
    cache_key = f"{cleaned}|{year}|{content_type}"
    if cache_key in tmdb_cache:
        rating, votes = tmdb_cache[cache_key]
        if rating is not None:
            print(f"  📦 TMDb cache: '{cleaned}' -> rating={rating}, votes={votes}")
            return rating, votes, "tmdb"

    rating, votes = get_tmdb_details(cleaned, year, content_type)
    tmdb_cache[cache_key] = (rating, votes)
    if rating is not None:
        print(f"  🎬 TMDb: '{cleaned}' -> rating={rating}, votes={votes}")
        return rating, votes, "tmdb"

    # ----- 2. OMDb fallback (daily limit) -----
    if omdb_calls_today >= OMDB_DAILY_LIMIT:
        print(f"  ⚠️ OMDb daily limit reached ({omdb_calls_today}). Skipping.")
        return None, 0, "none"

    rating, votes, _, limit_reached = get_imdb_details(cleaned, year, content_type, known_imdb_id=None)
    omdb_calls_today += 1
    if limit_reached:
        print(f"  🛑 OMDb limit reached – stopping further OMDb calls.")
        sys.exit(0)
    if rating is not None:
        print(f"  🎬 OMDb: '{cleaned}' -> rating={rating}, votes={votes}")
        return rating, votes, "omdb"

    print(f"  ❌ No rating found for '{cleaned}'.")
    return None, 0, "none"

def process_file(file_path: Path, content_type: str, processed_set: Set[Tuple[str, str]]):
    print(f"\n📁 Processing {file_path.name} (type: {content_type})")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Cannot load: {e}")
        return

    if not isinstance(data, dict):
        print("  ⚠️ Not a dictionary, skipping.")
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
        if rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    existing = json.load(rf)
                if existing.get("rating") not in (None, "N/A"):
                    print(f"  ⏭️ {content_id} already rated ({existing['rating']}) – skipping")
                    save_progress(file_path.name, content_id)
                    continue
                else:
                    print(f"  🔄 {content_id} existing rating is null, re‑fetching...")
            except:
                pass

        rating, votes, source = get_rating_and_votes(file_path.name, content_id, title, year, content_type)

        # ----- SAFEGUARD: preserve existing numeric rating if new lookup returns None -----
        if rating is None and rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    existing = json.load(rf)
                existing_rating = existing.get("rating")
                if existing_rating not in (None, "N/A"):
                    print(f"  🛡️ Preserving existing rating {existing_rating} for {content_id} (new lookup returned None)")
                    save_progress(file_path.name, content_id)
                    continue
            except:
                pass  # If we can't read the file, proceed with writing None

        rating_data = {
            "content_id": content_id,
            "title": title,
            "year": year,
            "rating": rating,
            "votes": votes,
            "source": source,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(rating_data, f, indent=2, ensure_ascii=False)
        print(f"  💾 Saved rating for {content_id} (source: {source})")

        save_progress(file_path.name, content_id)
        time.sleep(TMDB_DELAY)

def main():
    print("🚀 Starting update_ratings.py (TMDb primary, OMDb fallback)")
    load_tmdb_cache()
    processed = load_progress()

    for filename, media_type in CONTENT_FILES.items():
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            process_file(file_path, media_type, processed)
        else:
            print(f"⚠️ {filename} not found, skipping.")

    save_tmdb_cache()
    print(f"\n✅ Finished. OMDb calls used today: {omdb_calls_today} (limit: {OMDB_DAILY_LIMIT})")

if __name__ == "__main__":
    main()