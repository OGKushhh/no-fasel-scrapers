import os
import subprocess
from time import perf_counter
from datetime import date

start_time = perf_counter()

# Create output directory if it doesn't exist
os.makedirs("./output", exist_ok=True)

print("==========================================")
print("Starting FaselHD scrapers (INCREMENTAL mode)")
print("==========================================")

# 1. Movies incremental
print("\n[1/3] Running FaselMoviesIncremental.py ...")
result = subprocess.run(["python", "FaselMoviesIncremental.py"])
if result.returncode != 0:
    print("Movies incremental scraper failed. Exiting.")
    exit(1)

# 2. Anime incremental
print("\n[2/3] Running FaselAnimeIncremental.py ...")
result = subprocess.run(["python", "FaselAnimeIncremental.py"])
if result.returncode != 0:
    print("Anime incremental scraper failed. Exiting.")
    exit(1)

# 3. Series incremental (covers series, tvshows, asian-series)
print("\n[3/3] Running FaselSeriesIncremental.py ...")
result = subprocess.run(["python", "FaselSeriesIncremental.py"])
if result.returncode != 0:
    print("Series incremental scraper failed. Exiting.")
    exit(1)

# Post‑processing
print("\nRunning TrendingScraper.py ...")
subprocess.run(["python", "TrendingScraper.py"])

print("\nRunning Postprocessing.py ...")
subprocess.run(["python", "Postprocessing.py"])

print("\nRunning AllContentIndexer.py ...")
subprocess.run(["python", "AllContentIndexer.py"])

end_time = perf_counter()

# Update last-scraped date
with open("./output/last-scraped.txt", "w") as fp:
    fp.write(date.today().strftime("%Y-%m-%d"))

print(f"\nFinished incremental update in about {round((end_time - start_time) / 60)} minutes")