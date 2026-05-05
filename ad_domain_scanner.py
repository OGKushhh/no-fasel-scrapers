#!/usr/bin/env python3
"""
ad_domain_scanner.py
Discover new ad/tracker domains by scanning a given URL with a mobile user agent.
Logs unrecognized domains to 'new_ad_domains.log' and prints them.
"""

import sys
import os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# ---------- Configuration ----------
# Known ad domains (start with your existing list; you can extend from Common.py if needed)
KNOWN_AD_DOMAINS = {
    "googletagmanager.com", "doubleclick.net", "googleadservices.com",
    "google-analytics.com", "popads.net", "adsterra.com", "exponential.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com", "madurird.com",
    "acscdn.com", "crumpetprankerstench.com", "propellerads.com", "clickadu.com"
}

# Mobile user agent (iPhone 12 Pro)
MOBILE_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
# Alternatively, test with a more generic Android UA:
# MOBILE_USER_AGENT = "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.210 Mobile Safari/537.36"

# Output log file
LOG_FILE = "new_ad_domains.log"

# ---------- Helper functions ----------
def extract_domain(url: str) -> str:
    """Extract registered domain from a URL (e.g., sub.example.com -> example.com)."""
    parsed = urlparse(url)
    domain = parsed.netloc
    parts = domain.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain

def is_likely_ad(request) -> bool:
    """
    Heuristic to filter normal resources (fonts, CSS, etc.). 
    Returns True if the request is likely an ad/tracker.
    """
    # Resource types commonly used for ads/trackers
    ad_resource_types = ['image', 'media', 'script', 'xmlhttprequest']
    if request.resource_type not in ad_resource_types:
        return False
    url = request.url.lower()
    keywords = ['ads', 'track', 'analytics', 'banner', 'adserver', 'metrics', 'pixel', 'beacon', 'doubleclick']
    for kw in keywords:
        if kw in url:
            return True
    return False

# ---------- Main scanner ----------
def scan_url(target_url: str, headless: bool = True):
    print(f"[*] Scanning {target_url} with mobile UA...")
    discovered = set()
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="/tmp/playwright_ad_scan",  # temporary
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 375, "height": 812},   # typical mobile viewport
            user_agent=MOBILE_USER_AGENT
        )
        page = context.new_page()
        
        def log_request(route, request):
            domain = extract_domain(request.url)
            if domain and domain not in KNOWN_AD_DOMAINS and is_likely_ad(request):
                if domain not in discovered:
                    discovered.add(domain)
                    print(f"[!] New potential ad domain: {domain} (from {request.url})")
                    # Append to log file
                    with open(LOG_FILE, "a") as f:
                        f.write(f"{domain}\n")
            route.continue_()
        
        page.route("**/*", log_request)
        
        # Load the page, wait for network idle for 5 seconds to catch after-load requests
        page.goto(target_url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)  # extra time for lazy-loaded content
        context.close()
    
    if discovered:
        print(f"\n✅ Discovered {len(discovered)} new domains. Saved to {LOG_FILE}")
    else:
        print("\nℹ️ No new ad domains found.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python ad_domain_scanner.py <url>")
        print("Example: python ad_domain_scanner.py https://www.fasel-hd.cam/movies/...")
        sys.exit(1)
    
    url = sys.argv[1]
    if not url.startswith("http"):
        url = "https://" + url
    scan_url(url, headless=True)