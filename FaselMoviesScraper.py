from sys import setrecursionlimit
from bs4 import BeautifulSoup, ResultSet
from Common import *
from concurrent.futures import ThreadPoolExecutor
import json
from time import perf_counter

setrecursionlimit(25000)

try:
    with open("./output/movies.json") as fp:
        old_movies_dict = json.load(fp)
except FileNotFoundError:
    old_movies_dict = {}


def scrape_page(movie_divs: list[ResultSet]) -> dict:
    """Scrapes all the movies in the page provided"""
    movies_dict = {}
    for movie_div in movie_divs:
        try:
            movie_page_url = movie_div.find("a")["href"]
            movie_page = get_website_safe(movie_page_url)

            if movie_page is not None:
                soup = BeautifulSoup(movie_page.content, "html.parser")
            else:
                continue

            movie_id = get_content_id(soup)

            if (movie_id in old_movies_dict) or (movie_id is None):
                continue
            else:
                pass

            try:
                iframe_source = soup.find("iframe")["src"]
            except TypeError:
                continue

            # Get title - updated for new HTML structure
            try:
                title_div = movie_div.find("div", class_="h5")
                if title_div:
                    title = get_content_title(movie_div)
                else:
                    # Alternative title extraction
                    h1_title = soup.find("div", class_="h1 title")
                    if h1_title:
                        title = remove_year(remove_arabic_chars(
                            h1_title.text.split('\n')[1].strip() if '\n' in h1_title.text else h1_title.text.strip()
                        ))
                    else:
                        title = "Unknown Movie"
            except Exception:
                title = "Unknown Movie"

            # Get image - updated for new HTML structure
            try:
                img = movie_div.find("img")
                if img:
                    img_src = img.get("data-src", img.get("src", ""))
                else:
                    img_src = ""
            except:
                img_src = ""

            movies_dict[movie_id] = {
                "Title": title,
                "Category": "movies",
                "Genres": get_genres(soup),
                "Format": get_content_format(soup),
                "Image Source": upload_image(img_src, movie_id + "-fasel", get_website_safe),
                "Source": clean_iframe_source(iframe_source),
            }

        except Exception as e:
            if DEBUG:
                print(f"Error scraping movie: {e}")
            continue

    return movies_dict


def scrape_all_movies(page_range: tuple) -> dict:
    """Scrapes all the movies in the page range provided"""
    movies_dict = {}

    for page in range(page_range[0], page_range[1]):
        try:
            main_page = get_website_safe(
                FASEL_BASE_URL + f"movies/page/{page}")

            soup = BeautifulSoup(main_page.content, "html.parser")

            # Updated to match new HTML structure
            movie_divs = soup.find_all(
                "div", class_="col-xl-2 col-lg-2 col-md-3 col-sm-3")

            if not movie_divs:
                # Fallback to blockMovie divs
                movie_divs = soup.find_all("div", class_="blockMovie")

            movie_divs_ranges = split_into_ranges(6, len(movie_divs))
            splitted_movie_divs_list = [
                movie_divs[movie_divs_range[0] - 1: movie_divs_range[1] - 1]
                for movie_divs_range in movie_divs_ranges
            ]

            with ThreadPoolExecutor() as executor:
                results = executor.map(scrape_page, splitted_movie_divs_list)

            for result in results:
                movies_dict.update(result)

            if DEBUG:
                print(f'Done scraping page {page}')
            else:
                pass

        except Exception as e:
            if DEBUG:
                print(f"Error scraping movies page {page}: {e}")
            continue

    return movies_dict


def main() -> None:
    """Scapes all the movies from fasel"""
    # Updated selector to match new HTML structure
    get_cookies(FASEL_BASE_URL, (By.CLASS_NAME, "logo"))

    try:
        total_pages = get_number_of_pages(FASEL_BASE_URL + "movies")
    except Exception as e:
        if DEBUG:
            print(f"Error getting number of pages: {e}")
        total_pages = 1

    page_ranges_list = split_into_ranges(
        8,
        total_pages,
    )

    if DEBUG:
        print(page_ranges_list)
    else:
        pass

    with ThreadPoolExecutor() as executor:
        results = executor.map(scrape_all_movies, page_ranges_list)

    for result in results:
        old_movies_dict.update(result)

    with open("./output/movies.json", "w") as fp:
        json.dump(old_movies_dict, fp, indent=4)


if __name__ == "__main__":
    start_time = perf_counter()
    main()
    end_time = perf_counter()
    print(
        f"Finished scraping all movies from fasel in about {round((end_time - start_time) / 60)} minute(s)"
    )
else:
    pass
