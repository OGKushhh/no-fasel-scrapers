import json
import re
import time
from Common import get_imdb_rating

def backfill_movies_imdb():
    json_file = "./output/movies.json"
    print(f"Loading {json_file}...")
    with open(json_file, "r", encoding="utf-8") as f:
        movies = json.load(f)

    updated = 0
    total = len(movies)
    print(f"Total movies: {total}")

    for idx, (movie_id, movie) in enumerate(movies.items(), 1):
        # Skip if already has a rating
        if "IMDb_Rating" in movie and movie["IMDb_Rating"] is not None:
            print(f"[{idx}/{total}] Skipping {movie.get('Title')} (already has rating)")
            continue

        title = movie.get("Title")
        if not title:
            print(f"[{idx}/{total}] Movie ID {movie_id} has no title, skipping")
            continue

        # Try to extract year from ReleaseDate if available (optional, you may not have this field)
        year = None
        release_date = movie.get("ReleaseDate")
        if release_date:
            year_match = re.search(r'\d{4}', release_date)
            if year_match:
                year = year_match.group(0)

        print(f"[{idx}/{total}] Fetching IMDb rating for: {title}" + (f" ({year})" if year else ""))
        rating = get_imdb_rating(title, year, content_type="movie")
        if rating:
            movie["IMDb_Rating"] = rating
            updated += 1
            print(f"  ✅ Rating: {rating}")
        else:
            movie["IMDb_Rating"] = None
            print(f"  ⚠️ No rating found")

        # Be polite to the API (max 1000 requests/day, ~1 per second is safe)
        time.sleep(0.5)

        # Save every 20 movies to avoid losing progress
        if idx % 20 == 0:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(movies, f, indent=4, ensure_ascii=False)
            print(f"  💾 Saved progress at {idx}/{total}")

    # Final save
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(movies, f, indent=4, ensure_ascii=False)
    print(f"\n✅ Backfill complete. Updated {updated} out of {total} movies.")

if __name__ == "__main__":
    backfill_movies_imdb()