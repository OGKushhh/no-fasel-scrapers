---
title: abdobest-api
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# FaselHD API Service

This is a Flask API service that provides access to scraped movie and series data from FaselHD, including on‑demand video stream extraction.

## Endpoints

- `/api/movies` - List all movies
- `/api/anime` - List all anime
- `/api/series` - List all series
- `/api/tvshows` - List all TV shows
- `/api/asian-series` - List all Asian series
- `/api/featured` - Get featured content
- `/api/search?q=...` - Search across all content
- `/api/stream?url=...` - Extract video stream URL on‑demand