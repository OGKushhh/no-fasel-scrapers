import json
from Common import FILE_NAMES
from os import remove, listdir
import requests
from os import environ
from hashlib import md5


def main() -> None:
    file_hashes = {}
    ALL_FILES = ["all-content.json", "anime.json", "arabic-movies.json", "arabic-series.json", "asian-series.json",
                 "featured-content.json", "movies.json", "series.json", "trending-content.json", "tvshows.json", "last-scraped.txt"]

    # Clean up temporary image files
    for file in listdir("./output"):
        if ".jpg" in file or ".webp" in file:
            try:
                remove(f"./output/{file}")
            except:
                continue
        else:
            continue

    # Load existing image indices
    try:
        with open('./output/image-indices.json', 'r') as fp:
            image_indices = json.load(fp)
    except FileNotFoundError:
        image_indices = {}

    for index, file in enumerate(FILE_NAMES):
        try:
            with open(f'./output/{file}.json', 'r', encoding='utf-8') as fp:
                content = json.load(fp)
        except FileNotFoundError:
            if file in ["arabic-movies", "arabic-series"]:
                continue  # These are optional
            print(f"Warning: {file}.json not found, skipping...")
            continue
        except json.JSONDecodeError:
            print(f"Warning: {file}.json is not valid JSON, skipping...")
            continue

        for key in content:
            # Handle image indices
            if "Image Source" in content[key]:
                if "arabic" in file:
                    image_indices[key + "-akwam-" +
                                  file.split("-")[-1]] = content[key]["Image Source"]
                elif "hdw" in file:
                    image_indices[key + "-hdw"] = content[key]["Image Source"]
                else:
                    image_indices[key + "-fasel"] = content[key]["Image Source"]

            # Clean genres
            try:
                genres = content[key]["Genres"]

                for genre in list(genres):
                    if "%" in genre or genre == "/":
                        genres.remove(genre)
                    else:
                        continue

                    content[key]["Genres"] = genres
                else:
                    pass
            except KeyError:
                content[key]["Genres"] = []
            except TypeError:
                content[key]["Genres"] = []

            # Add TMDb ID if not present
            if "TMDb ID" in content[key] and content[key]["TMDb ID"] != None:
                continue
            else:
                params = {
                    "query": content[key]["Title"],
                    "api_key": environ.get("TMDB_API_KEY")
                }

                if "movies" in file:
                    request_url = "https://api.themoviedb.org/3/search/movie"
                else:
                    request_url = "https://api.themoviedb.org/3/search/tv"

                try:
                    resp = requests.get(request_url, params=params, timeout=10)
                    resp.raise_for_status()
                    
                    try:
                        tmdb_id = resp.json()["results"][0]["id"]
                    except IndexError:
                        tmdb_id = None
                    except KeyError:
                        tmdb_id = None
                except Exception as e:
                    tmdb_id = None

                content[key]["TMDb ID"] = tmdb_id

        # Clean invalid entries for series (indices 2-5)
        if index in range(2, 5):
            for key in list(content.keys()):
                try:
                    if len(content[key].get("Seasons", {})) == 0:
                        del content[key]
                    else:
                        continue
                except KeyError:
                    del content[key]

        # Clean invalid entries for movies (index 0)
        elif index == 0:
            for key in list(content.keys()):
                try:
                    if content[key].get("Source", "") == "":
                        del content[key]
                    else:
                        continue
                except KeyError:
                    del content[key]

        else:
            pass

        with open(f'./output/{file}.json', 'w', encoding='utf-8') as fp:
            json.dump(content, fp, indent=4, ensure_ascii=False)

    # Save updated image indices
    with open('./output/image-indices.json', 'w', encoding='utf-8') as fp:
        json.dump(image_indices, fp, indent=4, ensure_ascii=False)

    # Calculate file hashes for change detection
    for file in ALL_FILES:
        try:
            with open(f"./output/{file}", "r", encoding="utf-8") as fp:
                file_name = file.split(".")[0]
                if ".json" in file:
                    content = json.load(fp)
                    file_hashes[file_name] = md5(json.dumps(
                        content).encode("utf-8")).hexdigest()
                else:
                    file_hashes[file_name] = md5(
                        fp.read().encode("utf-8")).hexdigest()
        except FileNotFoundError:
            continue
        except json.JSONDecodeError:
            continue

    with open("./output/file-hashes.json", "w") as fp:
        json.dump(file_hashes, fp, indent=4)


if __name__ == '__main__':
    main()
else:
    pass
