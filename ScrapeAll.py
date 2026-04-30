import os
import subprocess
from time import perf_counter
from datetime import date, datetime

start_time = perf_counter()

os.makedirs("./output", exist_ok=True)

def run_script(script_name):
    """Run a Python script, return True if success, False if failed."""
    print(f"\n▶️ Running {script_name} ...")
    result = subprocess.run(["python", script_name])
    if result.returncode != 0:
        print(f"❌ {script_name} failed (exit code {result.returncode})")
        with open("./output/failed_scripts.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - {script_name} failed\n")
        return False
    print(f"✅ {script_name} finished successfully")
    return True

print("==========================================")
print("Starting FaselHD scraping pipeline")
print("==========================================")

# List of scripts in order of execution (TrendingScraper.py removed)
scripts = [
    "FaselMoviesScraper.py",
    "FaselAnimeScraper.py",
    "FaselSeriesScraper.py",
    "update_ratings.py",
    "update_episodes.py",
]

failures = []
for script in scripts:
    if not run_script(script):
        failures.append(script)

# Optional: run AllContentIndexer.py if it exists
if os.path.exists("AllContentIndexer.py"):
    run_script("AllContentIndexer.py")

end_time = perf_counter()

with open("./output/last-scraped.txt", "w") as fp:
    fp.write(date.today().strftime("%Y-%m-%d"))

print("\n" + "="*50)
if failures:
    print(f"⚠️ Some scripts failed: {', '.join(failures)}")
    print(f"Check ./output/failed_scripts.log for details.")
else:
    print("✅ All scripts completed successfully.")
print(f"Total time: {round((end_time - start_time) / 60)} minutes")