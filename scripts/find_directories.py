
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

df = pd.read_csv(
    DATA_DIR / "nj_districts.csv",
    dtype=str,
    keep_default_na=False
)

df = df[df["WEBSITE"].str.strip() != ""]
df = df.drop_duplicates(subset=["WEBSITE"]).head(10)

KEYWORDS = [
    "administration",
    "administrators",
    "staff directory",
    "directory",
    "leadership",
    "superintendent",
    "board of education",
    "contact"
]

HEADERS = {
    "User-Agent": "NJSchoolDirectoryResearch/1.0 (educational project)"
}

for _, row in df.iterrows():
    website = row["WEBSITE"].strip()

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    print("\n" + "=" * 65)
    print("DISTRICT:", row["LEA_NAME"])
    print("WEBSITE:", website)

    try:
        response = requests.get(
            website,
            headers=HEADERS,
            timeout=15
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        print("PAGE TITLE:", soup.title.get_text(strip=True) if soup.title else "Not found")
        print("POSSIBLE DIRECTORY LINKS:")

        found = 0

        for link in soup.find_all("a", href=True):
            text = link.get_text(" ", strip=True).lower()
            href = link["href"].lower()

            if any(keyword in text or keyword in href for keyword in KEYWORDS):
                full_url = urljoin(response.url, link["href"])

                if urlparse(full_url).scheme in ("http", "https"):
                    print("-", link.get_text(" ", strip=True), "->", full_url)
                    found += 1

        if found == 0:
            print("No obvious directory links found.")

    except requests.RequestException as error:
        print("Could not access website:", error)
