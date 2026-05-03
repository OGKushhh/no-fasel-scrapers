import json
import os
import re

# All content JSON files produced by scrapers (excluding trending/featured)
CONTENT_FILES = [
    "movies.json", "dubbed-movies.json", "hindi.json", "asian-movies.json", "anime-movies.json",
    "anime.json", "series.json", "tvshows.json", "asian-series.json"
]

def extract_year_from_item(item: dict) -> str:
    """Extract year from ReleaseDate or fallback to Title."""
    release_date = item.get("ReleaseDate")
    if release_date and isinstance(release_date, str):
        m = re.search(r'\b(19|20)\d{2}\b', release_date)
        if m:
            return m.group(0)
    title = item.get("Title", "")
    m = re.search(r'\b(19|20)\d{2}\b', title)
    return m.group(0) if m else ""

def main() -> None:
    all_content = []

    for filename in CONTENT_FILES:
        filepath = f"./output/{filename}"
        if not os.path.exists(filepath):
            print(f"Warning: {filename} not found, skipping...")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Infer content_type from filename
        if "movie" in filename or filename == "anime-movies.json":
            content_type = "movie"
        elif filename == "anime.json":
            content_type = "anime"
        else:
            content_type = "series"

        for item_id, item in data.items():
            entry = {
                "id": item_id,
                "title": item.get("Title", ""),
                "image": item.get("Image Source", ""),
                "category": content_type,
                "genres": item.get("Genres", []),
                "year": extract_year_from_item(item),
                "last_scraped": item.get("last_scraped")   # may be None
            }
            all_content.append(entry)

    # Write aggregated index
    with open("./output/all-content.json", "w", encoding="utf-8") as fp:
        json.dump({"content": all_content, "total": len(all_content)}, fp, indent=4, ensure_ascii=False)

    print(f"✅ all-content.json generated with {len(all_content)} items.")

if __name__ == "__main__":
    main()