#!/usr/bin/env python3
"""
update_runtime.py – Convert runtime to integer minutes using multiple sources.
Supports --sources imdbapi,tmdb,omdb (any order) and --category.
Parses existing runtime strings first, then tries API sources.
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from Common import fetch_imdbapi_by_id, OMDB_BASE_URL, OMDB_API_KEY, fetch_runtime_from_tmdb
import requests

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"
PROGRESS_FILE = OUTPUT_DIR / "runtime_update_progress.txt"

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

DELAYS = {
    "imdbapi": 1.0,
    "tmdb": 0.2,
    "omdb": 0.5,
}

def load_progress() -> set:
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

def parse_runtime_string(runtime_str) -> Optional[int]:
    """Parse common runtime formats into minutes. Accepts string or int."""
    if runtime_str is None:
        return None
    # If it's already an integer (minutes), return it directly
    if isinstance(runtime_str, int):
        return runtime_str if runtime_str > 0 else None
    # Convert to string and clean
    runtime_str = str(runtime_str).strip().lower()
    if not runtime_str or runtime_str == "n/a":
        return None
    # Hours and minutes: "2h 30min", "2h30m", "2 hours 30 minutes"
    match = re.search(r'(\d+)\s*h(?:ours?)?\s*(?:(\d+)\s*m(?:in)?)?', runtime_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours * 60 + minutes
    # Only minutes: "150 min", "150m"
    match = re.search(r'(\d+)\s*m(?:in)?', runtime_str)
    if match:
        return int(match.group(1))
    # HH:MM:SS format
    match = re.search(r'(\d{2}):(\d{2}):(\d{2})', runtime_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        return hours * 60 + minutes
    # Arabic: "2س 30د" or "150د"
    match = re.search(r'(\d+)\s*س\s*(?:(\d+)\s*د)?', runtime_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours * 60 + minutes
    match = re.search(r'(\d+)\s*د', runtime_str)
    if match:
        return int(match.group(1))
    return None

def fetch_runtime_imdbapi(imdb_id: str) -> Optional[int]:
    """Fetch runtime from IMDbAPI using /titles/{id}."""
    url = f"https://api.imdbapi.dev/titles/{imdb_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            runtime_seconds = data.get("runtimeSeconds")
            if runtime_seconds:
                return runtime_seconds // 60
    except Exception as e:
        print(f"  IMDbAPI error for {imdb_id}: {e}")
    return None

def fetch_runtime_omdb(imdb_id: str) -> Optional[int]:
    """Fallback to OMDb."""
    url = f"{OMDB_BASE_URL}?i={imdb_id}&apikey={OMDB_API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('Response') == 'True':
            runtime_str = data.get('Runtime', '')
            return parse_runtime_string(runtime_str)
    except Exception as e:
        print(f"  OMDb error for {imdb_id}: {e}")
    return None

def fetch_runtime_tmdb(imdb_id: str) -> Optional[int]:
    """Fetch runtime from TMDb via Common helper."""
    return fetch_runtime_from_tmdb(imdb_id)

def process_file(file_path: Path, content_type: str, processed_set: set, sources: list):
    print(f"\n[FILE] Processing {file_path.name} (sources: {sources})")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ERROR: Cannot load {file_path}: {e}")
        return

    if not isinstance(data, dict):
        print("  WARNING: Not a dictionary, skipping.")
        return

    modified = False
    for content_id, item in data.items():
        if not isinstance(item, dict):
            continue
        if (file_path.name, content_id) in processed_set:
            continue

        # Skip if already has runtime_minutes
        if "runtime_minutes" in item and item["runtime_minutes"] is not None:
            print(f"  SKIP {content_id}: already has runtime_minutes={item['runtime_minutes']}")
            save_progress(file_path.name, content_id)
            continue

        # Get IMDb ID from rating file
        rating_file = RATINGS_DIR / file_path.stem.split('.')[0] / f"{content_id}.json"
        imdb_id = None
        if rating_file.exists():
            try:
                with open(rating_file, "r") as rf:
                    rating_data = json.load(rf)
                    imdb_id = rating_data.get("imdb_id")
            except:
                pass

        runtime_minutes = None

        # First try to parse existing runtime string (if any) – local, no API
        existing_runtime = item.get("Runtime") or item.get("runtime") or item.get("EpisodeDuration")
        if existing_runtime:
            runtime_minutes = parse_runtime_string(existing_runtime)
            if runtime_minutes:
                print(f"  PARSED {content_id}: '{existing_runtime}' -> {runtime_minutes} min")

        # If not parsed and we have IMDb ID, try each source in order
        if not runtime_minutes and imdb_id and imdb_id.startswith("tt"):
            for src in sources:
                if src == "imdbapi":
                    runtime_minutes = fetch_runtime_imdbapi(imdb_id)
                elif src == "tmdb":
                    runtime_minutes = fetch_runtime_tmdb(imdb_id)
                elif src == "omdb":
                    runtime_minutes = fetch_runtime_omdb(imdb_id)
                else:
                    continue
                if runtime_minutes:
                    print(f"  FETCHED {content_id}: from {src} -> {runtime_minutes} min")
                    break
                time.sleep(DELAYS.get(src, 1.0))
            if not runtime_minutes:
                print(f"  FAILED {content_id}: no runtime from sources {sources}")

        if runtime_minutes:
            item["runtime_minutes"] = runtime_minutes
            modified = True
        else:
            print(f"  SKIP {content_id}: no runtime available")
        save_progress(file_path.name, content_id)

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  UPDATED {file_path.name}")

def main():
    parser = argparse.ArgumentParser(description="Update runtime (convert to minutes) using multiple sources")
    parser.add_argument("--sources", type=str, default="imdbapi,tmdb,omdb",
                        help="Comma-separated sources in priority order (imdbapi, tmdb, omdb). Default: imdbapi,tmdb,omdb")
    parser.add_argument("--category", type=str, help="Process only a specific category file (e.g., movies.json)")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",")]
    valid = {"imdbapi", "tmdb", "omdb"}
    for s in sources:
        if s not in valid:
            print(f"ERROR: Invalid source '{s}'. Choose from {valid}")
            sys.exit(1)

    print(f"Starting runtime update with sources: {sources}")
    processed = load_progress()

    for filename, media_type in CONTENT_FILES.items():
        if args.category and filename != args.category:
            continue
        file_path = OUTPUT_DIR / filename
        if file_path.exists():
            process_file(file_path, media_type, processed, sources)
        else:
            print(f"WARNING: {filename} not found, skipping.")

    print("\nDone.")

if __name__ == "__main__":
    main()