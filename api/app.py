import json
import os
import sys
from flask import Flask, jsonify, request
from flask_cors import CORS

# Add current directory to path so we can import Common.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from Common import extract_video_source

app = Flask(__name__)
CORS(app)  # Allow all origins (for development; restrict later if needed)

DATA_DIR = os.environ.get("DATA_DIR", "./data")

def load_json_file(filename):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return {"error": f"File {filename} not found"}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "FaselHD API (abdobest-api) is running",
        "endpoints": [
            "/api/movies",
            "/api/anime",
            "/api/series",
            "/api/tvshows",
            "/api/asian-series",
            "/api/featured",
            "/api/search?q=...",
            "/api/stream?url=..."
        ]
    })

# ---------- Static data endpoints ----------
@app.route("/api/movies", methods=["GET"])
def get_movies():
    movie_id = request.args.get("id")
    data = load_json_file("movies.json")
    if "error" in data:
        return jsonify(data), 404
    if movie_id:
        return jsonify(data.get(movie_id, {"error": "Movie not found"}))
    return jsonify(data)

@app.route("/api/anime", methods=["GET"])
def get_anime():
    anime_id = request.args.get("id")
    data = load_json_file("anime.json")
    if "error" in data:
        return jsonify(data), 404
    if anime_id:
        return jsonify(data.get(anime_id, {"error": "Anime not found"}))
    return jsonify(data)

@app.route("/api/series", methods=["GET"])
def get_series():
    series_id = request.args.get("id")
    data = load_json_file("series.json")
    if "error" in data:
        return jsonify(data), 404
    if series_id:
        return jsonify(data.get(series_id, {"error": "Series not found"}))
    return jsonify(data)

@app.route("/api/tvshows", methods=["GET"])
def get_tvshows():
    show_id = request.args.get("id")
    data = load_json_file("tvshows.json")
    if "error" in data:
        return jsonify(data), 404
    if show_id:
        return jsonify(data.get(show_id, {"error": "TV show not found"}))
    return jsonify(data)

@app.route("/api/asian-series", methods=["GET"])
def get_asian_series():
    series_id = request.args.get("id")
    data = load_json_file("asian-series.json")
    if "error" in data:
        return jsonify(data), 404
    if series_id:
        return jsonify(data.get(series_id, {"error": "Asian series not found"}))
    return jsonify(data)

@app.route("/api/featured", methods=["GET"])
def get_featured():
    data = load_json_file("featured-content.json")
    if "error" in data:
        return jsonify(data), 404
    return jsonify(data)

@app.route("/api/search", methods=["GET"])
def search():
    query = request.args.get("q", "").lower()
    if not query:
        return jsonify([])
    results = []
    categories = ["movies", "anime", "series", "tvshows", "asian-series"]
    for cat in categories:
        data = load_json_file(f"{cat}.json")
        if "error" in data:
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

# ---------- Video stream extraction endpoint (on‑demand) ----------
@app.route("/api/stream", methods=["GET"])
def get_stream():
    video_url = request.args.get("url")
    if not video_url:
        return jsonify({"error": "Missing 'url' parameter"}), 400
    
    try:
        stream_url = extract_video_source(video_url, headless=True)
        if stream_url:
            return jsonify({"stream_url": stream_url})
        else:
            return jsonify({"error": "Could not extract stream URL"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))