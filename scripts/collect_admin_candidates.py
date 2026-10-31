
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

OUTPUT_FILE = DATA_DIR / "admin_candidates_review.csv"

KEYWORDS = [
    "administration",
    "leadership",
    "superintendent",
    "staff-directory",
    "staff directory",
    "district-office",
    "district office",
    "administrators"
]

TITLE_PATTERN = re.compile(
    r"\b(Superintendent|Assistant Superintendent|"
    r"Chief of Operations|Business Administrator|"
    r"Director of [A-Za-z ,&'-]+|"
    r"Principal|Assistant Principal|"
    r"Clinical Director|Administrative Assistant)\b",
    re.IGNORECASE
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NJSchoolDirectoryResearch/1.0)"
}

session = requests.Session()
session.headers.update(HEADERS)


def get_page(url):
    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()

        if "text/html" not in response.headers.get("Content-Type", ""):
            return None

        return response

    except requests.RequestException:
        return None


def extract_candidates(url, district_name):
    response = get_page(url)

    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).splitlines()
        if line.strip()
    ]

    records = []

    for line in lines:
        match = TITLE_PATTERN.search(line)

        if not match:
            continue

        name = line[:match.start()].strip(" ,:-")
        title = match.group(0).strip()

        # Basic checks to avoid navigation text and long descriptions
        if not name or len(name.split()) < 2 or len(name.split()) > 8:
            continue

        if len(name) > 100:
            continue

        if any(word in name.lower() for word in [
            "search", "skip", "menu", "home", "about"
        ]):
            continue

        records.append({
            "district": district_name,
            "name": name,
            "title": title,
            "email": "",
            "phone": "",
            "source_url": response.url,
            "review_status": "Needs manual verification"
        })

    return records


def find_directory_links(homepage):
    response = get_page(homepage)

    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    links = []

    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True).lower()
        href = anchor["href"].lower()

        if any(word in label or word in href for word in KEYWORDS):
            full_url = urljoin(response.url, anchor["href"])

            if urlparse(full_url).scheme not in ("http", "https"):
                continue

            if urlparse(full_url).netloc != urlparse(response.url).netloc:
                continue

            if full_url not in links:
                links.append(full_url)

    return links[:5]


districts = pd.read_csv(
    DATA_DIR / "nj_districts.csv",
    dtype=str,
    keep_default_na=False
)

districts = districts[
    districts["WEBSITE"].str.strip() != ""
].drop_duplicates(subset=["LEAID"]).head(10)

all_records = []

for _, district in districts.iterrows():
    name = district["LEA_NAME"]
    website = district["WEBSITE"].strip()

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    print("\nProcessing:", name)

    directory_links = find_directory_links(website)

    if not directory_links:
        directory_links = [website]

    for link in directory_links:
        print("Checking:", link)

        records = extract_candidates(link, name)
        all_records.extend(records)

        print("Candidates found:", len(records))
        time.sleep(1)

    time.sleep(1)

if all_records:
    result = pd.DataFrame(all_records)
    result = result.drop_duplicates(
        subset=["district", "name", "title", "source_url"]
    )

    result.to_csv(OUTPUT_FILE, index=False)

    print("\n========== COLLECTION SUMMARY ==========")
    print("Administrator candidates:", len(result))
    print("Output:", OUTPUT_FILE)
else:
    print("\nNo candidates found in this batch.")
