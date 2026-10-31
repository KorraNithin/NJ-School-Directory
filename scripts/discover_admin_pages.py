
import pandas as pd
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    BASE_DIR / "data" / "extracted" /
    "new_jersey" / "nj_districts.csv"
)

OUTPUT_FILE = (
    BASE_DIR / "data" / "extracted" /
    "new_jersey" / "admin_pages_discovered.csv"
)

# Test with 20 districts first.
TEST_LIMIT = 20

KEYWORDS = [
    "administration",
    "administrator",
    "leadership",
    "staff directory",
    "faculty directory",
    "our team",
    "superintendent",
    "principal",
    "school directory",
    "contact directory",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NJSchoolDirectoryResearch/1.0)"
}


def normalize_url(url):
    if not url or not str(url).strip():
        return None

    url = str(url).strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url.rstrip("/")


def discover_pages(district):
    district_name = district.get("name", "")
    website = normalize_url(district.get("website", ""))

    if not website:
        print(f"Skipping {district_name}: No website")
        return []

    results = []

    try:
        response = requests.get(
            website,
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        original_domain = urlparse(response.url).netloc.lower()

        homepage_text = soup.get_text(" ", strip=True).lower()

        if any(keyword in homepage_text for keyword in KEYWORDS):
            results.append({
                "district": district_name,
                "district_website": website,
                "page_url": response.url,
                "link_text": "Homepage",
                "status": "homepage_candidate"
            })

        for link in soup.find_all("a", href=True):
            href = urljoin(response.url, link["href"])
            link_text = link.get_text(" ", strip=True)

            combined_text = (link_text + " " + href).lower()

            if not any(keyword in combined_text for keyword in KEYWORDS):
                continue

            parsed = urlparse(href)

            # Only inspect pages on the same official website.
            if parsed.netloc.lower() != original_domain:
                continue

            if parsed.scheme not in ("http", "https"):
                continue

            # Ignore files and email links.
            if parsed.path.lower().endswith(
                (".pdf", ".jpg", ".png", ".doc", ".docx")
            ):
                continue

            results.append({
                "district": district_name,
                "district_website": website,
                "page_url": href,
                "link_text": link_text,
                "status": "discovered"
            })

    except requests.RequestException as error:
        print(f"Could not access {district_name}: {error}")

    unique = {}

    for item in results:
        unique[item["page_url"]] = item

    print(f"{district_name}: {len(unique)} candidate pages")

    return list(unique.values())


def main():
    districts = pd.read_csv(
        INPUT_FILE,
        dtype=str
    ).fillna("")

    print("Original CSV columns:", list(districts.columns))

    # Support the original NCES dataset column names.
    districts = districts.rename(columns={
        "LEA_NAME": "name",
        "WEBSITE": "website"
    })

    # Also support the cleaned CSV column names if used later.
    if "name" not in districts.columns or "website" not in districts.columns:
        raise ValueError(
            "District name or website columns are missing. "
            "Expected LEA_NAME and WEBSITE, or name and website."
        )

    test_districts = districts.head(TEST_LIMIT)

    all_results = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(discover_pages, row.to_dict())
            for _, row in test_districts.iterrows()
        ]

        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception as error:
                print("Unexpected error:", error)

    output = pd.DataFrame(
        all_results,
        columns=[
            "district",
            "district_website",
            "page_url",
            "link_text",
            "status"
        ]
    )

    if not output.empty:
        output = output.drop_duplicates(
            subset=["district", "page_url"]
        )

    output.to_csv(OUTPUT_FILE, index=False)

    print("\n========== DISCOVERY SUMMARY ==========")
    print("Districts checked:", len(test_districts))
    print("Candidate pages found:", len(output))
    print("Output saved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
