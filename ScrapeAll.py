import os
from subprocess import Popen
from time import perf_counter
from datetime import date

# Create output directory if it doesn't exist
os.makedirs("./output", exist_ok=True)

start_time = perf_counter()

movies_process = Popen(["python", "FaselMoviesScraper.py"])
series_process = Popen(["python", "FaselSeriesScraper.py"])
anime_process = Popen(["python", "FaselAnimeScraper.py"])

movies_process.wait()
series_process.wait()
anime_process.wait()

trending_process = Popen(["python", "TrendingScraper.py"])
post_processing_process = Popen(["python", "Postprocessing.py"])

trending_process.wait()
post_processing_process.wait()

all_content_indexing_process = Popen(["python", "AllContentIndexer.py"])
all_content_indexing_process.wait()

end_time = perf_counter()

with open("./output/last-scraped.txt", "w") as fp:
    fp.write(date.today().strftime("%Y-%m-%d"))

print(f"Finished scraping all content in about {round((end_time - start_time) / 60)} minute(s)")