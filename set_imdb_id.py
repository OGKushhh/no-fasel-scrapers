#!/usr/bin/env python3
"""
set_imdb_id.py – Manually set or update IMDb ID for a content item.
Updates the rating file at output/ratings/{category_stem}/{id}.json.
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

OUTPUT_DIR = Path("./output")
RATINGS_DIR = OUTPUT_DIR / "ratings"

def main():
    parser = argparse.ArgumentParser(description="Set IMDb ID for a content item")
    parser.add_argument("--category", required=True, help="Category file name (e.g., movies.json)")
    parser.add_argument("--id", required=True, help="Content ID")
    parser.add_argument("--imdb_id", required=True, help="IMDb ID (e.g., tt1234567)")
    args = parser.parse_args()

    # Validate IMDb ID format
    if not args.imdb_id.startswith("tt") or not args.imdb_id[2:].isdigit():
        print(f"ERROR: Invalid IMDb ID format: {args.imdb_id}. Must start with 'tt' followed by digits.")
        sys.exit(1)

    # Determine rating subfolder (remove .json extension)
    category_stem = Path(args.category).stem
    rating_dir = RATINGS_DIR / category_stem
    rating_dir.mkdir(parents=True, exist_ok=True)

    rating_file = rating_dir / f"{args.id}.json"

    # Load existing data or create new
    if rating_file.exists():
        with open(rating_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "content_id": args.id,
            "title": "Unknown (manual)",
            "year": None,
            "rating": None,
            "votes": 0,
            "source": "manual",
            "imdb_id": args.imdb_id,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        # Try to get title from main JSON if possible
        main_json = OUTPUT_DIR / args.category
        if main_json.exists():
            try:
                with open(main_json, "r", encoding="utf-8") as f:
                    main_data = json.load(f)
                if args.id in main_data:
                    data["title"] = main_data[args.id].get("Title", "Unknown")
                    data["year"] = main_data[args.id].get("ReleaseDate") or None
            except:
                pass
        with open(rating_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Created rating file with IMDb ID {args.imdb_id} for {args.category}/{args.id}")
        return

    # Update existing rating file
    data["imdb_id"] = args.imdb_id
    data["source"] = "manual"
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    # Optionally keep existing rating; set to None to force refetch
    # data["rating"] = None   # uncomment if you want to force rating refetch
    with open(rating_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Updated IMDb ID to {args.imdb_id} for {args.category}/{args.id}")

if __name__ == "__main__":
    main()