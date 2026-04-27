# backfill_movies_description.py
import json
import time
from Common import get_website_safe, extract_description, REQUEST_DELAY
from bs4 import BeautifulSoup

def backfill_movies_description():
    with open("./output/movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)

    updated = 0
    for movie_id, movie_data in movies.items():
        if "Description" in movie_data and movie_data["Description"]:
            continue  # already has description
        # Use the post ID URL
        detail_url = f"https://www.fasel-hd.cam/?p={movie_id}"
        print(f"Fetching {movie_id} -> {detail_url}")
        resp = get_website_safe(detail_url)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            desc = extract_description(soup)
            movie_data["Description"] = desc
            updated += 1
            print(f"  Added description for {movie_id}")
        else:
            movie_data["Description"] = ""
            print(f"  Failed to fetch {movie_id}")
        time.sleep(REQUEST_DELAY)  # be polite

    # Save back
    with open("./output/movies.json", "w", encoding="utf-8") as f:
        json.dump(movies, f, indent=4, ensure_ascii=False)

    print(f"Done. Updated {updated} movies.")

if __name__ == "__main__":
    backfill_movies_description()