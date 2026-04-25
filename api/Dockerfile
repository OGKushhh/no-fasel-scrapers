# Use Python 3.11 for better compatibility with curl_cffi
FROM python:3.11-slim

# 1. Install EVERYTHING needed for compilers and Playwright as ROOT
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libffi-dev libssl-dev \
    libxml2-dev libxslt1-dev \
    wget gnupg ca-certificates \
    libnss3 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 2. Setup Hugging Face User
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# 3. Install Python libs (This will now succeed because GCC is present)
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Install Playwright browser
RUN playwright install chromium

# 5. Copy all files (Ensures Common.py and /data are present)
COPY --chown=user . .

# 6. Final Configuration
EXPOSE 7860
ENV PORT=7860

# We use a 180s timeout because Playwright takes time to boot
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--timeout", "180", "--workers", "1", "--threads", "2", "app:app"]