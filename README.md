# 🎬 NoFasel Scraper – Complete Scraping & API System

A production‑ready Python tool that scrapes all movies and series from FaselHD, extracts IMDb ratings and votes, stores episodes separately, and serves everything via a Flask API with persistent view counters.

## 📦 What’s Inside

- **3 unified scrapers** (movies, anime, series) – resumable, incremental, and sequential.
- **Separate rating system** – OMDb API fetches ratings + votes; stored in individual JSON files (no pollution of main metadata).
- **Episode updater** – checks all series for new episodes daily, updates episode JSONs and series `Status`.
- **Trending scraper** – enriches homepage content with fresh ratings.
- **Flask API** – serves metadata, ratings, episodes, and video stream extraction.
- **Global view counter** – cumulative per content, stored persistently (works on Hugging Face Spaces).

---

## 📂 Output File Structure

All generated files go into `./output/` (or `./data/` for the API). The structure is:

```
output/
├── content/ (main metadata)
│   ├── movies.json
│   ├── dubbed-movies.json
│   ├── hindi.json
│   ├── asian-movies.json
│   ├── anime-movies.json
│   ├── anime.json
│   ├── series.json
│   ├── tvshows.json
│   └── asian-series.json
│
├── episodes/
│   ├── anime/
│   ├── series/
│   ├── tvshows/
│   └── asian-series/
│
├── ratings/
│   ├── movies/
│   ├── anime/
│   ├── series/
│   └── ...
│
├── trending-content.json
├── featured-content.json
├── all-content.json (optional search index)
├── imdb_id_map.json
├── omdb_cache.json
├── last_page_*.txt (progress files)
├── last-scraped.txt
├── failed_scripts.log
└── scraper_errors.log
```

---

## 🛠️ Scripts & What They Do

| Script | Reads from | Writes / Updates | Notes |
|--------|------------|------------------|-------|
| `FaselMoviesScraper.py` | FaselHD movie categories | `movies.json`, `dubbed-movies.json`, `hindi.json`, `asian-movies.json`, `anime-movies.json` | Resumable, incremental. Never writes ratings. |
| `FaselAnimeScraper.py` | `/anime` (series) | `anime.json` + `episodes/anime/*.json` | Same as above. |
| `FaselSeriesScraper.py` | `/series`, `/tvshows`, `/asian-series` | `series.json`, `tvshows.json`, `asian-series.json` + episodes | Also extracts seasons & episodes. |
| `update_ratings.py` | All main content JSONs | `ratings/*/*.json`, `imdb_id_map.json`, `omdb_cache.json` | Fetches IMDb rating+votes. Exits cleanly on API limit – never writes `null`. |
| `update_episodes.py` | Main series/anime JSONs + existing episodes | Updates `episodes/*.json` (appends new episodes) and `Status` in main JSONs | Runs daily. Ignores `Status` when checking episodes – closes the loophole. |
| `TrendingScraper.py` | FaselHD homepage + rating files | `trending-content.json`, `featured-content.json` | Enriches with fresh ratings from `ratings/`. |
| `AllContentIndexer.py` (optional) | All main JSONs | `all-content.json` | Lightweight search index (id, title, image, category, genres). |
| `clean_metadata.py` (optional) | Main JSONs | Same files (in‑place) | Normalises country names, runtime, replaces hyphens in genres. |
| `ScrapeAll.py` | – | Orchestrates the pipeline. Creates `last-scraped.txt` and `failed_scripts.log`. | Runs scrapers → ratings → episodes in correct order. |
| `app.py` | `./data/` (or `./output/`) | Serves metadata, ratings, episodes. Also `/extract` (video) and `/api/view/*` (view counter). | Uses persistent storage (`/data`) for view counts. |

---

## 🔁 Pipeline Execution Order (Daily)

1. **Scrape new content** – `FaselMoviesScraper.py`, `FaselAnimeScraper.py`, `FaselSeriesScraper.py`
2. **Fetch/update ratings** – `update_ratings.py`
3. **Update episodes & status** – `update_episodes.py`
4. *(Optional)* **Rebuild trending content** – `TrendingScraper.py`
5. *(Optional)* **Build search index** – `AllContentIndexer.py`

Run `python ScrapeAll.py` to execute the full daily pipeline automatically.

---

## 🧠 Core Logic Explained

### Incremental Scraping (Daily Mode)
- After the first full scrape, each scraper stores `last_page_*.txt = total_pages`.
- On subsequent runs, it starts from **page 1**, checks **only the first 5 pages** (configurable), and stops as soon as a page contains **only already known IDs**. This catches all new releases without wasting time.
- During the **initial full scrape**, progress is saved so you can resume if interrupted.

### Separate Ratings
- Main metadata JSONs contain **no `IMDb_Rating`** field – they stay clean.
- Ratings are stored as `ratings/{category}/{id}.json`:
  ```json
  {
    "content_id": "12345",
    "title": "Ambulance",
    "year": "2022",
    "rating": "6.2",
    "votes": 123456,
    "source": "omdb",
    "imdb_id": "tt1234567",
    "last_updated": "2026-05-01T..."
  }
  ```
- If OMDb API daily limit (1000) is reached, the script **exits without writing any `null`** – no corrupt data.

### Episode & Status Loophole Fix
- `update_episodes.py` **ignores** the `Status` field – it always fetches the latest episode pages.
- If new episodes are found, it **forces `Status` back to `مستمر`** (ongoing).
- Then it updates the status from Fasel’s detail page. This prevents marking a series completed while new episodes exist.

### View Counter (Global)
- Endpoints: `POST /api/view/<category>/<id>` (with `{"increment_by": N}`) and `GET /api/view/<category>/<id>`.
- Data stored in `/data/view_counts.json` with file locking (`portalocker`).
- Cumulative, no reset.

---

## 🚀 Deployment on Hugging Face Spaces

1. **Create a Space** (Docker or Python). Choose a persistent storage tier (mounts `/data`).
2. **Upload your code** (all `.py` files, `requirements.txt`).
3. **Set `requirements.txt`** (minimal, no pinned versions – let pip resolve):
   ```
   requests
   beautifulsoup4
   flask
   flask-cors
   Pillow
   scrapling[all]
   curl_cffi
   playwright
   portalocker
   gunicorn
   ```
4. **Install Playwright browsers** – add a `Dockerfile`:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   RUN playwright install chromium && playwright install-deps
   COPY . .
   ENV PORT=7860
   CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "8"]
   ```
5. **Enable persistent storage** in Space settings (mounts `/data`). Put your pre‑scraped JSONs into `/data` (or copy via `hf sync`).
6. **Set environment variables** (optional): `OMDB_API_KEY`, `DATA_DIR` (defaults to `./data`).

After deployment, your API is live at `https://your-space.hf.space`.

---

## 🧪 Local Development (Windows / Linux)

- Use Python 3.11+.
- Install dependencies: `pip install -r requirements.txt` (use the same file as above).
- Run `playwright install chromium`.
- Set `DATA_DIR=./output` in your environment or let `app.py` default to `./data` (then symlink/copy `./output` to `./data`).
- Run the pipeline: `python ScrapeAll.py`.
- Start the API: `python app.py` (listens on `http://localhost:7860`).

---

## 📌 Important Notes

- **First run** will take a long time (scrapes all pages). Use `ScrapeAll.py` – it is resumable.
- **Daily runs** after that finish in minutes (only first few pages + new ratings).
- **OMDb API key** is free (1000 requests/day). The script respects the limit and never writes `null`.
- **FaselHD domain** may change. Update `FASEL_BASE_URL` in `Common.py` if the site moves.
- **Do not edit the JSON files manually** – they are overwritten. Use `clean_metadata.py` for normalisation.

---

## 🤝 Contributing

Pull requests are welcome. Before contributing, understand the data flow above and ensure changes respect the incremental logic and rate limits.

---

## ⚖️ DMCA Disclaimer

This tool does **not** host any content. It only scrapes publicly available web pages and uses the OMDb API for ratings. The developers are not affiliated with FaselHD or IMDb.

---

**Enjoy your fully automated media library!** 🎉