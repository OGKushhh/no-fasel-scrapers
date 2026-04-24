import os
import subprocess
from time import perf_counter
from datetime import date

start_time = perf_counter()

# Create output directory if it doesn't exist
os.makedirs("./output", exist_ok=True)

print("==========================================")
print("Starting FaselHD scrapers (sequential)")
print("==========================================")

# 1. Movies
print("\n[1/3] Running FaselMoviesScraper.py ...")
result = subprocess.run(["python", "FaselMoviesScraper.py"])
if result.returncode != 0:
    print("Movies scraper failed. Exiting.")
    exit(1)

# 2. Anime
print("\n[2/3] Running FaselAnimeScraper.py ...")
result = subprocess.run(["python", "FaselAnimeScraper.py"])
if result.returncode != 0:
    print("Anime scraper failed. Exiting.")
    exit(1)

# 3. Series (covers series, tvshows, asian-series)
print("\n[3/3] Running FaselSeriesScraper.py ...")
result = subprocess.run(["python", "FaselSeriesScraper.py"])
if result.returncode != 0:
    print("Series scraper failed. Exiting.")
    exit(1)

# Post‑processing
print("\nRunning TrendingScraper.py ...")
subprocess.run(["python", "TrendingScraper.py"])

print("\nRunning Postprocessing.py ...")
subprocess.run(["python", "Postprocessing.py"])

print("\nRunning AllContentIndexer.py ...")
subprocess.run(["python", "AllContentIndexer.py"])

end_time = perf_counter()

with open("./output/last-scraped.txt", "w") as fp:
    fp.write(date.today().strftime("%Y-%m-%d"))

print(f"\nFinished scraping all content in about {round((end_time - start_time) / 60)} minutes")