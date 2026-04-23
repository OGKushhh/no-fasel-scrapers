import asyncio
import json
from scrapling.fetchers import StealthySession
from Common import FASEL_BASE_URL, DEBUG

async def scrape_trending():
    async with StealthySession(headless=True, network_idle=True) as session:
        resp = await session.fetch_async(FASEL_BASE_URL + "main", headless=True)
        if not resp or resp.status != 200:
            if DEBUG:
                print("Failed to fetch homepage for trending content")
            return

        # Extract trending items using Scrapling's CSS selector
        featured = resp.css('.featured-item')  # adjust selector if needed
        # Process and save trending-content.json
        # (similar to original logic but using Scrapling's API)

if __name__ == "__main__":
    asyncio.run(scrape_trending())