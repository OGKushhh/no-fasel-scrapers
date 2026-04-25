import json
import logging
import os
import random
import re
import time
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Optional, Callable, Union, List, Dict
from urllib.parse import quote, unquote
from PIL import Image
import requests
from bs4 import BeautifulSoup, ResultSet, Tag
from requests import Response
from requests.exceptions import ConnectionError, TooManyRedirects, ReadTimeout, ChunkedEncodingError

# ----------------------------------------------------------------------
#  Logging configuration
# ----------------------------------------------------------------------
logging.basicConfig(
    filename='scraper_errors.log',
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ----------------------------------------------------------------------
#  Stealth fetching – Scrapling (primary) + curl_cffi (fallback)
#  NO Playwright here – this is thread‑safe.
# ----------------------------------------------------------------------
try:
    from scrapling.fetchers import StealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False
    print("Warning: scrapling not installed. Run: pip install scrapling[all]")

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    print("Warning: curl_cffi not installed. Run: pip install curl_cffi")

# Playwright ONLY for video extraction – will be imported only inside that function.
# Not imported at top level to avoid greenlet issues.
# try:
#     from playwright.sync_api import sync_playwright
# except ImportError: ...

# ----------------------------------------------------------------------
#  Constants & settings
# ----------------------------------------------------------------------
DEBUG = True                       # Set False for production runs
REQUEST_DELAY = 2.0                # seconds between page requests
JITTER = 0.5                       # random ± seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 2
IMPERSONATIONS = ["chrome", "chrome110", "chrome124", "edge101", "safari15_5"]

FASEL_BASE_URL = "https://www.fasel-hd.cam/"

# For other sites (leave as is)
CIMA_NOW_SELECTOR = ("class name", "owl-head.owl-loaded.owl-drag")
FILE_NAMES = ["movies", "anime", "asian-series", "series", "tvshows", "arabic-series", "arabic-movies"]
HDW_FILE_NAMES = ["hdwmovies", "series", "arabic-movies", "arabic-series"]
DEFAULT_HDW_SELECTOR = ("class name", "top-brand")

AKWAM_GENRES = {
    "87": "Ramadan", "30": "Animated", "18": "Action", "71": "Dubbed",
    "72": "Netflix", "20": "Comedy", "35": "Thriller", "34": "Mystery",
    "33": "Family", "88": "Kids", "32": "Sports", "25": "War", "89": "Short",
    "43": "Fantasy", "24": "Science Fiction", "31": "Musical", "29": "Biography",
    "28": "Documentary", "27": "Romance", "26": "History", "23": "Drama",
    "22": "Horror", "21": "Crime", "19": "Adventure", "91": "Western"
}

CIMA_NOW_GENRES = {
    "تشويق": "Suspense", "درامي": "Drama", "اكشن": "Action", "رعب": "Horror",
    "كوميدى": "Comedy", "مغامرة": "Adventure", "ترفيهي": "Entertainment",
    "غنائي": "Musical", "مسابقات": "Competitions", "اجتماعي": "Social",
    "جريمة": "Crime", "اثارة": "Thriller", "رومانسى": "Romance",
    "عائلي": "Family", "كوميدي": "Comedy", "درامى": "Drama"
}

# Genre mapping for FaselHD (Arabic -> English)
FASEL_GENRE_MAP = {
    "أكشن": "Action",
    "اكشن": "Action",
    "دراما": "Drama",
    "كوميدي": "Comedy",
    "كوميدى": "Comedy",
    "رعب": "Horror",
    "إثارة": "Thriller",
    "اثارة": "Thriller",
    "مغامرات": "Adventure",
    "مغامرة": "Adventure",
    "خيال علمي": "Science Fiction",
    "جريمة": "Crime",
    "رومانسية": "Romance",
    "رومانسي": "Romance",
    "رومانسى": "Romance",
    "تاريخي": "History",
    "سيرة ذاتية": "Biography",
    "وثائقي": "Documentary",
    "عائلي": "Family",
    "رياضي": "Sports",
    "حرب": "War",
    "غموض": "Mystery",
    "فانتازيا": "Fantasy",
    "موسيقى": "Music",
    "موسيقي": "Music",
    "أنميشن": "Animation",
    "انيميشن": "Animation",
    "غربي": "Western",
    "مسابقات": "Competitions",
    "تلفزيون الواقع": "Reality-TV",
    "ترفيهي": "Entertainment",
    "اجتماعي": "Social",
}

try:
    with open("./output/image-indices.json", "r") as fp:
        IMAGE_SOURCES = json.load(fp)
except FileNotFoundError:
    IMAGE_SOURCES = {}

cookie_lock = Lock()
headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9,ar;q=0.8",
}

# ----------------------------------------------------------------------
#  Core fetching function (synchronous, thread‑safe: Scrapling + curl_cffi)
# ----------------------------------------------------------------------
def get_website_safe(webpage_url: str, max_retries: int = MAX_RETRIES) -> Optional[Response]:
    """Fetch a page using Scrapling (stealth) or fallback to curl_cffi."""
    # Try Scrapling first (stateless, thread‑safe)
    if SCRAPLING_AVAILABLE:
        for attempt in range(max_retries):
            try:
                resp = StealthyFetcher.fetch(
                    webpage_url,
                    headless=True,
                    wait_for_selector=".blockMovie, .postDiv, body",
                    timeout=60000
                )
                if resp and resp.status == 200:
                    html = resp.body.decode('utf-8') if hasattr(resp, 'body') else resp.text
                    if html:
                        fake = requests.Response()
                        fake.status_code = 200
                        fake._content = html.encode('utf-8')
                        return fake
            except Exception as e:
                if DEBUG:
                    print(f"Scrapling error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(BACKOFF_FACTOR ** attempt)
        if DEBUG:
            print("Scrapling failed, falling back to curl_cffi")

    # Fallback to curl_cffi (thread‑safe)
    if CURL_CFFI_AVAILABLE:
        for attempt in range(max_retries):
            imp = IMPERSONATIONS[attempt % len(IMPERSONATIONS)]
            try:
                r = curl_requests.get(webpage_url, impersonate=imp, timeout=30)
                if r.status_code == 200:
                    fake = requests.Response()
                    fake.status_code = 200
                    fake._content = r.content
                    return fake
            except Exception as e:
                if DEBUG:
                    print(f"curl_cffi error: {e}")
            if attempt < max_retries - 1:
                time.sleep(BACKOFF_FACTOR ** attempt)

    logging.warning(f"Failed to fetch {webpage_url}")
    return None

# ----------------------------------------------------------------------
#  Pagination helpers
# ----------------------------------------------------------------------
def get_paginated_url(category_url: str, page: int) -> str:
    base = re.sub(r'/page/\d+/?$', '', category_url.rstrip('/'))
    return base if page == 1 else f"{base}/page/{page}/"

def get_number_of_pages(url: str) -> int:
    resp = get_website_safe(url)
    if not resp:
        return 1
    soup = BeautifulSoup(resp.text, "html.parser")
    pagination = soup.select_one("ul.pagination")
    if pagination:
        last_link = pagination.find("a", string="»")
        if last_link and last_link.get("href"):
            m = re.search(r'/page/(\d+)', last_link["href"])
            if m:
                return int(m.group(1))
        numbers = [int(a.text.strip()) for a in pagination.find_all("a", class_="page-link") if a.text.strip().isdigit()]
        if numbers:
            return max(numbers)
    # fallback
    max_page = 1
    for a in soup.find_all('a', href=True):
        m = re.search(r'/page/(\d+)', a['href'])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page if max_page > 1 else 1

# ----------------------------------------------------------------------
#  Metadata extraction from detail pages
# ----------------------------------------------------------------------
def clean_genre(genre: str) -> str:
    """Decode percent‑encoded Arabic strings."""
    try:
        decoded = unquote(genre)
        return decoded if '%' not in decoded else genre
    except:
        return genre

def get_content_id(soup: BeautifulSoup) -> Optional[str]:
    try:
        return remove_arabic_chars(soup.find("i", class_="fas fa-dot-circle").parent.text.replace(":", "").replace("#", ""))
    except AttributeError:
        return None

def get_content_format(soup: BeautifulSoup) -> str:
    try:
        cf = soup.find("i", class_="fas fa-play-circle").find_next_sibling().text
        return cf if cf.isascii() else "N/A"
    except AttributeError:
        return "N/A"

def get_genres_both(soup: BeautifulSoup) -> dict:
    """Return dict with 'en' (English) and 'ar' (Arabic decoded) genre lists."""
    try:
        genre_tags = soup.find("i", class_="far fa-folders").find_next_siblings("a")
        raw_genres = [tag["href"].split("/")[-1].capitalize() for tag in genre_tags]
        ar_genres = [clean_genre(g) for g in raw_genres]
        en_genres = [FASEL_GENRE_MAP.get(g, g) for g in ar_genres]
        return {"ar": ar_genres, "en": en_genres}
    except AttributeError:
        return {"ar": [], "en": []}

def clean_iframe_source(iframe_src):
    """Safely extract the actual video URL from an iframe src attribute."""
    if not iframe_src or "=" not in iframe_src:
        return ""
    try:
        return iframe_src.split("=")[2].replace("&img", "")
    except (IndexError, AttributeError):
        return ""

def remove_arabic_chars(s: str) -> str:
    return s.encode("ascii", "ignore").decode().strip()

def remove_year(title: str) -> str:
    if title[-4:].isdigit() and len(title) > 4:
        title = title.replace(title[-5:], "")
    return title

def get_content_title(soup_result: ResultSet) -> str:
    title = remove_year(remove_arabic_chars(soup_result.find("div", class_="h1").text))
    return title

def extract_country(soup: BeautifulSoup) -> Optional[str]:
    flag_icon = soup.find('i', class_='far fa-flag')
    if flag_icon:
        parent_span = flag_icon.find_parent('span')
        if parent_span:
            link = parent_span.find('a', rel='tag')
            if link:
                return link.text.strip()
    text = soup.get_text()
    match = re.search(r'دول الأنتاج\s*:\s*([^\n]+)', text)
    return match.group(1).strip() if match else None

def extract_runtime(soup: BeautifulSoup) -> Optional[int]:
    clock = soup.find('i', class_='far fa-clock')
    if clock:
        parent = clock.find_parent('span')
        if parent:
            m = re.search(r'(\d+)', parent.get_text())
            if m:
                return int(m.group(1))
    meta = soup.find('meta', attrs={'itemprop': 'duration'})
    if meta and meta.get('content'):
        dur = meta['content']
        m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur)
        if m:
            h = int(m.group(1)) if m.group(1) else 0
            mn = int(m.group(2)) if m.group(2) else 0
            return h * 60 + mn
    return None

# ----------------------------------------------------------------------
#  Image upload (Imgur)
# ----------------------------------------------------------------------
def upload_image(image_url: str, content_id: str, get_image: Callable[[str], Response]) -> str:
    if DEBUG:
        print(content_id)
    if content_id in IMAGE_SOURCES:
        return IMAGE_SOURCES[content_id]
    if not image_url:
        return "https://imgpile.com/images/TPDrVl.jpg"
    image = get_image(image_url)
    image_path = f"./output/{content_id}"
    if ".webp" in image_url:
        with open(image_path + ".webp", "wb") as f:
            f.write(image.content)
        jpg = Image.open(image_path + ".webp").convert("RGB")
        jpg.save(image_path + ".jpg", "jpeg")
        with open(image_path + ".jpg", "rb") as f:
            b64 = f.read()
    else:
        b64 = b64encode(image.content).decode("utf8")
    imgur_headers = {"Authorization": f"Client-ID {environ.get('IMGUR_CLIENT_ID')}"}
    data = {"image": b64}
    try:
        res = requests.post("https://api.imgur.com/3/image", headers=imgur_headers, data=data)
        return res.json()["data"]["link"]
    except Exception:
        return "https://imgpile.com/images/TPDrVl.jpg"

# ----------------------------------------------------------------------
#  Video source extraction (on‑demand) – uses Playwright, separate from metadata
#  This function is called only when a user requests a video.
# ----------------------------------------------------------------------
TEMP_PROFILE = os.path.abspath("./chrome_fresh_profile")
AD_DOMAINS = [
    "googletagmanager.com", "doubleclick.net", "googleadservices.com",
    "google-analytics.com", "popads.net", "adsterra.com", "exponential.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com", "madurird.com",
    "acscdn.com", "crumpetprankerstench.com", "propellerads.com", "clickadu.com"
]

def get_video_stream_url(page_url: str, headless: bool = True, max_attempts: int = 7) -> Optional[str]:
    """Launch a stealth browser, intercept .m3u8 request, click play button."""
    from playwright.sync_api import sync_playwright  # imported only here
    captured_url = None
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=TEMP_PROFILE,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--window-size=1280,720"
            ],
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        # block ads
        def block_ads(route, request):
            if any(domain in request.url for domain in AD_DOMAINS):
                route.abort()
                return
            route.continue_()
        page.route("**/*", block_ads)
        page.on("popup", lambda popup: popup.close())

        if DEBUG:
            print(f"[Video] Loading {page_url}")
        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)

        # locate player iframe
        iframe = page.frame(name="player_iframe")
        if not iframe:
            iframe_elem = page.query_selector("iframe[name='player_iframe']")
            if iframe_elem:
                iframe = iframe_elem.content_frame()
        if not iframe:
            if DEBUG:
                print("[Video] Could not find player iframe")
            context.close()
            return None

        try:
            iframe.wait_for_selector("body", timeout=15000)
        except:
            context.close()
            return None

        play_selector = ".jw-icon.jw-icon-display.jw-button-color.jw-reset"
        video_selector = "video"

        # intercept .m3u8
        def intercept(route, request):
            nonlocal captured_url
            if ".m3u8" in request.url:
                if "master.m3u8" in request.url:
                    captured_url = request.url
                    if DEBUG:
                        print(f"[Video] MASTER m3u8: {captured_url}")
                elif captured_url is None and "playlist.m3u8" in request.url:
                    captured_url = request.url
                    if DEBUG:
                        print(f"[Video] Fallback playlist: {captured_url}")
            route.continue_()
        page.route("**/*", intercept)

        for attempt in range(max_attempts):
            if captured_url:
                break
            if DEBUG:
                print(f"[Video] Click attempt {attempt+1}")
            try:
                iframe.click(play_selector, force=True, timeout=3000)
            except:
                try:
                    iframe.click(video_selector, force=True)
                except:
                    pass
            time.sleep(1.5)
            for p in context.pages:
                if p != page:
                    p.close()

        # wait a few seconds after clicks
        for _ in range(30):
            if captured_url:
                break
            time.sleep(0.5)

        context.close()
        return captured_url

def extract_video_source(page_url: str, headless: bool = True) -> str:
    """Synchronous wrapper – returns m3u8 URL or empty string."""
    url = get_video_stream_url(page_url, headless=headless)
    return url if url else ""

# ----------------------------------------------------------------------
#  Convenience sync functions for metadata scraping
# ----------------------------------------------------------------------
def get_latest_movies(soup: BeautifulSoup) -> List[dict]:
    movies = []
    divs = soup.select(".blockMovie") or soup.select(".postDiv")
    for div in divs:
        link = div.find("a")
        if not link:
            continue
        img = link.find("img")
        img_src = img.get("data-src") or img.get("src", "") if img else ""
        title_elem = link.find("div", class_="h5") or link.find("div", class_="h1")
        title = title_elem.text.strip() if title_elem else ""
        quality_span = link.find("span", class_="quality")
        quality = quality_span.text.strip() if quality_span else ""
        imdb_span = link.find("span", class_="pImdb") or link.find("span", class_="bimdb")
        imdb_rating = None
        if imdb_span:
            try:
                imdb_rating = float(imdb_span.text.strip())
            except:
                pass
        views_span = link.find("span", class_="pViews") or link.find("span", class_="bviews")
        views = 0
        if views_span:
            views_text = views_span.text.strip().replace("٬", "").replace(",", "")
            try:
                views = int(views_text)
            except:
                pass
        movies.append({
            "title": title,
            "link": link["href"],
            "image": img_src,
            "quality": quality,
            "imdb_rating": imdb_rating,
            "views": views,
            "content_type": "movies"
        })
    return movies

def get_latest_episodes(soup: BeautifulSoup) -> List[dict]:
    episodes = []
    for ep in soup.select(".epDivHome"):
        link_tag = ep.find("a", class_="epHomeImg")
        content_div = ep.find("div", class_="epHomeContent")
        link = ""
        image = ""
        if link_tag:
            link = link_tag.get("href", "")
            img = link_tag.find("img")
            image = img.get("data-src") or img.get("src", "") if img else ""
        elif content_div and content_div.find("a"):
            link = content_div.find("a").get("href", "")
        if not link:
            continue
        title = ""
        if content_div:
            title_div = content_div.find("div", class_="h4")
            if title_div:
                title = title_div.text.strip()
        if not title:
            title_div = ep.find("div", class_="h4")
            if title_div:
                title = title_div.text.strip()
        status_span = ep.find("span", class_="epStatus")
        status = status_span.text.strip() if status_span else ""
        content_type = "series"
        if "anime-episodes" in link:
            content_type = "anime"
        elif "asian-episodes" in link:
            content_type = "asian-series"
        episodes.append({
            "title": title,
            "link": link,
            "image": image,
            "status": status,
            "content_type": content_type
        })
    return episodes

def get_featured_content(soup: BeautifulSoup) -> List[dict]:
    featured = []
    for slide in soup.select(".swiper-slide"):
        title_div = slide.find("div", class_="h1 mb-1")
        if not title_div:
            continue
        a = title_div.find("a")
        if not a:
            continue
        title = a.text.strip()
        link = a.get("href", "")
        poster = slide.find("div", class_="poster")
        img_url = ""
        if poster:
            img = poster.find("img")
            img_url = img.get("src", "") if img else ""
        if not img_url:
            slide_img = slide.find("div", class_="slideImg")
            if slide_img and slide_img.get("style"):
                style = slide_img.get("style", "")
                if "url(" in style:
                    img_url = style.split("url(")[1].split(")")[0].strip("\"'")
        imdb_span = slide.find("span", class_="imdbRate")
        imdb = None
        if imdb_span:
            try:
                imdb = float(imdb_span.text.strip())
            except:
                pass
        categories = [c.text.strip() for c in slide.select(".slideCats span")]
        desc = ""
        p = slide.find("p")
        if p:
            desc = p.text.strip()
        content_type = "movies"
        if "/anime" in link:
            content_type = "anime"
        elif "/asian" in link:
            content_type = "asian-series"
        elif "/series" in link or "/episodes" in link:
            content_type = "series"
        featured.append({
            "title": title,
            "link": link,
            "image": img_url,
            "imdb_rating": imdb,
            "categories": categories,
            "description": desc,
            "content_type": content_type
        })
    return featured

def get_most_viewed_movies(soup: BeautifulSoup) -> List[dict]:
    """Extract the 'الأفلام الاكثر مشاهدة' (most viewed movies) slider from homepage."""
    most_viewed = []
    slider = soup.select_one('.viewsOrderSlider')
    if not slider:
        return most_viewed
    items = slider.select('.itemviews')
    for item in items:
        post_div = item.select_one('.postDiv')
        if not post_div:
            continue
        link_tag = post_div.find('a')
        if not link_tag:
            continue
        link = link_tag.get('href', '')
        title_elem = post_div.select_one('.h1')
        title = title_elem.text.strip() if title_elem else 'Unknown'
        img = post_div.find('img')
        img_src = img.get('data-src', img.get('src', '')) if img else ''
        quality_span = post_div.select_one('.quality')
        quality = quality_span.text.strip() if quality_span else ''
        imdb_span = post_div.select_one('.pImdb')
        imdb_rating = None
        if imdb_span:
            try:
                imdb_rating = float(imdb_span.text.strip())
            except:
                pass
        views_span = post_div.select_one('.pViews')
        views = 0
        if views_span:
            views_text = views_span.text.strip().replace('٬', '').replace(',', '')
            try:
                views = int(views_text)
            except:
                pass
        most_viewed.append({
            "title": title,
            "link": link,
            "image": img_src,
            "quality": quality,
            "imdb_rating": imdb_rating,
            "views": views,
        })
    return most_viewed

def get_latest_movies_from_homepage() -> List[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_latest_movies(soup)

def get_latest_episodes_from_homepage() -> List[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_latest_episodes(soup)

def get_featured_content_from_homepage() -> List[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_featured_content(soup)

def get_all_homepage_content() -> dict:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return {"movies": [], "episodes": [], "featured": []}
    soup = BeautifulSoup(resp.text, "html.parser")
    return {
        "movies": get_latest_movies(soup),
        "episodes": get_latest_episodes(soup),
        "featured": get_featured_content(soup)
    }

def get_category_page_rendered(category_url: str, page: int = 1) -> List[dict]:
    url = get_paginated_url(category_url, page)
    resp = get_website_safe(url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return get_latest_movies(soup)

# ----------------------------------------------------------------------
#  Legacy functions – Akwam, HDW, CimaNow (unchanged)
# ----------------------------------------------------------------------
def split_into_ranges(num_ranges: int, end: int, start: int = 0) -> list:
    step = (end - start) // num_ranges
    ranges = []
    for i in range(num_ranges):
        b = start + step * i
        e = end if i == num_ranges - 1 else start + step * (i + 1)
        if (b+1, e+1) not in ranges and b+1 != e+1:
            ranges.append((b+1, e+1))
    return ranges

def fix_url(url: str) -> str:
    return quote(url.split("?")[0]).replace("%3A", ":")

def akwam_get_website_safe(url: str) -> Response:
    while True:
        try:
            return requests.get(url)
        except (ConnectionError, ChunkedEncodingError):
            continue

def akwam_get_last_page_number(url: str) -> int:
    soup = BeautifulSoup(akwam_get_website_safe(url).content, "html.parser")
    return int(soup.find_all("a", class_="page-link")[-3].text)

def split_anchor_links(response: Response) -> list:
    soup = BeautifulSoup(response.content, "html.parser")
    links = [a["href"] for a in soup.find_all("a", class_="icn play")]
    ranges = split_into_ranges(6, len(links))
    return [links[r[0]-1 : r[1]-1] for r in ranges]

def akwam_get_genres(soup: BeautifulSoup) -> list:
    tags = soup.find_all("a", class_="badge badge-pill badge-light ml-2")
    try:
        ids = [t["href"].split("=")[-1] for t in tags]
        return [AKWAM_GENRES[i] for i in ids]
    except:
        return []

def hdw_get_last_page_number(url: str, selector=None) -> int:
    resp = get_website_safe(url)
    soup = BeautifulSoup(resp.content, "html.parser")
    return int(soup.find_all("a", class_="page-link")[-2].text)

def hdw_get_image_source(div: Tag) -> str:
    return div.find_previous_sibling("a").find("img")["src"]

def hdw_get_rating(div: Tag) -> Optional[str]:
    try:
        return div.find_previous_sibling("a").find("span", class_="float-left yellow").text.replace(",", ".").strip()
    except:
        return None

def hdw_get_genres(div: Tag) -> list:
    return [g.strip() for g in div.find("span", class_="content-views").text.split(", ")]

def get_tmdb_id(title: str, genre: str) -> Optional[str]:
    api_key = environ.get("TMDB_API_KEY")
    if not api_key:
        return None
    url = "https://api.themoviedb.org/3/search/movie" if genre == "movies" else "https://api.themoviedb.org/3/search/tv"
    params = {"query": title, "api_key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=10)
        return resp.json().get("results", [{}])[0].get("id")
    except:
        return None

def cima_now_get_last_page(soup: BeautifulSoup) -> int:
    return int(soup.find_all("ul")[-1].find_all("li")[-1].text)

def cima_now_get_sources(soup: BeautifulSoup) -> list:
    anchors = soup.find("ul", {"id": "download"}).find("li").find_all("a")
    return [{a.text.split()[0]: a["href"]} for a in anchors]