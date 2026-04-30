import requests

OMDB_API_KEY = "b7fc5b44"
OMDB_BASE_URL = "http://www.omdbapi.com/"

def test_omdb():
    url = f"{OMDB_BASE_URL}?t=The Batman&apikey={OMDB_API_KEY}"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    print(f"Response: {data}")
    if data.get("Response") == "True":
        print(f"Rating: {data.get('imdbRating')}, Votes: {data.get('imdbVotes')}")
    else:
        print("Error:", data.get("Error"))

if __name__ == "__main__":
    test_omdb()