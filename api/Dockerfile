FROM python:3.11-slim

# 1. Install system compilers + base libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libffi-dev libssl-dev \
    libxml2-dev libxslt1-dev \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Create non‑root user (but we'll still run as root for now)
RUN useradd -m -u 1000 user

# 3. Set Playwright browser cache to user's home directory
ENV PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright

# 4. Switch to user to install Python packages (so they go to user's site-packages)
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# 5. Copy requirements and install Python dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Switch back to root to install Playwright system dependencies and browser
USER root
RUN playwright install-deps && \
    playwright install chromium

# 7. Ensure the browser cache directory is owned by the user
RUN chown -R user:user /home/user/.cache

# 8. Switch back to user for the running application
USER user

# 9. Copy the rest of the application
COPY --chown=user . .

# 10. Expose port and run
EXPOSE 7860
ENV PORT=7860
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--timeout", "180", "--workers", "1", "--threads", "2", "app:app"]