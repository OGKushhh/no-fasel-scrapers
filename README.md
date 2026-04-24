# NoFasel Scraper

Library that provides movie and series sources from [FaselHD](https://www.fasel-hd.cam/).

## Features

- Scrapes movies, anime, series, TV shows, and Asian series from FaselHD
- Bypasses Cloudflare using `Scrapling` (stealth browser) + `curl_cffi` fallback
- Resumable scraping (stop and continue later)
- Extracts metadata: title, image, quality, runtime, country, genres (English & Arabic)
- Dual‑language genres: `Genres` (English) and `GenresAr` (Arabic decoded)
- On‑demand video source extraction (`.m3u8` stream via Playwright)
- Outputs JSON files: `movies.json`, `anime.json`, `series.json`, `tvshows.json`, `asian-series.json`, `trending-content.json`, `featured-content.json`, `all-content.json`

## Requirements

- Python 3.12+
- Google Chrome (for Playwright video extraction)

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

Run the full pipeline:

```bash
python ScrapeAll.py
```

Or run individual scrapers:

```bash
python FaselMoviesScraper.py
python FaselAnimeScraper.py
python FaselSeriesScraper.py
```

After scraping, run post‑processing:

```bash
python TrendingScraper.py
python Postprocessing.py
python AllContentIndexer.py
```

## Contributing

Thanks for taking the time to contribute!

#### Prerequisites

Before you start, please note that the ability to use the following technologies is **required**:

- Python
- Web scraping (BeautifulSoup, Scrapling, Playwright)

## DMCA disclaimer

The developers of this application **do not** have any affiliation with the content available in the app. It is collected from sources freely available through any web browser.

<h4 align='center'>© 2026 OGKushhh</h4>
