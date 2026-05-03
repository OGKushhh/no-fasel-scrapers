"""
AbdoBest API – Metadata + Video Extraction + Episodes + Global View Counter
Serves JSON files from /data, extracts video streams, tracks cumulative views.
"""

import os
import time
import threading
import json
import portalocker
from typing import Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone

# ----------------------------------------------------------------------
#  In‑memory cache for video extraction (TTL 6 hours)
# ----------------------------------------------------------------------
class Cache:
    def __init__(self, default_ttl: int = 21600):
        self._store = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() > entry["expires_at"]:
                del self._store[key]
                return None
            return {"stream_url": entry["stream_url"], "quality_options": entry.get("quality_options", [])}

    def set(self, key: str, stream_url: str, quality_options: list = None, ttl: int = None):
        ttl = ttl or self._default_ttl
        with self._lock:
            self._store[key] = {
                "stream_url": stream_url,
                "quality_options": quality_options or [],
                "expires_at": time.time() + ttl,
                "created_at": time.time(),
            }

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            valid = sum(1 for e in self._store.values() if now < e["expires_at"])
            return {"total_entries": len(self._store), "valid_entries": valid, "default_ttl": self._default_ttl}

# ----------------------------------------------------------------------
#  Global view counter – persistent storage with file locking
# ----------------------------------------------------------------------
VIEWS_FILE = "/data/view_counts.json"   # Persistent storage on Hugging Face Spaces
os.makedirs(os.path.dirname(VIEWS_FILE), exist_ok=True)

def _read_views() -> dict:
    """Read view counts from JSON file with shared lock."""
    if not os.path.exists(VIEWS_FILE):
        return {}
    with open(VIEWS_FILE, "r") as f:
        portalocker.lock(f, portalocker.LOCK_SH)
        try:
            return json.load(f)
        finally:
            portalocker.unlock(f)

def _write_views(views: dict):
    """Write view counts to JSON file with exclusive lock."""
    with open(VIEWS_FILE, "w") as f:
        portalocker.lock(f, portalocker.LOCK_EX)
        try:
            json.dump(views, f, indent=2)
        finally:
            portalocker.unlock(f)

def increment_view(content_id: str, category: str = "general", by: int = 1) -> int:
    """
    Increment global view count for a content ID by a given amount.
    Returns the new total count.
    """
    views = _read_views()
    key = f"{category}:{content_id}"
    views[key] = views.get(key, 0) + by
    _write_views(views)
    return views[key]

def get_view_count(content_id: str, category: str = "general") -> int:
    """Get current global view count for a content ID."""
    views = _read_views()
    key = f"{category}:{content_id}"
    return views.get(key, 0)

# ----------------------------------------------------------------------
#  Helper to load JSON files from the data folder
# ----------------------------------------------------------------------
DATA_DIR = os.environ.get("DATA_DIR", "./data")

def load_json(filename: str):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def load_episodes(category: str, content_id: str):
    filepath = os.path.join(DATA_DIR, "episodes", category, f"{content_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

# ----------------------------------------------------------------------
#  App setup
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
CORS(app, resources={r"/*": {"origins": "*"}})

cache = Cache(default_ttl=21600)

try:
    from Common import extract_video_source
    SCRAPER_READY = True
except ImportError as e:
    SCRAPER_READY = False
    print(f"[ERROR] Cannot import Common.py: {e}")
    def extract_video_source(url, headless=True):
        raise NotImplementedError("Common.py not available")

# ----------------------------------------------------------------------
#  Root endpoint – friendly JSON message
# ----------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "✅ AbdoBest API is running!",
        "endpoints": {
            "health": "/health",
            "extract (POST)": "/extract",
            "movies": "/api/movies",
            "dubbed_movies": "/api/dubbed-movies",
            "hindi": "/api/hindi",
            "asian_movies": "/api/asian-movies",
            "anime": "/api/anime",
            "anime_movies": "/api/anime-movies",
            "series": "/api/series",
            "tvshows": "/api/tvshows",
            "asian_series": "/api/asian-series",
            "trending": "/api/trending",
            "featured": "/api/featured",
            "search": "/api/search?q=...",
            "ratings": "/api/ratings/<category>/<id>",
            "all_content": "/api/all-content",
            "episodes": "/api/episodes/<category>/<id>",
            "anime_episodes": "/api/anime-episodes/<id>",
            "view_increment": "POST /api/view/<category>/<id> (body: {\"increment_by\": N})",
            "view_get": "GET /api/view/<category>/<id>"
        },
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

# ----------------------------------------------------------------------
#  Global view counter endpoints
# ----------------------------------------------------------------------
@app.route("/api/view/<category>/<content_id>", methods=["POST"])
def increment_view_endpoint(category: str, content_id: str):
    """
    Increment global view count for a specific content.
    Accepts JSON body: {"increment_by": N} (default 1).
    Returns the new total count.
    """
    data = request.get_json(silent=True) or {}
    increment_by = data.get("increment_by", 1)
    if not isinstance(increment_by, int) or increment_by <= 0:
        increment_by = 1
    new_count = increment_view(content_id, category, by=increment_by)
    return jsonify({
        "content_id": content_id,
        "category": category,
        "views": new_count,
        "incremented_by": increment_by,
        "status": "ok"
    })

@app.route("/api/view/<category>/<content_id>", methods=["GET"])
def get_view_endpoint(category: str, content_id: str):
    """Get current global view count for a specific content."""
    count = get_view_count(content_id, category)
    return jsonify({
        "content_id": content_id,
        "category": category,
        "views": count
    })

# ----------------------------------------------------------------------
#  Metadata endpoints (existing, unchanged)
# ----------------------------------------------------------------------
@app.route("/api/movies", methods=["GET"])
def get_movies():
    data = load_json("movies.json")
    if data is None:
        return jsonify({"error": "movies.json not found"}), 404
    movie_id = request.args.get("id")
    if movie_id:
        return jsonify(data.get(movie_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/dubbed-movies", methods=["GET"])
def get_dubbed_movies():
    data = load_json("dubbed-movies.json")
    if data is None:
        return jsonify({"error": "dubbed-movies.json not found"}), 404
    movie_id = request.args.get("id")
    if movie_id:
        return jsonify(data.get(movie_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/hindi", methods=["GET"])
def get_hindi_movies():
    data = load_json("hindi.json")
    if data is None:
        return jsonify({"error": "hindi.json not found"}), 404
    movie_id = request.args.get("id")
    if movie_id:
        return jsonify(data.get(movie_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/asian-movies", methods=["GET"])
def get_asian_movies():
    data = load_json("asian-movies.json")
    if data is None:
        return jsonify({"error": "asian-movies.json not found"}), 404
    movie_id = request.args.get("id")
    if movie_id:
        return jsonify(data.get(movie_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/anime", methods=["GET"])
def get_anime():
    data = load_json("anime.json")
    if data is None:
        return jsonify({"error": "anime.json not found"}), 404
    anime_id = request.args.get("id")
    if anime_id:
        return jsonify(data.get(anime_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/series", methods=["GET"])
def get_series():
    data = load_json("series.json")
    if data is None:
        return jsonify({"error": "series.json not found"}), 404
    series_id = request.args.get("id")
    if series_id:
        return jsonify(data.get(series_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/tvshows", methods=["GET"])
def get_tvshows():
    data = load_json("tvshows.json")
    if data is None:
        return jsonify({"error": "tvshows.json not found"}), 404
    show_id = request.args.get("id")
    if show_id:
        return jsonify(data.get(show_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/asian-series", methods=["GET"])
def get_asian_series():
    data = load_json("asian-series.json")
    if data is None:
        return jsonify({"error": "asian-series.json not found"}), 404
    series_id = request.args.get("id")
    if series_id:
        return jsonify(data.get(series_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/anime-movies", methods=["GET"])
def get_anime_movies():
    data = load_json("anime-movies.json")
    if data is None:
        return jsonify({"error": "anime-movies.json not found"}), 404
    movie_id = request.args.get("id")
    if movie_id:
        return jsonify(data.get(movie_id, {"error": "Not found"}))
    return jsonify(data)

@app.route("/api/trending", methods=["GET"])
def get_trending():
    data = load_json("trending-content.json")
    if data is None:
        return jsonify({"error": "trending-content.json not found"}), 404
    return jsonify(data)

@app.route("/api/featured", methods=["GET"])
def get_featured():
    data = load_json("featured-content.json")
    if data is None:
        return jsonify({"error": "featured-content.json not found"}), 404
    return jsonify(data)

@app.route("/api/ratings/<category>/<content_id>", methods=["GET"])
def get_rating(category: str, content_id: str):
    rating_file = os.path.join(DATA_DIR, "ratings", category, f"{content_id}.json")
    if not os.path.exists(rating_file):
        return jsonify({"error": "Rating not found"}), 404
    with open(rating_file, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

# ----------------------------------------------------------------------
#  All content endpoint (aggregated search index)
# ----------------------------------------------------------------------
@app.route("/api/all-content", methods=["GET"])
def get_all_content():
    """Return the aggregated search index (all-content.json)."""
    data = load_json("all-content.json")
    if data is None:
        return jsonify({"error": "all-content.json not found"}), 404
    return jsonify(data)

# ----------------------------------------------------------------------
#  Search endpoint (still useful for advanced queries)
# ----------------------------------------------------------------------
@app.route("/api/search", methods=["GET"])
def search():
    query = request.args.get("q", "").lower()
    if not query:
        return jsonify([])
    results = []
    categories = ["movies", "dubbed-movies", "hindi", "asian-movies", "anime", "series", "tvshows", "asian-series"]
    for cat in categories:
        data = load_json(f"{cat}.json")
        if not data:
            continue
        for item_id, item in data.items():
            title = item.get("Title", "").lower()
            if query in title:
                results.append({
                    "id": item_id,
                    "title": item.get("Title"),
                    "image": item.get("Image Source"),
                    "category": cat
                })
    return jsonify(results[:50])

# ----------------------------------------------------------------------
#  Episodes endpoints
# ----------------------------------------------------------------------
@app.route("/api/episodes/<category>/<content_id>", methods=["GET"])
def get_episodes(category: str, content_id: str):
    if category not in ["series", "tvshows", "asian-series"]:
        return jsonify({"error": "Invalid category. Use series, tvshows, or asian-series"}), 400
    episodes = load_episodes(category, content_id)
    if episodes is None:
        return jsonify({"error": f"Episodes not found for {category}/{content_id}"}), 404
    return jsonify(episodes)

@app.route("/api/anime-episodes/<anime_id>", methods=["GET"])
def get_anime_episodes(anime_id: str):
    episodes = load_episodes("anime", anime_id)
    if episodes is None:
        return jsonify({"error": f"Episodes not found for anime/{anime_id}"}), 404
    return jsonify(episodes)

# ----------------------------------------------------------------------
#  Health and video extraction endpoints
# ----------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "scraper_ready": SCRAPER_READY,
        "cache": cache.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

@app.route("/extract", methods=["POST"])
def extract():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"error": "Missing 'url' field"}), 400
    page_url = data["url"].strip()
    if not page_url:
        return jsonify({"error": "Empty URL"}), 400
    cache_key = page_url
    cached = cache.get(cache_key)
    if cached:
        return jsonify({
            "stream_url": cached["stream_url"],
            "quality_options": cached["quality_options"],
            "cached": True,
            "cache_key": cache_key
        })
    if not SCRAPER_READY:
        return jsonify({"error": "Scraper not available"}), 503
    try:
        stream_url = extract_video_source(page_url, headless=True)
        if not stream_url:
            return jsonify({"error": "Could not extract video stream"}), 404
        quality_options = ["Auto"]
        if "master.m3u8" in stream_url:
            quality_options = ["1080p", "720p", "480p", "360p"]
        cache.set(cache_key, stream_url, quality_options)
        return jsonify({
            "stream_url": stream_url,
            "quality_options": quality_options,
            "cached": False,
            "cache_key": cache_key
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------------------------------------------------------------
#  Run the server
# ----------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port)