import csv
import re
import time
import requests
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, urldefrag
from bs4 import BeautifulSoup

ROOT = Path.cwd()
DATA = ROOT / "data" / "extracted" / "new_jersey"

INPUT = DATA / "nj_districts.csv"
OUTPUT = DATA / "admin_pages_discovered_all.csv"
FAILURES = DATA / "admin_discovery_failures_all.csv"

MAX_PAGES_PER_DISTRICT = 12
MAX_WORKERS = 5
TIMEOUT = 20

KEYWORDS = [
    "administration", "leadership", "staff directory",
    "staff", "directory", "superintendent", "principal",
    "board of education", "central office", "our team",
    "faculty", "contact us", "district office",
    "business administrator", "school leaders"
]

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif",
    ".zip", ".doc", ".docx", ".xls", ".xlsx"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SchoolDirectoryResearch/1.0)"
}

def matches_keyword(value):
    value = (value or "").lower()
    return any(keyword in value for keyword in KEYWORDS)

def normalize_url(url):
    url, _ = urldefrag(url)
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    if parsed.path.lower().endswith(SKIP_EXTENSIONS):
        return ""

    return url.rstrip("/")

def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    if "html" not in content_type:
        raise ValueError("Page is not HTML")

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    page_text = soup.get_text(" ", strip=True)

    links = []
    for a in soup.find_all("a", href=True):
        href = normalize_url(urljoin(response.url, a["href"]))
        label = a.get_text(" ", strip=True)

        if not href:
            continue

        if urlparse(href).netloc.lower() != urlparse(response.url).netloc.lower():
            continue

        if matches_keyword(label + " " + href):
            links.append((href, label))

    return response.url, title, page_text, links

def discover_district(row):
    district = (row.get("LEA_NAME") or "").strip()
    website = (row.get("WEBSITE") or "").strip()

    result_pages = []
    failures = []

    if not website:
        failures.append({
            "district": district,
            "website": website,
            "failed_url": "",
            "error": "No website listed in district data"
        })
        return result_pages, failures

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    website = normalize_url(website)

    if not website:
        failures.append({
            "district": district,
            "website": website,
            "failed_url": "",
            "error": "Invalid website URL"
        })
        return result_pages, failures

    queue = deque([(website, 0)])
    visited = set()

    while queue and len(visited) < MAX_PAGES_PER_DISTRICT:
        current_url, depth = queue.popleft()
        current_url = normalize_url(current_url)

        if not current_url or current_url in visited:
            continue

        visited.add(current_url)

        try:
            final_url, title, page_text, links = get_page(current_url)

            result_pages.append({
                "district": district,
                "district_website": website,
                "page_url": final_url,
                "page_title": title,
                "matched_keywords": "; ".join(
                    keyword for keyword in KEYWORDS
                    if keyword in (title + " " + final_url + " " + page_text).lower()
                ),
                "discovery_depth": depth,
                "status": "SUCCESS"
            })

            if depth < 2:
                for link_url, label in links:
                    if link_url not in visited:
                        queue.append((link_url, depth + 1))

        except Exception as e:
            failures.append({
                "district": district,
                "website": website,
                "failed_url": current_url,
                "error": str(e)[:300]
            })

    return result_pages, failures

def main():
    if not INPUT.exists():
        print("ERROR: District CSV not found:", INPUT)
        return

    with INPUT.open(encoding="utf-8-sig", newline="") as f:
        districts = list(csv.DictReader(f))

    print("Districts to process:", len(districts))
    print("Workers:", MAX_WORKERS)
    print("Maximum pages per district:", MAX_PAGES_PER_DISTRICT)
    print("\nStarting discovery. This may take some time...\n")

    all_pages = []
    all_failures = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(discover_district, row)
            for row in districts
        ]

        for future in as_completed(futures):
            try:
                pages, failures = future.result()
                all_pages.extend(pages)
                all_failures.extend(failures)
            except Exception as e:
                all_failures.append({
                    "district": "UNKNOWN",
                    "website": "",
                    "failed_url": "",
                    "error": str(e)[:300]
                })

            completed += 1

            if completed % 25 == 0 or completed == len(districts):
                print(
                    f"Progress: {completed}/{len(districts)} districts | "
                    f"Pages: {len(all_pages)} | "
                    f"Failures: {len(all_failures)}"
                )

    page_fields = [
        "district", "district_website", "page_url",
        "page_title", "matched_keywords",
        "discovery_depth", "status"
    ]

    failure_fields = [
        "district", "website", "failed_url", "error"
    ]

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=page_fields)
        writer.writeheader()
        writer.writerows(all_pages)

    with FAILURES.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=failure_fields)
        writer.writeheader()
        writer.writerows(all_failures)

    print("\nDISCOVERY COMPLETE")
    print("Districts processed:", len(districts))
    print("Pages discovered:", len(all_pages))
    print("Failed page requests:", len(all_failures))
    print("Pages file:", OUTPUT.resolve())
    print("Failures file:", FAILURES.resolve())
    print("\nNo Supabase operations were performed.")

if __name__ == "__main__":
    main()
