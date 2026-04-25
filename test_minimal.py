from Common import get_website_safe, get_paginated_url, FASEL_BASE_URL

url = get_paginated_url(FASEL_BASE_URL + "movies", 186)
resp = get_website_safe(url)
if resp:
    print(f"Status: {resp.status_code}, length: {len(resp.text)}")
    if "blockMovie" in resp.text:
        print("Found movie containers")
    else:
        print("No movies")
else:
    print("Failed")