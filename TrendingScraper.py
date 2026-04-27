import json
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from Common import (
    get_website_safe, FASEL_BASE_URL,
    get_latest_movies, get_latest_episodes,
    get_featured_content, get_most_viewed_movies
)

def scrape_trending():
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        print("Failed to fetch homepage")
        return
    soup = BeautifulSoup(resp.text, "html.parser")
    trending_movies = get_latest_movies(soup)        # latest movies grid
    trending_episodes = get_latest_episodes(soup)    # latest episodes
    featured = get_featured_content(soup)            # main slider
    most_viewed = get_most_viewed_movies(soup)       # most viewed slider

    # Ensure all items have a content_type field for frontend routing
    for movie in trending_movies:
        if "content_type" not in movie:
            movie["content_type"] = "movies"
    for item in most_viewed:
        if "content_type" not in item:
            item["content_type"] = "movies"

    # Add timestamp to both outputs
    now = datetime.now(timezone.utc).isoformat()

    with open("./output/trending-content.json", "w", encoding="utf-8") as fp:
        json.dump({
            "movies": trending_movies,
            "episodes": trending_episodes,
            "most_viewed": most_viewed,
            "generated_at": now
        }, fp, indent=4, ensure_ascii=False)

    with open("./output/featured-content.json", "w", encoding="utf-8") as fp:
        json.dump({
            "content": featured,
            "generated_at": now
        }, fp, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    scrape_trending()