import json
import re

# Load movies.json
with open("./output/movies.json", "r", encoding="utf-8") as f:
    movies = json.load(f)

# Normalisation rules
country_replacements = {
    "Also known as": "International",
    "United States": "USA",
    "United Kingdom": "UK",
    # add more as needed
}

for movie_id, data in movies.items():
    # Clean genres (replace hyphen with space)
    if "Genres" in data:
        data["Genres"] = [g.replace("-", " ") for g in data["Genres"]]
    if "GenresAr" in data:
        data["GenresAr"] = [g.replace("-", " ") for g in data["GenresAr"]]

    # Normalise country
    if "Country" in data and data["Country"] in country_replacements:
        data["Country"] = country_replacements[data["Country"]]

# Write back
with open("./output/movies.json", "w", encoding="utf-8") as f:
    json.dump(movies, f, indent=4, ensure_ascii=False)