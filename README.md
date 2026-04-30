# 🎬 NoFasel Scraper

A complete, production‑ready Python library that scrapes movie and series metadata from [FaselHD](https://www.fasel-hd.cam/), extracts episodes, and fetches IMDb ratings & vote counts – all without storing ratings inside your main JSONs.

## ✨ Features

- ✅ Bypasses Cloudflare using **Scrapling** (stealth browser) + **curl_cffi** fallback – no Playwright in metadata fetching.
- 🎞️ Scrapes **all movie categories**: `movies`, `dubbed-movies`, `hindi`, `asian-movies`, `anime-movies`.
- 📺 Scrapes **series, TV shows, Asian series, and anime** (with episodes).
- 📝 Extracts **titles, images, quality, runtime, country, dual‑language genres** (English & Arabic decoded).
- 💾 Saves metadata as **separate JSON files** (`movies.json`, `dubbed-movies.json`, `hindi.json`, `asian-movies.json`, `anime-movies.json`, `anime.json`, `series.json`, `tvshows.json`, `asian-series.json`).
- 🎥 **On‑demand video source extraction** (`.m3u8`) using Playwright – no pre‑scraping of video URLs.
- ⭐ **Separate IMDb ratings & vote counts** stored in `./output/ratings/{category}/{id}.json` – never touches original metadata.
- 🔁 **Unified scrapers** (one per content type) that are both **resumable** and **incremental** – they stop when all content on a page is already known.
- 🆕 **Daily episode updater** (`update_episodes.py`) that checks all series for new episodes and updates the episode files **and** the `Status` field (handles the “completed with new episodes” loophole).
- 📈 **Rating updater** (`update_ratings.py`) fetches IMDb ratings + vote counts from OMDb API – respects 1000/day limit, caches results, resumable.
- 📆 **Orchestrator script** (`ScrapeAll.py`) runs the entire pipeline in the correct order.

## 📋 Requirements

- 🐍 Python 3.12+
- 🌐 Google Chrome (for Playwright video extraction)
- An [OMDb API](http://www.omdbapi.com/) key (free tier: 1000 requests/day) – already included in `Common.py` (you can replace it with your own).

## 🚀 Installation

```bash
git clone https://github.com/yourusername/no-fasel-scrapers.git
cd no-fasel-scrapers
pip install -r requirements.txt
playwright install chromium
```

## 🧪 Usage

### 🔁 Full scrape (initial seed)

Run the unified orchestrator to build the initial JSON files and episode/rating folders:

```bash
python ScrapeAll.py
```

This will:
1. Scrape all movie categories, anime, and series (metadata only)
2. Fetch IMDb ratings & votes (separate files)
3. Generate trending and featured content (using fresh ratings)
4. Check for episodes and update statuses

### 📆 Daily incremental updates

After the first full run, `ScrapeAll.py` (with its built‑in incremental logic) will automatically:
- Start from the last saved page for each category
- Stop when a page contains only already known IDs
- Only fetch new IMDb ratings for missing items
- Only check ongoing series for new episodes

No separate incremental script needed – the unified scrapers do it all.

### 🧽 Optional: Clean metadata

Run `clean_metadata.py` occasionally to normalise country names, runtime, and replace hyphens in genres:

```bash
python clean_metadata.py
```

### 🎯 On‑demand video source extraction

To get the direct `.m3u8` stream URL for a movie or episode page (without downloading), use the `/extract` endpoint in `app.py` or call `extract_video_source(page_url)` directly:

```python
from Common import extract_video_source
stream_url = extract_video_source("https://www.fasel-hd.cam/movies/...")
```

## 📁 File Structure

| File | Purpose |
|------|---------|
| `Common.py` | Core fetching + extraction (thread‑safe) |
| `FaselMoviesScraper.py` | Unified scraper for all movie categories |
| `FaselAnimeScraper.py` | Unified scraper for anime series |
| `FaselSeriesScraper.py` | Unified scraper for series, tvshows, asian-series |
| `TrendingScraper.py` | Extracts homepage trending content and enriches with fresh ratings |
| `update_ratings.py` | Fetches IMDb ratings & votes → `./output/ratings/` |
| `update_episodes.py` | Checks for new episodes, updates episode files & status |
| `clean_metadata.py` | (Optional) manual normalisation of genres, country, runtime |
| `AllContentIndexer.py` | (Optional) creates unified `all-content.json` for fast search |
| `ScrapeAll.py` | Orchestrator – runs all steps in correct order |
| `app.py` | Flask API to serve metadata, episodes, and ratings |
| `fasel_downloader_final.py` | Legacy video extraction + download (Playwright + yt‑dlp) |

## 📂 Output Structure

```
./output/
├── movies.json
├── dubbed-movies.json
├── hindi.json
├── asian-movies.json
├── anime-movies.json
├── anime.json
├── series.json
├── tvshows.json
├── asian-series.json
├── trending-content.json
├── featured-content.json
├── all-content.json (optional)
├── ratings/
│   ├── movies/
│   │   └── {id}.json
│   ├── anime/
│   ├── series/
│   └── ...
├── episodes/
│   ├── series/
│   ├── tvshows/
│   ├── asian-series/
│   └── anime/
└── last_page_*.txt (progress files)
```

Each rating file contains:
```json
{
  "content_id": "12345",
  "title": "Ambulance",
  "year": "2022",
  "rating": "6.2",
  "votes": 123456,
  "source": "omdb",
  "last_updated": "2026-04-30T12:00:00Z"
}
```

## 🗺️ Next Steps for Your Project

1. 🏃 **Run `ScrapeAll.py` once** – it will scrape everything (may take hours). You can stop and resume anytime.
2. 🔄 **Set up a daily cron job** (or use cron‑job.org) to run `ScrapeAll.py` every day – the incremental logic ensures it only fetches new content and ratings.
3. ⚛️ **Build your React frontend** to consume the JSON files (or use `app.py` as an API).
4. ▶️ **For video playback**, call `/extract` with the content URL or use the `extract_video_source()` function.

## 🔮 Future Enhancements (Parked)

- 🎌 Group anime seasons using external metadata (MyAnimeList) or title‑based heuristics.
- 🌐 Proxy rotation and persistent browser session (optional).
- 🗄️ SQLite storage instead of JSON files.

## 🤝 Contributing

Thanks for taking the time to contribute!

#### Prerequisites

Before you start, please note that the ability to use the following technologies is **required**:

- 🐍 Python
- 🕸️ Web scraping (BeautifulSoup, Scrapling, Playwright)

## ⚖️ DMCA Disclaimer

The developers of this application **do not** have any affiliation with the content available in the app. It is collected from sources freely available through any web browser.

<h4 align='center'>© 2026 OGKushhh</h4>