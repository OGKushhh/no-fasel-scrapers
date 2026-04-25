"""
AbdoBest Video Extraction API
Flask wrapper around Common.py's get_video_stream_url()
"""

import os
import time
import threading
import email.utils  # Added to replace broken Werkzeug functions
from typing import Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta, timezone

# --- Replacement for removed Werkzeug functions ---
def dump_date(d):
    """Replaces werkzeug.http.dump_date"""
    return email.utils.format_datetime(d)

def parse_date(s):
    """Replaces werkzeug.http.parse_date"""
    return email.utils.parsedate_to_datetime(s)

# ─── In-memory cache with TTL ───────────────────────────────────────────
class Cache:
    def __init__(self, default_ttl: int = 21600):
        self._store: dict = {}
        self._locks: dict = {}
        self._default_ttl = default_ttl
        self._mutex = threading.Lock()

    def get(self, key: str) -> Optional[dict]:
        with self._mutex:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() > entry["expires_at"]:
                del self._store[key]
                return None
            return {"video_url": entry["video_url"], "quality_options": entry["quality_options"]}

    def set(self, key: str, video_url: str, quality_options: list = None, ttl: int = None):
        ttl = ttl or self._default_ttl
        with self._mutex:
            self._store[key] = {
                "video_url": video_url,
                "quality_options": quality_options or [],
                "expires_at": time.time() + ttl,
                "created_at": time.time(),
            }

    def stats(self) -> dict:
        with self._mutex:
            now = time.time()
            valid = sum(1 for e in self._store.values() if now < e["expires_at"])
            return {"total_entries": len(self._store), "valid_entries": valid, "default_ttl": self._default_ttl}

# ─── App setup ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
CORS(app, resources={r"/*": {"origins": "*"}})
cache = Cache(default_ttl=21600)

try:
    from Common import get_video_stream_url
    SCRAPER_READY = True
except ImportError as e:
    SCRAPER_READY = False
    print(f"[WARN] Cannot import Common.py: {e}")

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

    url = data.get("url", "").strip()
    cache_key = str(hash(url))

    cached = cache.get(cache_key)
    if cached:
        return jsonify({**cached, "cache_key": cache_key, "cached": True})

    if not SCRAPER_READY:
        return jsonify({"error": "Scraper not available"}), 503

    try:
        video_url = get_video_stream_url(url, headless=True)
        if not video_url:
            return jsonify({"error": "Could not extract video URL"}), 404

        quality_options = ["1080p", "720p", "480p", "360p"] if "master.m3u8" in video_url else ["Auto"]
        cache.set(cache_key, video_url, quality_options)

        return jsonify({
            "video_url": video_url,
            "quality_options": quality_options,
            "cache_key": cache_key,
            "cached": False
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port)