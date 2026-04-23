from Common import *
from bs4 import BeautifulSoup
from time import perf_counter
import requests
import json
from difflib import get_close_matches

content_dict = {'movies': {}, 'asian-series': {},
                'anime': {}, 'series': {}, "arabic-series": {},
                "arabic-movies": {}}

featured_content_dict = {"content": []}


def scrape_akwam() -> None:
    """Scrapes the recent arabic series and movies from akwam"""
    try:
        home_page = requests.get("https://akwam.to/one")
        soup = BeautifulSoup(home_page.content, "html.parser")
        anchor_tags = soup.find_all("a", class_="icn play")
        content_links = [tag["href"] for tag in anchor_tags]

        with open("./output/arabic-series.json", "r", encoding="utf-8") as fp:
            arabic_series = json.load(fp)

        with open("./output/arabic-movies.json", "r", encoding="utf-8") as fp:
            arabic_movies = json.load(fp)

        for link in content_links:
            if "series" in link:
                series_id = link.split("/")[-2]

                try:
                    content_dict["arabic-series"][series_id] = {"Title": arabic_series[series_id]["Title"],
                                                                "Image Source": arabic_series[series_id]["Image Source"],
                                                                "Category": "arabic-series"}
                except KeyError:
                    continue

            elif "movie" in link:
                movie_id = link.split("/")[-2]

                try:
                    content_dict["arabic-movies"][movie_id] = {"Title": arabic_movies[movie_id]["Title"],
                                                               "Image Source": arabic_movies[movie_id]["Image Source"],
                                                               "Category": "arabic-movies"}
                except KeyError:
                    continue

            else:
                continue
    except Exception as e:
        if DEBUG:
            print(f"Error scraping akwam: {e}")


def scrape_fasel() -> None:
    """Scrapes the content on the home page of fasel"""
    # Updated selector to match new HTML structure
    get_cookies(FASEL_BASE_URL, (By.CLASS_NAME, "logo"))
    home_page = get_website_safe(FASEL_BASE_URL)
    soup = BeautifulSoup(home_page.content, 'html.parser')

    # Get trending content using new helper functions
    trending_movies = get_latest_movies(soup)
    trending_episodes = get_latest_episodes(soup)
    featured_content = get_featured_content(soup)

    seen = []

    # Process trending movies
    for movie in trending_movies:
        link = movie["link"]
        try:
            content_page = get_website_safe(link)
            soup = BeautifulSoup(content_page.content, 'html.parser')

            # Updated title extraction for new HTML structure
            try:
                title_div = soup.find("div", class_="h1 title")
                if title_div:
                    content_title = remove_year(remove_arabic_chars(
                        title_div.text.split('\n')[1].strip() if '\n' in title_div.text else title_div.text.strip()
                    ))
                else:
                    content_title = movie["title"]
            except Exception:
                content_title = movie["title"]

            if '/movies/' in link or 'anime-movies' in link or 'asian-movies' in link:
                content_category = 'movies'
            elif 'asian-episodes' in link or 'asian-series' in link:
                content_category = 'asian-series'
            elif 'anime-episodes' in link or '/anime/' in link:
                content_category = 'anime'
            else:
                content_category = 'series'

            with open(f'./output/{content_category}.json', 'r') as fp:
                content_file = json.load(fp)

            for key in content_file:
                current_title = "".join(content_file[key]["Title"].lower().split())
                clean_content_title = "".join(content_title.lower().split())
                if (current_title == clean_content_title) and (key not in seen):
                    seen.append(key)

                    if "Rating" in content_file[key]:
                        rating = content_file[key]["Rating"]
                    else:
                        rating = "N/A"

                    if "TMDb ID" in content_file[key]:
                        tmdb_id = content_file[key]["TMDb ID"]
                    else:
                        tmdb_id = None

                    content_dict[content_category].update(
                        {key: {
                            "Title": content_file[key]["Title"],
                            "Image Source": content_file[key]["Image Source"],
                            "Category": content_category,
                            "Genres": content_file[key].get("Genres", []),
                            "Rating": rating,
                            "TMDb ID": tmdb_id
                        }})

                    break
                else:
                    continue
        except Exception as e:
            if DEBUG:
                print(f"Error processing movie {link}: {e}")
            continue

    # Process trending episodes
    for episode in trending_episodes:
        link = episode["link"]
        try:
            content_page = get_website_safe(link)
            soup = BeautifulSoup(content_page.content, 'html.parser')

            # Updated title extraction for new HTML structure
            try:
                title_div = soup.find("div", class_="h1 title")
                if title_div:
                    content_title = remove_year(remove_arabic_chars(
                        title_div.text.split('\n')[1].strip() if '\n' in title_div.text else title_div.text.strip()
                    ))
                else:
                    content_title = episode["title"]
            except Exception:
                content_title = episode["title"]

            if 'anime-episodes' in link or '/anime/' in link:
                content_category = 'anime'
            elif 'asian-episodes' in link or 'asian-series' in link:
                content_category = 'asian-series'
            else:
                content_category = 'series'

            with open(f'./output/{content_category}.json', 'r') as fp:
                content_file = json.load(fp)

            for key in content_file:
                current_title = "".join(content_file[key]["Title"].lower().split())
                clean_content_title = "".join(content_title.lower().split())
                if (current_title == clean_content_title) and (key not in seen):
                    seen.append(key)

                    if "Rating" in content_file[key]:
                        rating = content_file[key]["Rating"]
                    else:
                        rating = "N/A"

                    if "TMDb ID" in content_file[key]:
                        tmdb_id = content_file[key]["TMDb ID"]
                    else:
                        tmdb_id = None

                    content_dict[content_category].update(
                        {key: {
                            "Title": content_file[key]["Title"],
                            "Image Source": content_file[key]["Image Source"],
                            "Category": content_category,
                            "Genres": content_file[key].get("Genres", []),
                            "Rating": rating,
                            "TMDb ID": tmdb_id
                        }})

                    break
                else:
                    continue
        except Exception as e:
            if DEBUG:
                print(f"Error processing episode {link}: {e}")
            continue

    # Process featured content
    with open("./output/movies.json", "r") as fp:
        movies = json.load(fp)

    for item in featured_content:
        try:
            link = item["link"]
            content_page = get_website_safe(link)

            movie_id = get_content_id(BeautifulSoup(
                content_page.content, "html.parser"))

            if movie_id is None:
                continue

            if movie_id in movies:
                if "Genres" in movies[movie_id]:
                    genres = movies[movie_id]["Genres"]
                else:
                    genres = []

                if "Rating" in movies[movie_id]:
                    rating = movies[movie_id]["Rating"]
                else:
                    rating = "N/A"

                if "TMDb ID" in movies[movie_id]:
                    tmdb_id = movies[movie_id]["TMDb ID"]
                else:
                    tmdb_id = "N/A"

                featured_content_dict["content"].append({
                    "key": movie_id,
                    "Title": movies[movie_id]["Title"],
                    "Image Source": movies[movie_id]["Image Source"],
                    "Category": movies[movie_id].get("Category", "movies"),
                    "Genres": genres,
                    "Rating": rating,
                    "TMDb ID": tmdb_id,
                    "Featured": True
                })

        except KeyError:
            continue
        except Exception as e:
            if DEBUG:
                print(f"Error processing featured content: {e}")
            continue

    with open("./output/featured-content.json", "w") as fp:
        json.dump(featured_content_dict, fp, indent=4)


def main() -> None:
    scrape_fasel()
    scrape_akwam()

    with open("./output/trending-content.json", "w", encoding="utf-8") as fp:
        json.dump(content_dict, fp, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    start_time = perf_counter()
    main()
    end_time = perf_counter()
    print(
        f"Finished scraping the trending content in about {round((end_time - start_time) / 60)} minute(s)"
    )
else:
    pass
