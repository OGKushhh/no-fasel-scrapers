"""
Test script for AbdoBest video extraction — synced with VideoExtractor.tsx v7
Run: python test_extract.py [URL_or_ID]

  Examples:
    python test_extract.py
    python test_extract.py https://www.fasel-hd.cam/episodes/some-slug
    python test_extract.py /episodes/some-slug
    python test_extract.py 12345          # numeric → fasel-hd.cam/?p=12345

Requirements:
    pip install playwright requests beautifulsoup4
    playwright install chromium
"""

import sys
import time

# ── Same UA as VideoExtractor.tsx WebView (Android Chrome) ──────────────────
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Mobile Safari/537.36"
)

BASE_URL = "https://www.fasel-hd.cam"

# ── Exact BLOCKED_DOMAINS from VideoExtractor.tsx ───────────────────────────
BLOCKED_DOMAINS = [
    "s8ey.com", "wplmtckt.com", "reffpa.com", "1xlite-11151.pro", "pyppo.com",
    "googletagmanager.com", "doubleclick.net", "googleadservices.com",
    "google-analytics.com", "popads.net", "adsterra.com", "exponential.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com", "madurird.com",
    "acscdn.com", "crumpetprankerstench.com", "propellerads.com",
    "clickadu.com", "adnxs.com", "ads.yahoo.com",
    "notix.io", "pushwoosh.com", "onesignal.com",
    "tmll7.com", "1xlite-24510.bar", "mahjong778jpx.site",
    "browsecoherentunrefined.com",
]

# ── Allowed domains from VideoExtractor.tsx (anything else gets flagged) ─────
ALLOWED_DOMAINS = [
    "fasel-hd.cam", "faselhd.com", "faselhd.tv",
    "faselhdx.bid", "faselhdx.com",
    "scdns.io",
    "jwpcdn.com", "jwplayer.com",
    "cdn.jwplayer.com", "content.jwplatform.com", "ssl.p.jwpcdn.com",
    "cloudfront.net", "akamaized.net", "akamai.net",
    "fastly.net", "llnwd.net", "edgesuite.net",
]


def resolve_url(arg: str) -> str:
    """Turn an ID, path, or full URL into a full URL."""
    arg = arg.strip()
    if arg.isdigit():
        return f"{BASE_URL}/?p={arg}"
    if arg.startswith("http"):
        return arg
    if arg.startswith("/"):
        return BASE_URL + arg
    return arg


def pick_url() -> str:
    """Interactive URL/ID picker when no CLI arg given."""
    print("Enter a FaselHD URL, path, or numeric ID.")
    print(f"  Base: {BASE_URL}")
    print("  Examples:")
    print("    https://www.fasel-hd.cam/episodes/marry-murderer-...-1")
    print("    /episodes/marry-murderer-...-1")
    print("    12345\n")
    raw = input("URL / path / ID: ").strip()
    if not raw:
        print("[ERROR] Nothing entered — exiting.")
        sys.exit(1)
    return resolve_url(raw)


def test_extract(page_url: str, headless: bool = True):
    from playwright.sync_api import sync_playwright

    captured_urls: list[str] = []
    all_video_requests: list[dict] = []
    # New-tab / popup ad URLs
    popup_urls: list[str] = []
    # Requests to unknown domains (not in allowed, not in blocked) — suspicious
    unknown_domain_requests: list[str] = []

    print(f"\n{'='*65}")
    print(f"URL      : {page_url}")
    print(f"UA       : {USER_AGENT}")
    print(f"Headless : {headless}")
    print(f"{'='*65}\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="./chrome_test_profile",
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--window-size=1280,720",
            ],
            viewport={"width": 1280, "height": 720},
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        # ── Block same BLOCKED_DOMAINS as VideoExtractor ─────────────
        def block_ads(route, request):
            url = request.url
            if any(d in url for d in BLOCKED_DOMAINS):
                print(f"  [BLOCKED] {url[:90]}")
                route.abort()
                return
            route.continue_()

        page.route("**/*", block_ads)

        # ── Capture popup / new-tab URLs (VideoExtractor blocks these) ─
        def on_popup(popup):
            popup_url = popup.url or "(blank)"
            popup_urls.append(popup_url)
            print(f"  [POPUP/NEW-TAB] {popup_url[:90]}")
            popup.close()

        context.on("page", on_popup)

        # ── Intercept network for diagnostics ────────────────────────
        def on_request(request):
            url = request.url
            # m3u8 capture
            if ".m3u8" in url:
                print(f"  [NETWORK m3u8] {url}")
                captured_urls.append(url)
            # Any video-adjacent request
            if any(x in url for x in [".m3u8", ".mp4", ".ts", "stream", "video", "player", "embed"]):
                all_video_requests.append({"url": url, "type": request.resource_type})
            # Flag requests to domains not in allowed list and not blocked
            if not any(d in url for d in BLOCKED_DOMAINS) and \
               not any(d in url for d in ALLOWED_DOMAINS) and \
               not url.startswith("data:") and not url.startswith("blob:"):
                unknown_domain_requests.append(url)

        page.on("request", on_request)

        # ── Load page ─────────────────────────────────────────────────
        print("[1] Loading page...")
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"  [ERROR] Page load failed: {e}")
            context.close()
            return None

        print("[2] Page loaded. Waiting 2s for JS to settle...")
        time.sleep(2)

        # ── Iframe diagnostics ────────────────────────────────────────
        print("\n[3] Checking iframes...")
        iframes_info = page.evaluate("""() => {
            const iframes = document.querySelectorAll('iframe');
            return Array.from(iframes).map(f => ({
                name: f.name, id: f.id,
                src: f.src || f.getAttribute('data-src') || '',
                class: f.className
            }));
        }""")

        if iframes_info:
            print(f"  Found {len(iframes_info)} iframe(s):")
            for i, fr in enumerate(iframes_info):
                print(f"    [{i}] name='{fr['name']}' id='{fr['id']}' "
                      f"src='{fr['src'][:80]}' class='{fr['class']}'")
        else:
            print("  [WARNING] No iframes found on page!")

        # ── server_tokens (tabs-ul) — same logic as CLICK_JS ─────────
        print("\n[4] Extracting server token URLs from tabs-ul...")
        server_tokens = page.evaluate("""() => {
            var serverTabs = document.querySelectorAll('.tabs-ul li');
            var tokens = [];
            serverTabs.forEach(function(li) {
                var oc = li.getAttribute('onclick') || '';
                var m = oc.match(/player_iframe\\.location\\.href\\s*=\\s*['"]([^'"]+)['"]/);
                if (m && m[1]) tokens.push(m[1]);
            });
            return tokens;
        }""")
        if server_tokens:
            print(f"  Found {len(server_tokens)} server token(s):")
            for t in server_tokens:
                print(f"    {t[:100]}")
        else:
            print("  None — either no tabs-ul or no tokens found")

        # ── Direct video elements ─────────────────────────────────────
        print("\n[5] Checking for direct <video> elements...")
        videos = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('video')).map(v => ({
                src: v.src, currentSrc: v.currentSrc, class: v.className
            }));
        }""")
        if videos:
            for v in videos:
                print(f"  src='{v['src']}' currentSrc='{v['currentSrc']}'")
        else:
            print("  None")

        # ── Locate player_iframe (same selector priority as CLICK_JS) ─
        print("\n[6] Locating player_iframe...")
        iframe_elem = page.query_selector("iframe[name='player_iframe']")
        iframe = None
        if iframe_elem:
            print("  [OK] Found by name='player_iframe'")
            iframe = iframe_elem.content_frame()
        else:
            iframe_elem = page.query_selector("iframe#player_iframe")
            if iframe_elem:
                print("  [OK] Found by id='player_iframe'")
                iframe = iframe_elem.content_frame()
            else:
                iframe_elem = page.query_selector("iframe")
                if iframe_elem:
                    src = iframe_elem.get_attribute("src") or iframe_elem.get_attribute("data-src") or ""
                    print(f"  [FALLBACK] First iframe, src='{src[:80]}'")
                    iframe = iframe_elem.content_frame()
                else:
                    print("  [FAIL] No iframe found at all")

        # ── Navigate to video_player URL (mirrors CLICK_JS STEP 1) ───
        if iframe:
            src_attr = (iframe_elem.get_attribute("data-src") or
                        iframe_elem.get_attribute("src") or "")
            if "video_player" in src_attr:
                print(f"\n[7] Navigating WebView to video_player page: {src_attr[:80]}")
                try:
                    iframe.goto(src_attr, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    print(f"  [WARN] iframe.goto failed: {e}")
            else:
                print(f"\n[7] iframe src doesn't contain video_player — skipping navigation")

            # ── Click play inside iframe ──────────────────────────────
            print("\n[8] Clicking play inside iframe (up to 7 attempts)...")
            PLAY_SELECTORS = [
                ".jw-icon-display",
                ".jw-icon.jw-icon-display",
                ".jw-display-icon-container",
                "[class*='jw-icon'][class*='play']",
                ".jw-media video",
                "video",
                "[class*='play'][class*='btn']",
                "[class*='play'][class*='button']",
                "[class*='video-play']",
            ]
            try:
                iframe.wait_for_selector("body", timeout=10000)

                # Dump iframe DOM elements for debugging
                iframe_els = iframe.evaluate("""() => {
                    var els = document.querySelectorAll('button, [class*="play"], [class*="jw"], video');
                    return Array.from(els).slice(0, 12).map(b => ({
                        tag: b.tagName, class: b.className, id: b.id
                    }));
                }""")
                if iframe_els:
                    print("  Elements inside iframe:")
                    for el in iframe_els:
                        print(f"    <{el['tag']}> class='{el['class']}' id='{el['id']}'")
                else:
                    print("  [WARNING] Iframe body is empty — player may not have loaded")

                for attempt in range(7):
                    if captured_urls:
                        break
                    for sel in PLAY_SELECTORS:
                        try:
                            iframe.click(sel, force=True, timeout=2000)
                            print(f"  Attempt {attempt+1}: clicked '{sel}'")
                            break
                        except:
                            continue
                    time.sleep(1.5)
                    # Close any popups spawned during play
                    for pg in context.pages:
                        if pg != page:
                            popup_url = pg.url
                            popup_urls.append(f"[during-click] {popup_url}")
                            print(f"  [POPUP during click] {popup_url[:80]}")
                            pg.close()

            except Exception as e:
                print(f"  [ERROR] Iframe interaction failed: {e}")
        else:
            # No iframe — try clicking directly on page (same VideoExtractor fallback)
            print("\n[8] No iframe — clicking play directly on main page...")
            for attempt in range(5):
                if captured_urls:
                    break
                for sel in [".jw-icon-display", "video"]:
                    try:
                        page.click(sel, force=True, timeout=2000)
                        print(f"  Attempt {attempt+1}: clicked '{sel}'")
                        break
                    except:
                        continue
                time.sleep(1.5)

        # ── Wait for delayed m3u8 ─────────────────────────────────────
        print("\n[9] Waiting up to 15s for m3u8 to appear...")
        for _ in range(30):
            if captured_urls:
                break
            time.sleep(0.5)

        # ── Results ───────────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("RESULTS")
        print(f"{'='*65}")

        if captured_urls:
            print(f"[SUCCESS] {len(captured_urls)} m3u8 URL(s):")
            for u in captured_urls:
                print(f"  {u}")
        else:
            print("[FAILED] No m3u8 URL captured")

        print(f"\nAll video-adjacent requests ({len(all_video_requests)}):")
        if all_video_requests:
            for r in all_video_requests:
                print(f"  [{r['type']}] {r['url'][:100]}")
        else:
            print("  None — player may not have loaded at all")

        if popup_urls:
            print(f"\n[AD POPUPS / NEW TABS] {len(popup_urls)} popup(s) detected:")
            for u in popup_urls:
                print(f"  {u[:100]}")
        else:
            print("\n[AD POPUPS] None detected")

        # Unknown domain requests — helpful for finding new ad domains
        suspicious = [u for u in unknown_domain_requests
                      if not any(skip in u for skip in [
                          "fasel-hd.cam", "faselhd", "jwp", "jwplayer",
                          "cloudfront", "akamai", "fastly", "google.com/recaptcha",
                          "fonts.g", "gstatic", "ajax.googleapis"
                      ])]
        if suspicious:
            # Deduplicate by domain for brevity
            seen_domains: set[str] = set()
            unique: list[str] = []
            for u in suspicious:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(u).netloc
                    if domain not in seen_domains:
                        seen_domains.add(domain)
                        unique.append(u)
                except:
                    unique.append(u)
            print(f"\n[UNKNOWN DOMAINS — potential new ads] {len(unique)} unique domain(s):")
            for u in unique[:20]:
                print(f"  {u[:100]}")

        # Save HTML dump
        html = page.content()
        with open("page_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nPage HTML → page_dump.html ({len(html):,} chars)")
        print("Search for 'iframe', 'player_token', 'm3u8', 'popup' to debug\n")

        context.close()
        return captured_urls[0] if captured_urls else None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        page_url = resolve_url(sys.argv[1])
    else:
        page_url = pick_url()

    # Set headless=False to watch the browser live
    result = test_extract(page_url, headless=True)

    print(f"{'='*65}")
    print(f"FINAL: {result if result else 'FAILED — check page_dump.html'}")
    print(f"{'='*65}")
