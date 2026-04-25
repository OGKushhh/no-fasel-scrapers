#!/bin/bash
# Render build script – installs Python dependencies and Playwright browsers

pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browsers (Chromium is enough for extraction)
playwright install chromium