import json
import os
import shutil
import re
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Files to clean (all metadata JSONs produced by scrapers)
FILES_TO_CLEAN = [
    "movies.json",
    "dubbed-movies.json",
    "hindi.json",
    "asian-movies.json",
    "anime-movies.json",
    "anime.json",
    "series.json",
    "tvshows.json",
    "asian-series.json"
]

# Country normalisation
COUNTRY_REPLACEMENTS = {
    "Also known as": "International",
    "United States": "USA",
    "United Kingdom": "UK",
    "U.S.": "USA",
    "U.K.": "UK",
    "N/A": None,
    "": None,
}

# English → Arabic genre map (used only if TRANSLATE_MISSING = True)
EN_TO_AR_GENRE = {
    "Action": "أكشن",
    "Comedy": "كوميدي",
    "Drama": "دراما",
    "Horror": "رعب",
    "Thriller": "إثارة",
    "Adventure": "مغامرة",
    "Crime": "جريمة",
    "Romance": "رومانسية",
    "Science Fiction": "خيال علمي",
    "Fantasy": "فانتازيا",
    "Animation": "أنميشن",
    "Documentary": "وثائقي",
    "Biography": "سيرة ذاتية",
    "History": "تاريخي",
    "Music": "موسيقى",
    "Family": "عائلي",
    "Mystery": "غموض",
    "War": "حرب",
    "Western": "غربي",
    "Sport": "رياضي",
    "Reality-TV": "تلفزيون الواقع",
    "News": "أخبار",
    "Talk-Show": "برامج حوارية",
    "Game-Show": "برامج مسابقات",
    "Musical": "موسيقي",
}

def backup_file(file_path: str) -> None:
    """Create a backup copy in ./baks/ folder before modifying."""
    if not os.path.exists(file_path):
        return
    baks_dir = Path("./baks")
    baks_dir.mkdir(exist_ok=True)
    filename = os.path.basename(file_path)
    backup_path = baks_dir / f"{filename}.bak"
    shutil.copy2(file_path, backup_path)
    logging.info(f"Backup created: {backup_path}")

def clean_genre_string(genre: str) -> str:
    """Replace hyphens with spaces in a single genre string."""
    return genre.replace("-", " ")

def clean_genre_list(genres: list) -> list:
    """Apply hyphen→space replacement to each genre in the list."""
    if not genres:
        return genres
    return [clean_genre_string(g) for g in genres]

def clean_country(country: str) -> Optional[str]:
    """Normalise country name; return None for invalid."""
    if not country or country == "N/A":
        return None
    return COUNTRY_REPLACEMENTS.get(country, country)

def clean_runtime(runtime):
    """Ensure runtime is int or None."""
    if runtime is None:
        return None
    if isinstance(runtime, int):
        return runtime
    if isinstance(runtime, str):
        cleaned = re.sub(r'[^0-9]', '', runtime)
        if cleaned.isdigit():
            return int(cleaned)
    return None

def clean_release_date(date_str: str) -> str:
    """
    Normalise release date string.
    Converts "20242025" -> "2024-2025"
    Converts "2024 2025" -> "2024-2025"
    Also if the string is a single 4‑digit year outside realistic range, return empty string.
    """
    if not isinstance(date_str, str):
        return date_str
    # Handle concatenated years: 20242025 -> 2024-2025
    match = re.fullmatch(r'^(\d{4})(\d{4})$', date_str.strip())
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    # Handle years separated by whitespace or non-digit
    match = re.search(r'(\d{4})\s*[^\d]?\s*(\d{4})', date_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    
    # If it's a single 4-digit year, validate it
    match = re.fullmatch(r'^\s*(\d{4})\s*$', date_str)
    if match:
        year = int(match.group(1))
        current_year = datetime.now().year
        if not (1900 <= year <= current_year + 4):
            return ""  # remove unrealistic year
    return date_str

def translate_missing_arabic_genres(data: dict) -> bool:
    """
    If GenresAr is empty or identical to Genres (English), replace GenresAr
    with translated Arabic using the map. Returns True if changed.
    """
    genres_en = data.get("Genres", [])
    genres_ar = data.get("GenresAr", [])
    if not genres_ar or genres_ar == genres_en:
        translated = [EN_TO_AR_GENRE.get(g, g) for g in genres_en]
        data["GenresAr"] = translated
        return True
    return False

def clean_json_file(file_name: str, translate_missing_ar: bool = False) -> None:
    """Load, clean, and save a JSON file (replace hyphens, normalise country/runtime/release date)."""
    file_path = f"./output/{file_name}"
    if not os.path.exists(file_path):
        logging.warning(f"{file_path} not found, skipping.")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in {file_path}: {e}")
        return

    # Backup original to ./baks/
    backup_file(file_path)

    modified = False
    for content_id, content in data.items():
        # Replace hyphens in genres
        if "Genres" in content and isinstance(content["Genres"], list):
            new_genres = clean_genre_list(content["Genres"])
            if new_genres != content["Genres"]:
                content["Genres"] = new_genres
                modified = True
        if "GenresAr" in content and isinstance(content["GenresAr"], list):
            new_ar_genres = clean_genre_list(content["GenresAr"])
            if new_ar_genres != content["GenresAr"]:
                content["GenresAr"] = new_ar_genres
                modified = True

        # Optional: fill missing Arabic genres
        if translate_missing_ar and "Genres" in content:
            if translate_missing_arabic_genres(content):
                modified = True

        # Clean country
        if "Country" in content:
            new_country = clean_country(content["Country"])
            if new_country != content["Country"]:
                content["Country"] = new_country
                modified = True

        # Clean runtime
        if "Runtime" in content:
            new_runtime = clean_runtime(content["Runtime"])
            if new_runtime != content["Runtime"]:
                content["Runtime"] = new_runtime
                modified = True

        # Clean release date
        if "ReleaseDate" in content:
            new_date = clean_release_date(content["ReleaseDate"])
            if new_date != content["ReleaseDate"]:
                content["ReleaseDate"] = new_date
                modified = True

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Cleaned and saved {file_path}")
    else:
        logging.info(f"No changes needed for {file_path}")

def main():
    # Set to True if you want to add Arabic translations for missing GenresAr
    TRANSLATE_MISSING = False   # Keep False to preserve original Arabic data

    for file_name in FILES_TO_CLEAN:
        clean_json_file(file_name, translate_missing_ar=TRANSLATE_MISSING)

    logging.info("Metadata cleaning complete.")

if __name__ == "__main__":
    main()