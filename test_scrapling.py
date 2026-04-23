from scrapling.fetchers import StealthyFetcher
from bs4 import BeautifulSoup

print("Starting test...")
resp = StealthyFetcher.fetch(
    "https://www.fasel-hd.cam/main",
    headless=True,
    wait_for_selector=".blockMovie",
    timeout=60000
)
if resp and resp.status == 200:
    html = resp.body.decode('utf-8')   # <-- critical fix
    soup = BeautifulSoup(html, "html.parser")
    movies = soup.select(".blockMovie")
    print(f"Found {len(movies)} movies")
else:
    print("Fetch failed")