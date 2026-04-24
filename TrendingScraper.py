import json
from bs4 import BeautifulSoup
from Common import get_website_safe, FASEL_BASE_URL, get_latest_movies, get_latest_episodes, get_featured_content

def scrape_trending():
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        print("Failed to fetch homepage")
        return
    soup = BeautifulSoup(resp.text, "html.parser")
    trending_movies = get_latest_movies(soup)
    trending_episodes = get_latest_episodes(soup)
    featured = get_featured_content(soup)

    # Save to output files (adapt to your existing format)
    with open("./output/trending-content.json", "w", encoding="utf-8") as fp:
        json.dump({"movies": trending_movies, "episodes": trending_episodes}, fp, indent=4, ensure_ascii=False)
    with open("./output/featured-content.json", "w", encoding="utf-8") as fp:
        json.dump({"content": featured}, fp, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    scrape_trending()