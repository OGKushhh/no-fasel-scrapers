import re

# Simulated href values from a FaselHD category page (movies, anime, series)
test_hrefs = [
    "https://www.fasel-hd.cam/?p=148151",                    # shortlink
    "/?p=148151",                                            # relative shortlink
    "/movies/%d9%81%d9%8a%d9%84%d9%85-batman-2022-%d9%85%d8%aa%d8%b1%d8%ac%d9%85-rt",  # pretty slug
    "/anime/%d8%a3%d9%86%d9%85%d9%8a-radiant",               # anime slug
    "/series/%d9%85%d8%b3%d9%84%d8%b3%d9%84-breaking-bad",    # series slug
    "/tvshows/%d8%a8%d8%b1%d9%86%d8%a7%d9%85%d8%ac-the-late-show",  # tvshows slug
    "https://www.fasel-hd.cam/movies/page/2/?p=99999",       # shortlink with extra path
    "/?p=12345&something=else",                              # shortlink with extra query
]

print("Testing href extraction:\n")
for href in test_hrefs:
    match = re.search(r'[?&]p=(\d+)', href)
    if match:
        extracted_id = match.group(1)
        print(f"✅ HREF: {href}")
        print(f"   Extracted ID: {extracted_id}\n")
    else:
        print(f"❌ HREF: {href}")
        print(f"   No numeric ID found (only slug).\n")