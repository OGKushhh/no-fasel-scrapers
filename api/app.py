"""
AbdoBest Video Extraction API
Flask wrapper around Common.py's extract_video_source()
"""

import os
import time
import threading
from typing import Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone

# ----------------------------------------------------------------------
#  In‑memory cache with TTL
# ----------------------------------------------------------------------
class Cache:
    def __init__(self, default_ttl: int = 21600):  # 6 hours
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
#  App setup
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins (React frontend)

cache = Cache(default_ttl=21600)

# Import the video extraction function
try:
    from Common import extract_video_source
    SCRAPER_READY = True
except ImportError as e:
    SCRAPER_READY = False
    print(f"[ERROR] Cannot import Common.py: {e}")
    # Define a dummy function to avoid crashes
    def extract_video_source(url, headless=True):
        raise NotImplementedError("Common.py not available")

# ----------------------------------------------------------------------
#  Health check endpoint (used by frontend)
# ----------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "scraper_ready": SCRAPER_READY,
        "cache": cache.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

# ----------------------------------------------------------------------
#  Main extraction endpoint (matches frontend expectations)
# ----------------------------------------------------------------------
@app.route("/extract", methods=["POST"])
def extract():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify({"error": "Missing 'url' field"}), 400

    page_url = data["url"].strip()
    if not page_url:
        return jsonify({"error": "Empty URL"}), 400

    # Use the page URL as cache key (stable for the video page)
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
        # Call the extraction function (returns .m3u8 URL)
        stream_url = extract_video_source(page_url, headless=True)
        if not stream_url:
            return jsonify({"error": "Could not extract video stream"}), 404

        # Basic quality options (can be improved by inspecting the m3u8)
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