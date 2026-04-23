from sys import setrecursionlimit
from time import perf_counter
from bs4 import BeautifulSoup
from googletrans import Translator
from Common import *
from concurrent.futures import ThreadPoolExecutor
import json
from httpx import ReadTimeout

setrecursionlimit(25000)

try:
    with open("./output/anime.json", "r") as fp:
        old_animes = json.load(fp)
except FileNotFoundError:
    old_animes = {}


def clean_anime_title(anime_title: str) -> str:
    """Translate the anime title and remove all unnecessary characters"""
    translation = None
    while translation is None:
        try:
            translation = Translator().translate(
                anime_title, src="ar", dest="en").text
        except ReadTimeout:
            translation = None
        except Exception as e:
            if DEBUG:
                print(f"Translation error: {e}")
            translation = None

    cleaned_anime_title = translation.replace("Anime", "").replace(
        "anime", "").replace("?", "").strip().encode("ascii", "ignore").decode()

    return cleaned_anime_title


def get_iframe_source(episodes: list[str]) -> dict:
    """Gets the video source for each episode"""
    episodes_dict = {}

    for episode in episodes:
        try:
            episode_url = episode["href"]
            episode_page = get_website_safe(episode_url)

            if episode_page is not None:
                soup = BeautifulSoup(episode_page.content, "html.parser")
            else:
                continue

            episode_id = get_content_id(soup)

            if episode_id is None:
                # Try alternative method for episode ID
                try:
                    episode_id = episode_url.split("/")[-1]
                except:
                    continue

            try:
                iframeSource = soup.find("iframe")["src"]
            except TypeError:
                continue

            # Extract episode number from the episode text
            episode_text = episode.text if episode.text else ""
            try:
                episode_number = int(remove_arabic_chars(episode_text).strip())
            except ValueError:
                # Try to extract from URL
                try:
                    episode_number = int(episode_url.split("-")[-1])
                except:
                    episode_number = len(episodes_dict) + 1

            episodes_dict[episode_id] = {
                "Episode Number": episode_number,
                "Source": iframeSource,
            }
        except Exception as e:
            if DEBUG:
                print(f"Error getting iframe source: {e}")
            continue

    return episodes_dict


def scrape_episodes(current_number_of_episodes: int, episodes_sources: list[str], start_episode: int = 0) -> dict:
    """Scrapes all the episodes of the anime and their sources"""
    episode_ranges = split_into_ranges(
        8, current_number_of_episodes, start_episode)

    splitted_episodes_list = [
        episodes_sources[episode_range[0] - 1: episode_range[1] - 1]
        for episode_range in episode_ranges
    ]

    with ThreadPoolExecutor() as executor:
        results = executor.map(get_iframe_source, splitted_episodes_list)

    master_dict = {}
    for result in results:
        master_dict.update(result)

    return master_dict


def scrape_anime(page_range: tuple, category_url: str = None) -> dict:
    """Scrapes all the animes in the page range provided
    
    Args:
        page_range: Tuple of (start_page, end_page)
        category_url: The base category URL (e.g., "https://www.fasel-hd.cam/anime")
    """
    anime_dict = {}
    
    # Use provided category URL or default to /anime
    if category_url is None:
        category_url = FASEL_BASE_URL + "anime"

    for page in range(page_range[0], page_range[1]):
        try:
            # Use get_paginated_url for correct URL construction
            page_url = get_paginated_url(category_url, page)
            main_page = get_website_safe(page_url)
            
            if main_page is None:
                if DEBUG:
                    print(f"Failed to fetch page {page}: {page_url}")
                continue
                
            soup = BeautifulSoup(main_page.content, "html.parser")
            
            # Updated to match new HTML structure
            anime_divs = soup.find_all(
                "div", class_="col-xl-2 col-lg-2 col-md-3 col-sm-3")

            for anime_div in anime_divs:
                try:
                    anime_page_source = anime_div.find("a")["href"]

                    anime_page = get_website_safe(anime_page_source)
                    soup = BeautifulSoup(anime_page.content, "html.parser")

                    anime_id = get_content_id(soup)

                    if anime_id is None:
                        continue
                    else:
                        pass

                    try:
                        # Updated to find episode container
                        ep_all_div = soup.find("div", class_="epAll")
                        if ep_all_div:
                            anime_episodes_list = ep_all_div.find_all("a")
                        else:
                            # Try alternative episode container
                            anime_episodes_list = soup.find_all("a", class_="epLink")
                            if not anime_episodes_list:
                                continue
                    except AttributeError:
                        continue

                    current_number_of_episodes = len(anime_episodes_list)

                    try:
                        old_number_of_episodes = old_animes[anime_id]["Number Of Episodes"]
                        if current_number_of_episodes == old_number_of_episodes:
                            continue
                        else:
                            new_episodes = scrape_episodes(
                                current_number_of_episodes, anime_episodes_list, old_number_of_episodes)

                            old_animes[anime_id]["Number Of Episodes"] += len(
                                new_episodes)

                            old_animes[anime_id]["Episodes"].update(new_episodes)
                            continue
                    except KeyError:
                        # Get title - updated for new HTML structure
                        try:
                            title_div = anime_div.find("div", class_="h5")
                            if title_div:
                                title = title_div.text.strip()
                            else:
                                title_div = anime_div.find("div", class_="h1")
                                if title_div:
                                    title = title_div.text.strip()
                                else:
                                    title = "Unknown Anime"
                        except:
                            title = "Unknown Anime"

                        # Get image - updated for new HTML structure
                        try:
                            img = anime_div.find("img")
                            if img:
                                img_src = img.get("data-src", img.get("src", ""))
                            else:
                                img_src = ""
                        except:
                            img_src = ""

                        anime_dict[anime_id] = {
                            "Title": clean_anime_title(title),
                            "Category": "anime",
                            "Number Of Episodes": current_number_of_episodes,
                            "Format": get_content_format(soup),
                            "Image Source": upload_image(img_src, anime_id + "-fasel", get_website_safe),
                            "Episodes": scrape_episodes(current_number_of_episodes, anime_episodes_list)
                        }

                except Exception as e:
                    if DEBUG:
                        print(f"Error scraping anime on page {page}: {e}")
                    continue

            if DEBUG:
                print(f'Done scraping page {page}')
            else:
                pass

        except Exception as e:
            if DEBUG:
                print(f"Error scraping anime page {page}: {e}")
            continue

    return anime_dict


def main() -> None:
    """Scrapes all the anime from fasel"""
    # Updated selector to match new HTML structure
    get_cookies(FASEL_BASE_URL, (By.CLASS_NAME, "logo"))
    
    # Use the correct category URL (page 1)
    category_url = FASEL_BASE_URL + "anime"
    
    try:
        total_pages = get_number_of_pages(category_url)
    except Exception as e:
        if DEBUG:
            print(f"Error getting number of pages: {e}")
        total_pages = 1

    page_ranges_list = split_into_ranges(8, total_pages)

    if DEBUG:
        print(f"Total pages: {total_pages}")
        print(f"Page ranges: {page_ranges_list}")
    else:
        pass

    # Pass category_url to scrape_anime
    from itertools import repeat
    with ThreadPoolExecutor() as executor:
        results = executor.map(
            scrape_anime, 
            page_ranges_list,
            repeat(category_url)
        )

    for result in results:
        old_animes.update(result)

    with open("./output/anime.json", "w") as fp:
        json.dump(old_animes, fp, indent=4)


if __name__ == "__main__":
    start_time = perf_counter()
    main()
    end_time = perf_counter()
    print(
        f"Done scraping all animes from fasel in about {round((end_time - start_time) / 60)} minute(s)"
    )
else:
    pass
