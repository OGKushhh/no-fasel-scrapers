import os
import subprocess
from time import perf_counter
from datetime import date

start_time = perf_counter()

os.makedirs("./output", exist_ok=True)

print("==========================================")
print("Starting FaselHD scraping pipeline")
print("==========================================")

# 1. Scrape new content (metadata only)
print("\n[1/6] Running FaselMoviesScraper.py ...")
subprocess.run(["python", "FaselMoviesScraper.py"], check=True)

print("\n[2/6] Running FaselAnimeScraper.py ...")
subprocess.run(["python", "FaselAnimeScraper.py"], check=True)

print("\n[3/6] Running FaselSeriesScraper.py ...")
subprocess.run(["python", "FaselSeriesScraper.py"], check=True)

# 2. Fetch fresh IMDb ratings + votes (separate files)
print("\n[4/6] Running update_ratings.py ...")
subprocess.run(["python", "update_ratings.py"], check=True)

# 3. Build trending & featured content (uses rating files)
print("\n[5/6] Running TrendingScraper.py ...")
subprocess.run(["python", "TrendingScraper.py"], check=True)

# 4. Update episodes & status for ongoing series
print("\n[6/6] Running update_episodes.py ...")
subprocess.run(["python", "update_episodes.py"], check=True)

# 5. (Optional) Build global search index
if os.path.exists("AllContentIndexer.py"):
    print("\n[7/7] Running AllContentIndexer.py ...")
    subprocess.run(["python", "AllContentIndexer.py"])

end_time = perf_counter()

with open("./output/last-scraped.txt", "w") as fp:
    fp.write(date.today().strftime("%Y-%m-%d"))

print(f"\n✅ All tasks completed in about {round((end_time - start_time) / 60)} minutes")