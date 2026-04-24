from Common import get_website_safe, FASEL_BASE_URL
from bs4 import BeautifulSoup

url = FASEL_BASE_URL + "movies/1%d9%81%d9%8a%d9%84%d9%85-pirates-of-the-caribbean-the-curse-of-the-black-pearl-2013-%d9%85%d8%aa%d8%b1%d8%ac%d9%85-nj"
resp = get_website_safe(url)
if resp:
    soup = BeautifulSoup(resp.text, "html.parser")
    iframe = soup.find("iframe")
    print("Iframe found:", iframe is not None)
    if iframe:
        print("Iframe src:", iframe.get("src"))
    # Also check content ID
    from Common import get_content_id
    cid = get_content_id(soup)
    print("Content ID:", cid)
else:
    print("Failed to fetch")