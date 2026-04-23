from base64 import b64encode
from time import sleep
import requests
from bs4 import BeautifulSoup, ResultSet, Tag
from urllib.parse import quote
from typing import Optional, Callable, Union, List, Dict
import json
import re
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from requests.exceptions import ConnectionError, TooManyRedirects, ReadTimeout, ChunkedEncodingError
from requests import Response
from os import environ
from PIL import Image

# Scrapling for undetectable browser automation (primary)
try:
    from scrapling.fetchers import StealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False
    print("Warning: scrapling not installed. Install with: pip install scrapling[all]")

# curl_cffi as fast fallback (sometimes works)
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    print("Warning: curl_cffi not installed. Install with: pip install curl_cffi")

# Playwright for video source extraction (only used directly)
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: Playwright not installed. Run: pip install playwright && playwright install chromium")

# ========== RATE LIMITING & IMPERSONATION SETTINGS ==========
DEBUG = True                     # Set to True for verbose output
REQUEST_DELAY = 3.0               # Base seconds between page requests
JITTER = 0.5                      # Random +/- seconds added to delay
MAX_RETRIES = 3
BACKOFF_FACTOR = 2

# Rotating impersonations for curl_cffi (fallback)
IMPERSONATIONS = ["chrome", "chrome110", "chrome124", "edge101", "safari15_5"]

# For other sites (CimaNow, HDW) – using strings instead of Selenium's By
CIMA_NOW_SELECTOR = ("class name", "owl-head.owl-loaded.owl-drag")

FILE_NAMES = ["movies", "anime", "asian-series",
              "series", "tvshows", "arabic-series",
              "arabic-movies"]

HDW_FILE_NAMES = ["hdwmovies", "series", "arabic-movies", "arabic-series"]

FASEL_BASE_URL = "https://www.fasel-hd.cam/"

DEFAULT_HDW_SELECTOR = ("class name", "top-brand")

AKWAM_GENRES = {
    "87": "Ramadan",
    "30": "Animated",
    "18": "Action",
    "71": "Dubbed",
    "72": "Netflix",
    "20": "Comedy",
    "35": "Thriller",
    "34": "Mystery",
    "33": "Family",
    "88": "Kids",
    "32": "Sports",
    "25": "War",
    "89": "Short",
    "43": "Fantasy",
    "24": "Science Fiction",
    "31": "Musical",
    "29": "Biography",
    "28": "Documentary",
    "27": "Romance",
    "26": "History",
    "23": "Drama",
    "22": "Horror",
    "21": "Crime",
    "19": "Adventure",
    "91": "Western"
}

CIMA_NOW_GENRES = {
    "تشويق": "Suspense",
    "درامي": "Drama",
    "اكشن": "Action",
    "رعب": "Horror",
    "كوميدى": "Comedy",
    "مغامرة": "Adventure",
    "ترفيهي": "Entertainment",
    "غنائي": "Musical",
    "مسابقات": "Competitions",
    "اجتماعي": "Social",
    "جريمة": "Crime",
    "اثارة": "Thriller",
    "رومانسى": "Romance",
    "عائلي": "Family",
    "كوميدي": "Comedy",
    "درامى": "Drama"
}

try:
    with open("./output/image-indices.json", "r") as fp:
        IMAGE_SOURCES = json.load(fp)
except FileNotFoundError:
    IMAGE_SOURCES = {}

cookie_lock = Lock()

# Default headers (fallback for curl_cffi)
headers: dict = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9,ar;q=0.8",
    "accept-encoding": "gzip, deflate, br",
    "connection": "keep-alive",
    "upgrade-insecure-requests": "1",
}

# ========== SYNC REQUEST HANDLER (Scrapling with .body.decode) ==========

def get_website_safe(webpage_url: str, max_retries: int = MAX_RETRIES) -> Optional[Response]:
    """
    Fetch a webpage using Scrapling's StealthyFetcher with wait_for_selector.
    Falls back to curl_cffi if Scrapling fails.
    Returns a requests.Response-like object for compatibility.
    """
    # Try Scrapling first (with proper waiting for dynamic content)
    if SCRAPLING_AVAILABLE:
        for attempt in range(max_retries):
            try:
                resp = StealthyFetcher.fetch(
                    webpage_url,
                    headless=True,
                    wait_for_selector=".blockMovie, .postDiv, body",
                    timeout=60000  # 60 seconds
                )
                if resp and resp.status == 200:
                    # Extract HTML from .body (bytes) or fallback
                    html = resp.body.decode('utf-8') if hasattr(resp, 'body') else resp.text
                    if html:
                        fake_resp = requests.Response()
                        fake_resp.status_code = 200
                        fake_resp._content = html.encode('utf-8')
                        return fake_resp
                if DEBUG:
                    print(f"Scrapling attempt {attempt+1} status {resp.status if resp else 'None'}")
            except Exception as e:
                if DEBUG:
                    print(f"Scrapling error on attempt {attempt+1}: {e}")
            if attempt < max_retries - 1:
                sleep(BACKOFF_FACTOR ** attempt)
        if DEBUG:
            print("Scrapling failed, falling back to curl_cffi")

    # Fallback to curl_cffi
    if CURL_CFFI_AVAILABLE:
        for attempt in range(max_retries):
            impersonation = IMPERSONATIONS[attempt % len(IMPERSONATIONS)]
            try:
                response = curl_requests.get(
                    webpage_url,
                    impersonate=impersonation,
                    timeout=30,
                    allow_redirects=True
                )
                if response.status_code == 200:
                    resp = requests.Response()
                    resp.status_code = 200
                    resp._content = response.content
                    return resp
                elif response.status_code == 403:
                    if DEBUG:
                        print(f"curl_cffi 403 with {impersonation} on {webpage_url}, attempt {attempt+1}")
                    if attempt < max_retries - 1:
                        sleep(BACKOFF_FACTOR ** attempt)
                else:
                    if DEBUG:
                        print(f"curl_cffi status {response.status_code} with {impersonation}")
            except Exception as e:
                if DEBUG:
                    print(f"curl_cffi error with {impersonation}: {e}")
            if attempt < max_retries - 1:
                sleep(BACKOFF_FACTOR ** attempt)
    if DEBUG:
        print(f"Failed to fetch {webpage_url} after {max_retries} retries")
    return None

# ========== ASYNC HELPERS (for scrapers that need async) ==========

async def get_website_safe_async(url: str, max_retries: int = MAX_RETRIES) -> Optional[str]:
    """Async wrapper for get_website_safe (runs sync fetcher in thread)."""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        resp = await loop.run_in_executor(
            executor,
            get_website_safe,
            url,
            max_retries
        )
    if resp:
        return resp.text
    return None

async def get_number_of_pages_async(url: str) -> int:
    """Async version: get total pages using Scrapling directly."""
    html = await get_website_safe_async(url)
    if not html:
        return 1
    soup = BeautifulSoup(html, "html.parser")
    pagination = soup.select_one("ul.pagination")
    if pagination:
        page_links = pagination.find_all("a", class_="page-link")
        numbers = []
        for link in page_links:
            text = link.text.strip()
            if text.isdigit():
                numbers.append(int(text))
        if numbers:
            return max(numbers)
        last_link = pagination.find("a", string="»")
        if last_link and last_link.get("href"):
            match = re.search(r'/page/(\d+)', last_link["href"])
            if match:
                return int(match.group(1))
    max_page = 1
    for link in soup.find_all('a', href=True):
        match = re.search(r'/page/(\d+)', link['href'])
        if match:
            max_page = max(max_page, int(match.group(1)))
    return max_page if max_page > 1 else 1

async def get_category_page_async(category_url: str, page: int = 1) -> List[dict]:
    """Async version: fetch a category page and extract movies."""
    page_url = get_paginated_url(category_url, page)
    html = await get_website_safe_async(page_url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return get_latest_movies(soup)

async def scrape_category_pages_async(category_name: str, start_page: int = 1, end_page: Optional[int] = None) -> List[dict]:
    """Async version: scrape all pages of a category with rate limiting."""
    base_url = FASEL_BASE_URL + category_name
    if end_page is None:
        end_page = await get_number_of_pages_async(base_url)
    all_movies = []
    for page in range(start_page, end_page + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        await asyncio.sleep(delay)
        movies = await get_category_page_async(base_url, page)
        all_movies.extend(movies)
        if DEBUG:
            print(f"Scraped {category_name} page {page}/{end_page}, found {len(movies)} movies")
    return all_movies

# ========== VIDEO SOURCE EXTRACTION (PLAYWRIGHT ONLY) ==========

def extract_video_source(video_page_url: str, timeout: int = 30) -> Optional[str]:
    """
    Use Playwright (headless Chromium) to load the video page and extract
    the actual stream URL from JavaScript variables, iframes, or video elements.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError("Playwright not installed. Run: pip install playwright && playwright install chromium")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(video_page_url, timeout=timeout * 1000)

            page.wait_for_selector("video, iframe, script[src*='player'], .player, #player", timeout=timeout * 1000)

            html = page.content()
            patterns = [
                r'(?:file|source|src|video_url|mp4|m3u8)["\']?\s*[:=]\s*["\']([^"\']+\.(?:mp4|m3u8|m3u)[^"\']*)',
                r'["\'](https?://[^"\']+\.(?:mp4|m3u8|m3u)[^"\']*)["\']',
                r'data-(?:src|file)=["\']([^"\']+\.(?:mp4|m3u8))',
                r'<video[^>]+src=["\']([^"\']+)["\']',
                r'<source[^>]+src=["\']([^"\']+)["\']',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    browser.close()
                    return matches[0]

            iframes = page.query_selector_all("iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src")
                if src and ("embed" in src or "player" in src):
                    browser.close()
                    return src

            browser.close()
            return None

    except Exception as e:
        if DEBUG:
            print(f"Playwright extraction error: {e}")
        return None

# ========== PAGINATION HELPERS (SYNC) ==========

def get_paginated_url(category_url: str, page: int) -> str:
    base = re.sub(r'/page/\d+/?$', '', category_url.rstrip('/'))
    if page == 1:
        return base
    return f"{base}/page/{page}/"

def get_number_of_pages(url: str) -> int:
    webpage = get_website_safe(url)
    if not webpage:
        return 1
    soup = BeautifulSoup(webpage.content, "html.parser")
    pagination = soup.select_one("ul.pagination")
    if pagination:
        page_links = pagination.find_all("a", class_="page-link")
        numbers = []
        for link in page_links:
            text = link.text.strip()
            if text.isdigit():
                numbers.append(int(text))
        if numbers:
            return max(numbers)
        last_link = pagination.find("a", string="»")
        if last_link and last_link.get("href"):
            match = re.search(r'/page/(\d+)', last_link["href"])
            if match:
                return int(match.group(1))
    max_page = 1
    for link in soup.find_all('a', href=True):
        match = re.search(r'/page/(\d+)', link['href'])
        if match:
            max_page = max(max_page, int(match.group(1)))
    return max_page if max_page > 1 else 1

def scrape_category_pages(category_name: str, start_page: int = 1, end_page: Optional[int] = None) -> List[dict]:
    base_url = FASEL_BASE_URL + category_name
    if end_page is None:
        end_page = get_number_of_pages(base_url)
    all_movies = []
    for page in range(start_page, end_page + 1):
        delay = REQUEST_DELAY + random.uniform(-JITTER, JITTER)
        if delay < 0.5:
            delay = 0.5
        sleep(delay)
        url = get_paginated_url(base_url, page)
        if DEBUG:
            print(f"Scraping {category_name} page {page}/{end_page}: {url}")
        movies = get_category_page_rendered(base_url, page)
        all_movies.extend(movies)
    return all_movies

# ========== FASELHD METADATA EXTRACTION ==========

def get_latest_movies(soup: BeautifulSoup) -> list[dict]:
    """Extract movies from homepage (.blockMovie) or category page (.postDiv)."""
    movies = []
    movie_divs = soup.select(".blockMovie") or soup.select(".postDiv")
    for movie_div in movie_divs:
        link_tag = movie_div.find("a")
        if not link_tag:
            continue
        img = link_tag.find("img")
        image_url = img.get("data-src", img.get("src", "")) if img else ""
        title_div = link_tag.find("div", class_="h5") or link_tag.find("div", class_="h1")
        title = title_div.text.strip() if title_div else ""
        quality_span = link_tag.find("span", class_="quality")
        quality = quality_span.text.strip() if quality_span else ""
        imdb_span = link_tag.find("span", class_="pImdb") or link_tag.find("span", class_="bimdb")
        imdb_rating = None
        if imdb_span:
            try:
                rating_text = imdb_span.text.strip()
                if rating_text and rating_text != "N/A":
                    imdb_rating = float(rating_text)
            except ValueError:
                pass
        views_span = link_tag.find("span", class_="pViews") or link_tag.find("span", class_="bviews")
        views = 0
        if views_span:
            views_text = views_span.text.strip().replace("٬", "").replace(",", "")
            try:
                views = int(views_text)
            except ValueError:
                pass
        link = link_tag.get("href", "")
        content_type = "movies"
        if "anime-movies" in link:
            content_type = "anime-movies"
        elif "asian-movies" in link:
            content_type = "asian-movies"
        elif "hindi" in link:
            content_type = "hindi-movies"
        movies.append({
            "title": title,
            "link": link,
            "image": image_url,
            "quality": quality,
            "imdb_rating": imdb_rating,
            "views": views,
            "content_type": content_type
        })
    return movies

def get_latest_episodes(soup: BeautifulSoup) -> list[dict]:
    episodes = []
    for ep_div in soup.select(".epDivHome"):
        link_tag = ep_div.find("a", class_="epHomeImg")
        content_div = ep_div.find("div", class_="epHomeContent")
        link = ""
        image_url = ""
        if link_tag:
            link = link_tag.get("href", "")
            img = link_tag.find("img")
            image_url = img.get("data-src", img.get("src", "")) if img else ""
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
            title_div = ep_div.find("div", class_="h4")
            if title_div:
                title = title_div.text.strip()
        status_span = ep_div.find("span", class_="epStatus")
        status = status_span.text.strip() if status_span else ""
        content_type = "series"
        if "anime-episodes" in link:
            content_type = "anime"
        elif "asian-episodes" in link:
            content_type = "asian-series"
        episodes.append({
            "title": title,
            "link": link,
            "image": image_url,
            "status": status,
            "content_type": content_type
        })
    return episodes

def get_featured_content(soup: BeautifulSoup) -> list[dict]:
    featured = []
    for slide in soup.select(".swiper-slide"):
        title_div = slide.find("div", class_="h1 mb-1")
        if not title_div:
            continue
        title_link = title_div.find("a")
        if not title_link:
            continue
        title = title_link.text.strip()
        link = title_link.get("href", "")
        poster_div = slide.find("div", class_="poster")
        image_url = ""
        if poster_div:
            img = poster_div.find("img")
            image_url = img.get("src", "") if img else ""
        if not image_url:
            slide_img = slide.find("div", class_="slideImg")
            if slide_img and slide_img.get("style"):
                style = slide_img.get("style", "")
                if "url(" in style:
                    image_url = style.split("url(")[1].split(")")[0].strip("\"'")
        imdb_span = slide.find("span", class_="imdbRate")
        imdb_rating = None
        if imdb_span:
            try:
                imdb_rating = float(imdb_span.text.strip())
            except ValueError:
                pass
        categories = [cat.text.strip() for cat in slide.select(".slideCats span")]
        description = ""
        desc_p = slide.find("p")
        if desc_p:
            description = desc_p.text.strip()
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
            "image": image_url,
            "imdb_rating": imdb_rating,
            "categories": categories,
            "description": description,
            "content_type": content_type
        })
    return featured

def get_latest_movies_from_homepage() -> list[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")
    return get_latest_movies(soup)

def get_latest_episodes_from_homepage() -> list[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")
    return get_latest_episodes(soup)

def get_featured_content_from_homepage() -> list[dict]:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")
    return get_featured_content(soup)

def get_all_homepage_content() -> dict:
    resp = get_website_safe(FASEL_BASE_URL + "main")
    if not resp:
        return {"movies": [], "episodes": [], "featured": []}
    soup = BeautifulSoup(resp.content, "html.parser")
    return {
        "movies": get_latest_movies(soup),
        "episodes": get_latest_episodes(soup),
        "featured": get_featured_content(soup)
    }

def get_category_page_rendered(category_url: str, page: int = 1) -> list[dict]:
    url = get_paginated_url(category_url, page)
    resp = get_website_safe(url)
    if not resp:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")
    return get_latest_movies(soup)

# ========== LEGACY HELPER FUNCTIONS (unchanged) ==========

def split_into_ranges(number_of_ranges: int, range_end: int, range_start: int = 0) -> list[tuple[int, int]]:
    number_to_be_split = range_end - range_start
    number_per_chunk = number_to_be_split // number_of_ranges
    ranges_list = []
    for number in range(number_of_ranges):
        begin = range_start + (number_per_chunk * number)
        if number == number_of_ranges - 1:
            end = range_end
        else:
            end = range_start + (number_per_chunk * (number + 1))
        if (begin + 1, end + 1) in ranges_list or (begin + 1 == end + 1):
            continue
        else:
            ranges_list.append((begin + 1, end + 1))
    return ranges_list

def remove_arabic_chars(string: str) -> str:
    return string.encode("ascii", "ignore").decode().strip()

def fix_url(url: str) -> str:
    return quote(url.split("?")[0]).replace("%3A", ":")

def get_content_format(soup: BeautifulSoup) -> str:
    try:
        content_format = soup.find("i", class_="fas fa-play-circle").find_next_sibling().text
        return content_format if content_format.isascii() else "N/A"
    except AttributeError:
        return "N/A"

def get_content_id(soup: BeautifulSoup) -> Optional[str]:
    try:
        return remove_arabic_chars(soup.find("i", class_="fas fa-dot-circle").parent.text.replace(":", "").replace("#", ""))
    except AttributeError:
        return None

def upload_image(image_url: str, content_id: str, get_image: Callable[[str], Response]) -> str:
    if DEBUG:
        print(content_id)
    if content_id in IMAGE_SOURCES:
        return IMAGE_SOURCES[content_id]
    if image_url == "":
        return "https://imgpile.com/images/TPDrVl.jpg"
    image = get_image(image_url)
    image_path = f"./output/{content_id}"
    if ".webp" in image_url:
        with open(image_path + ".webp", "wb") as handler:
            handler.write(image.content)
        jpg_image = Image.open(image_path + ".webp").convert("RGB")
        jpg_image.save(image_path + ".jpg", "jpeg")
        with open(image_path + ".jpg", "rb") as fp:
            base64_image = fp.read()
    else:
        base64_image = b64encode(image.content).decode("utf8")
    headers_imgur = {"Authorization": f"Client-ID {environ.get('IMGUR_CLIENT_ID')}"}
    data = {"image": base64_image}
    try:
        return requests.post("https://api.imgur.com/3/image", headers=headers_imgur, data=data).json()["data"]["link"]
    except Exception:
        return "https://imgpile.com/images/TPDrVl.jpg"

def remove_year(title: str) -> str:
    if title[-4:].isdigit() and len(title) > 4:
        title = title.replace(title[-5:], "")
    return title

def get_content_title(soup_result: ResultSet) -> str:
    title = remove_year(remove_arabic_chars(soup_result.find("div", class_="h1").text))
    return title

def get_genres(soup: BeautifulSoup) -> Union[list[str], str]:
    try:
        genre_tags = soup.find("i", class_="far fa-folders").find_next_siblings("a")
        genres = [tag["href"].split("/")[-1].capitalize() for tag in genre_tags]
    except AttributeError:
        genres = []
    return genres

# --- Akwam, HDW, CimaNow legacy functions (kept for compatibility) ---

def akwam_get_website_safe(url: str) -> Response:
    response = None
    while response is None:
        try:
            response = requests.get(url)
        except (ConnectionError, ChunkedEncodingError):
            response = None
    return response

def akwam_get_last_page_number(url: str) -> int:
    main_page_source = akwam_get_website_safe(url)
    soup = BeautifulSoup(main_page_source.content, "html.parser")
    last_page = int(soup.find_all("a", class_="page-link")[-3].text)
    return last_page

def split_anchor_links(response: Response) -> list[list[str]]:
    soup = BeautifulSoup(response.content, "html.parser")
    anchor_tags = soup.find_all("a", class_="icn play")
    links = [tag["href"] for tag in anchor_tags]
    links_ranges = split_into_ranges(6, len(links))
    splitted_links = [links[links_range[0] - 1: links_range[1] - 1] for links_range in links_ranges]
    return splitted_links

def akwam_get_genres(soup: BeautifulSoup) -> Union[list[str], str]:
    genre_tags = soup.find_all("a", class_="badge badge-pill badge-light ml-2")
    try:
        genre_ids = [tag["href"].split("=")[-1] for tag in genre_tags]
    except TypeError:
        return []
    genres = [AKWAM_GENRES[key] for key in genre_ids]
    return genres

def hdw_get_last_page_number(url: str, selector: tuple[str, str] = DEFAULT_HDW_SELECTOR) -> int:
    webpage = get_website_safe(url)
    soup = BeautifulSoup(webpage.content, "html.parser")
    return int(soup.find_all("a", class_="page-link")[-2].text)

def hdw_get_image_source(div: Tag) -> str:
    return div.find_previous_sibling("a").find("img")["src"]

def hdw_get_rating(div: Tag) -> Optional[str]:
    try:
        rating = div.find_previous_sibling("a").find("span", class_="float-left yellow").text.replace(",", ".").strip()
    except AttributeError:
        rating = None
    return rating

def hdw_get_genres(div: Tag) -> list[str]:
    return list(map(lambda genre: genre.strip(), div.find("span", class_="content-views").text.split(", ")))

def clean_iframe_source(iframe_source: str) -> str:
    try:
        return iframe_source.split("=")[2].replace("&img", "")
    except IndexError:
        return ""

def get_tmdb_id(title: str, genre: str) -> Optional[str]:
    params = {"query": title, "api_key": environ.get("TMDB_API_KEY")}
    request_url = "https://api.themoviedb.org/3/search/movie" if genre == "movies" else "https://api.themoviedb.org/3/search/tv"
    resp = requests.get(request_url, params=params)
    try:
        tmdb_id = resp.json().get("results")[0].get("id")
    except IndexError:
        tmdb_id = None
    return tmdb_id

def cima_now_get_last_page(soup: BeautifulSoup):
    return int(soup.find_all("ul")[-1].find_all("li")[-1].text)

def cima_now_get_sources(soup: BeautifulSoup):
    anchors = soup.find("ul", {"id": "download"}).find("li").find_all("a")
    return [{anchor.text.split()[0]: anchor["href"]} for anchor in anchors]