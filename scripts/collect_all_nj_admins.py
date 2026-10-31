
import csv
import json
import re
import time
import logging
import threading

from pathlib import Path
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "extracted" / "new_jersey"

DISTRICTS_FILE = DATA / "nj_districts.csv"

OUTPUT_FILE = DATA / "admin_fast_run_raw.csv"
REVIEW_FILE = DATA / "admin_fast_run_review.csv"
COVERAGE_FILE = DATA / "admin_fast_run_coverage.csv"
FAILURES_FILE = DATA / "admin_fast_run_failures.csv"
SUMMARY_FILE = DATA / "admin_fast_run_summary.json"

CHECKPOINT_FILE = DATA / "admin_fast_run_checkpoint.json"
RECORDS_FILE = DATA / "admin_fast_run_records.jsonl"

WORKERS = 24
TIMEOUT = 15
MAX_PAGES = 25
MAX_DEPTH = 3
MIN_ADMIN_PER_DISTRICT = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}

ROLE_RE = re.compile(
    r"\b("
    r"superintendent(?:\s+of\s+schools?)?|"
    r"assistant\s+superintendent|"
    r"deputy\s+superintendent|"
    r"principal|"
    r"vice\s+principal|"
    r"assistant\s+principal|"
    r"head\s+of\s+school|"
    r"lead\s+person|"
    r"school\s+business\s+administrator|"
    r"business\s+administrator|"
    r"assistant\s+school\s+business\s+administrator|"
    r"board\s+secretary|"
    r"chief\s+operating\s+officer|"
    r"chief\s+operations\s+officer|"
    r"chief\s+academic\s+officer|"
    r"chief\s+executive\s+officer|"
    r"executive\s+director|"
    r"director\s+of\s+(?:special\s+services|"
    r"curriculum|instruction|student\s+services|"
    r"human\s+resources|technology|transportation|"
    r"finance|operations|special\s+education)"
    r")\b",
    re.I
)

EXCLUDE_RE = re.compile(
    r"department[s]?:|"
    r"superintendent.?s office|"
    r"principal.?s office|"
    r"staff directory|"
    r"parent engagement|"
    r"enrollment|"
    r"athletics|"
    r"communications",
    re.I
)

NAME_RE = re.compile(
    r"^(?:(?:Dr|Mr|Mrs|Ms|Miss)\.?\s+)?"
    r"[A-Z][A-Za-zÀ-ÿ'’.-]+"
    r"(?:\s+[A-Z]\.?)?"
    r"(?:\s+[A-Z][A-Za-zÀ-ÿ'’.-]+){1,3}$"
)

EMAIL_RE = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.I
)

PHONE_RE = re.compile(
    r"(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}"
)

LINK_WORDS = (
    "staff", "directory", "administration", "leadership",
    "superintendent", "principal", "faculty", "our-team",
    "district-office", "central-office", "school-leaders"
)

thread_local = threading.local()


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def normalize(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def get_session():
    if not hasattr(thread_local, "session"):
        session = requests.Session()
        session.headers.update(HEADERS)

        retry = Retry(
            total=2,
            connect=2,
            read=1,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=30,
            pool_maxsize=30
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        thread_local.session = session

    return thread_local.session


def clean_url(url):
    url = str(url or "").strip()

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url.rstrip("/")


def fetch_page(url):
    try:
        response = get_session().get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "html" not in content_type:
            if not response.text.lstrip().lower().startswith(
                ("<!doctype html", "<html")
            ):
                return None, response.url, "Not HTML"

        if len(response.content) > 8_000_000:
            return None, response.url, "Page too large"

        soup = BeautifulSoup(response.text, "html.parser")

        return soup, response.url, ""

    except Exception as error:
        return None, url, str(error)[:300]


def valid_name(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()

    if len(value) > 70:
        return False

    if not NAME_RE.fullmatch(value):
        return False

    if re.search(
        r"school|district|office|staff|department|"
        r"principal|director|superintendent",
        value,
        re.I
    ):
        return False

    return True


def valid_title(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()

    if not value or EXCLUDE_RE.search(value):
        return ""

    match = ROLE_RE.search(value)

    if not match:
        return ""

    return value[:180].strip(" -|,:;")


def extract_contact(block, name):
    text = block.get_text(" ", strip=True)

    emails = set(EMAIL_RE.findall(text))

    for link in block.find_all("a", href=True):
        href = link["href"].strip()

        if href.lower().startswith("mailto:"):
            emails.update(
                EMAIL_RE.findall(href[7:].split("?")[0])
            )

    email = ""

    if len(emails) == 1:
        email = next(iter(emails))

    elif emails:
        name_parts = [
            x.lower()
            for x in re.findall(r"[A-Za-z]+", name)
            if len(x) > 2
        ]

        for candidate in emails:
            local = re.split(
                r"[._+-]",
                candidate.split("@")[0].lower()
            )

            if any(part in local for part in name_parts):
                email = candidate
                break

    phone = ""

    for link in block.find_all("a", href=True):
        href = link["href"].strip()

        if href.lower().startswith("tel:"):
            match = PHONE_RE.search(href[4:])

            if match:
                phone = match.group(0)
                break

    if not phone:
        phones = set(PHONE_RE.findall(text))

        if len(phones) == 1:
            phone = next(iter(phones))

    return email, phone


# --------------------------------------------------
# ADMINISTRATOR EXTRACTION
# --------------------------------------------------

def extract_from_block(block, district, source_url):
    text = block.get_text(" ", strip=True)

    if not text or len(text) > 1800:
        return None

    lines = [
        re.sub(r"\s+", " ", line).strip(" \t\r\n•|,:;")
        for line in block.get_text("\n", strip=True).splitlines()
    ]

    lines = [line for line in lines if line]

    name = ""
    title = ""

    # First try structured name elements.
    selectors = [
        ".fsConstituentName",
        ".fsFullName",
        ".fsName",
        ".fsDirectoryName",
        ".staff-name",
        ".person-name",
        ".employee-name",
        ".name",
        "h2",
        "h3",
        "h4"
    ]

    for selector in selectors:
        for element in block.select(selector):
            candidate = element.get_text(" ", strip=True)

            if valid_name(candidate):
                name = candidate
                break

        if name:
            break

    # Find title from structured elements.
    title_selectors = [
        ".fsDepartments",
        ".fsTitles",
        ".fsConstituentTitle",
        ".fsPosition",
        ".staff-title",
        ".person-title",
        ".job-title",
        ".position",
        ".department",
        ".title"
    ]

    for selector in title_selectors:
        for element in block.select(selector):
            candidate = valid_title(
                element.get_text(" ", strip=True)
            )

            if candidate:
                title = candidate
                break

        if title:
            break

    # Fallback: read visible lines.
    for index, line in enumerate(lines):
        if not title:
            title = valid_title(line)

        if not name and valid_name(line):
            name = line

        if name and title:
            break

    # Fallback for text such as:
    # Dr. Brian McGuire Principal/Lead Person
    if not name or not title:
        for line in lines:
            match = ROLE_RE.search(line)

            if not match:
                continue

            before = line[:match.start()].strip(" -|,:;")

            if valid_name(before):
                name = name or before
                title = title or valid_title(line)

    if not name or not title:
        return None

    email, phone = extract_contact(block, name)

    location = ""

    for selector in [
        ".fsConstituentLocation",
        ".fsLocation",
        ".location",
        ".address"
    ]:
        element = block.select_one(selector)

        if element:
            location = element.get_text(" ", strip=True)[:180]
            break

    return {
        "district": district,
        "name": name,
        "title": title,
        "email": email,
        "phone": phone,
        "location": location,
        "source_url": source_url,
        "evidence": text[:700],
        "extraction_method": "html_directory",
        "verified": "source_page"
    }


def extract_page(soup, district, source_url):
    records = {}
    selectors = [
        ".fsConstituentItem",
        ".fsConstituent",
        "[class*='fsConstituentItem']",
        ".staff-member",
        ".staff-card",
        ".staff-item",
        ".person-card",
        ".employee-card",
        ".directory-item",
        "[class*='staff-card']",
        "[class*='person-card']",
        "[class*='employee']",
        "tr",
        "article",
        "li"
    ]

    blocks = []

    for selector in selectors:
        try:
            blocks.extend(soup.select(selector))
        except Exception:
            pass

    blocks.sort(
        key=lambda block: len(block.get_text(" ", strip=True))
    )

    for block in blocks:
        record = extract_from_block(
            block, district, source_url
        )

        if not record:
            continue

        key = (
            normalize(record["name"]),
            normalize(record["title"])
        )

        old = records.get(key)

        if not old:
            records[key] = record
        else:
            if not old["email"] and record["email"]:
                old["email"] = record["email"]

            if not old["phone"] and record["phone"]:
                old["phone"] = record["phone"]

    return list(records.values())


# --------------------------------------------------
# WEBSITE CRAWLING
# --------------------------------------------------

def same_domain(url, root_host):
    host = (urlparse(url).hostname or "").lower()

    if host.startswith("www."):
        host = host[4:]

    return (
        host == root_host
        or host.endswith("." + root_host)
        or root_host.endswith("." + host)
    )


def crawl_district(district_row):
    district = str(district_row.get("LEA_NAME", "")).strip()
    homepage = clean_url(district_row.get("WEBSITE", ""))

    if not homepage:
        return district, [], ["No website"], "No website"

    root_soup, landed, error = fetch_page(homepage)

    if root_soup is None:
        return district, [], [error], error

    root_host = (urlparse(landed).hostname or "").lower()

    if root_host.startswith("www."):
        root_host = root_host[4:]

    queue = deque([(landed, 0)])
    visited = set()
    records = {}
    failures = []

    while queue and len(visited) < MAX_PAGES:
        url, depth = queue.popleft()
        url = urldefrag(url)[0]

        if url in visited:
            continue

        visited.add(url)

        if url == landed:
            soup = root_soup
            final_url = landed
        else:
            soup, final_url, page_error = fetch_page(url)

            if soup is None:
                failures.append({
                    "url": url,
                    "error": page_error
                })
                continue

        page_records = extract_page(
            soup, district, final_url
        )

        for record in page_records:
            key = (
                normalize(record["name"]),
                normalize(record["title"])
            )

            old = records.get(key)

            if not old:
                records[key] = record
            else:
                if not old["email"] and record["email"]:
                    old["email"] = record["email"]

                if not old["phone"] and record["phone"]:
                    old["phone"] = record["phone"]

        if depth >= MAX_DEPTH:
            continue

        for link in soup.find_all("a", href=True):
            href = urljoin(final_url, link["href"].strip())
            label = link.get_text(" ", strip=True)

            combined = (href + " " + label).lower()

            if not href.startswith(("http://", "https://")):
                continue

            if not same_domain(href, root_host):
                continue

            if any(
                word in href.lower()
                for word in [
                    ".pdf", ".jpg", ".png", ".zip",
                    "facebook.com", "instagram.com",
                    "youtube.com", "linkedin.com"
                ]
            ):
                continue

            relevant = any(
                word in combined for word in LINK_WORDS
            )

            pagination = (
                label.lower().strip() in
                ["next", "next page", "more", "›", "»"]
                or bool(re.search(r"[?&](page|p|start)=", href, re.I))
            )

            if relevant or pagination:
                if href not in visited:
                    queue.append((href, depth + 1))

    return district, list(records.values()), failures, ""


# --------------------------------------------------
# EXISTING DATA AND CHECKPOINTS
# --------------------------------------------------

def read_csv(path):
    if not path.exists():
        return []

    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        return list(csv.DictReader(file))


def read_existing_records():
    filenames = [
        "admin_candidates_all_districts_raw.csv",
        "admin_candidates_all.csv",
        "NJ_School_Admin_Directory_FINAL.csv",
        "admin_candidates_combined_raw.csv",
        "admin_contacts_raw.csv"
    ]

    records = []

    for filename in filenames:
        for row in read_csv(DATA / filename):
            district = (
                row.get("district")
                or row.get("LEA_NAME")
                or ""
            ).strip()

            name = (
                row.get("name")
                or row.get("full_name")
                or ""
            ).strip()

            title = (
                row.get("title")
                or row.get("position")
                or ""
            ).strip()

            title = valid_title(title)

            if not district or not name or not title:
                continue

            records.append({
                "district": district,
                "name": name,
                "title": title,
                "email": (row.get("email") or "").strip(),
                "phone": (row.get("phone") or "").strip(),
                "location": (row.get("location") or "").strip(),
                "source_url": (
                    row.get("source_url")
                    or row.get("profile_source_url")
                    or ""
                ).strip(),
                "evidence": (row.get("evidence") or "").strip(),
                "extraction_method": (
                    row.get("extraction_method")
                    or "existing_data"
                ),
                "verified": row.get("verified") or "source_page"
            })

    return dedupe(records)


def dedupe(records):
    result = {}

    for row in records:
        key = (
            normalize(row.get("district")),
            normalize(row.get("name")),
            normalize(row.get("title"))
        )

        if not all(key):
            continue

        old = result.get(key)

        if not old:
            result[key] = row
            continue

        for field in [
            "email", "phone", "source_url",
            "evidence", "location"
        ]:
            if not old.get(field) and row.get(field):
                old[field] = row[field]

    return list(result.values())


def load_checkpoint():
    completed = set()
    records = []

    if CHECKPOINT_FILE.exists():
        try:
            state = json.loads(
                CHECKPOINT_FILE.read_text(encoding="utf-8")
            )
            completed = set(state.get("completed_leaids", []))
        except Exception:
            pass

    if RECORDS_FILE.exists():
        with RECORDS_FILE.open(
            "r", encoding="utf-8"
        ) as file:
            for line in file:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    return completed, records


def save_checkpoint(completed, records):
    CHECKPOINT_FILE.write_text(
        json.dumps({
            "completed_leaids": sorted(completed),
            "completed_count": len(completed),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }, indent=2),
        encoding="utf-8"
    )

    temp = RECORDS_FILE.with_suffix(".tmp")

    with temp.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    temp.replace(RECORDS_FILE)


def write_csv(path, records):
    fields = [
        "district", "name", "title", "email", "phone",
        "location", "source_url", "evidence",
        "extraction_method", "verified"
    ]

    with path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(records)


# --------------------------------------------------
# MAIN RUN
# --------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s"
    )

    DATA.mkdir(parents=True, exist_ok=True)

    districts = read_csv(DISTRICTS_FILE)

    if not districts:
        raise RuntimeError(
            "Could not read nj_districts.csv"
        )

    logging.info(
        "Loaded %s districts", len(districts)
    )

    existing = read_existing_records()

    counts = Counter(
        normalize(row["district"])
        for row in existing
    )

    targets = []

    for district in districts:
        name = district.get("LEA_NAME", "").strip()
        website = district.get("WEBSITE", "").strip()

        if not name or not website:
            continue

        if counts.get(normalize(name), 0) < MIN_ADMIN_PER_DISTRICT:
            targets.append(district)

    logging.info(
        "Existing leadership records: %s",
        len(existing)
    )

    logging.info(
        "Districts needing more contacts: %s",
        len(targets)
    )

    completed, checkpoint_records = load_checkpoint()

    target_ids = {
        str(row.get("LEAID", ""))
        for row in targets
    }

    checkpoint_records = [
        row for row in checkpoint_records
        if normalize(row.get("district", ""))
        in {normalize(d.get("LEA_NAME", "")) for d in targets}
    ]

    todo = [
        row for row in targets
        if str(row.get("LEAID", "")) not in completed
    ]

    logging.info(
        "Already completed: %s | Remaining: %s",
        len(completed), len(todo)
    )

    collected = list(checkpoint_records)
    failures = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(crawl_district, row): row
            for row in todo
        }

        done = 0

        for future in as_completed(futures):
            district_row = futures[future]
            lea_id = str(district_row.get("LEAID", ""))

            try:
                district, records, errors, error = future.result()

                collected.extend(records)

                for item in errors:
                    failures.append({
                        "district": district,
                        "url": item.get("url", ""),
                        "error": item.get("error", "")
                    })

                if error:
                    failures.append({
                        "district": district,
                        "url": district_row.get("WEBSITE", ""),
                        "error": error
                    })

            except Exception as exc:
                failures.append({
                    "district": district_row.get("LEA_NAME", ""),
                    "url": district_row.get("WEBSITE", ""),
                    "error": str(exc)[:400]
                })

            completed.add(lea_id)
            done += 1

            if done % 5 == 0 or done == len(todo):
                combined = dedupe(existing + collected)

                save_checkpoint(completed, collected)
                write_csv(OUTPUT_FILE, combined)

                logging.info(
                    "Progress: %s/%s | Total records: %s",
                    done, len(todo), len(combined)
                )

    all_records = dedupe(existing + collected)

    write_csv(OUTPUT_FILE, all_records)
    write_csv(REVIEW_FILE, all_records)

    coverage = []

    for district in districts:
        name = district.get("LEA_NAME", "").strip()

        count = sum(
            1 for row in all_records
            if normalize(row["district"]) == normalize(name)
        )

        coverage.append({
            "district": name,
            "website": district.get("WEBSITE", ""),
            "administrator_count": count,
            "status": (
                "HAS ADMINISTRATORS"
                if count else "NEEDS EXTRACTION"
            )
        })

    with COVERAGE_FILE.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "district", "website",
                "administrator_count", "status"
            ]
        )

        writer.writeheader()
        writer.writerows(coverage)

    with FAILURES_FILE.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["district", "url", "error"]
        )

        writer.writeheader()
        writer.writerows(failures)

    summary = {
        "total_districts": len(districts),
        "districts_with_admin_contacts": sum(
            1 for row in coverage
            if row["administrator_count"] > 0
        ),
        "districts_needing_extraction": sum(
            1 for row in coverage
            if row["administrator_count"] == 0
        ),
        "total_leadership_records": len(all_records),
        "records_with_email": sum(
            bool(row["email"]) for row in all_records
        ),
        "records_with_phone": sum(
            bool(row["phone"]) for row in all_records
        ),
        "new_records_collected": len(dedupe(collected)),
        "failed_pages": len(failures)
    }

    SUMMARY_FILE.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8"
    )

    save_checkpoint(completed, collected)

    print("\n========== EXTRACTION COMPLETE ==========")
    print(json.dumps(summary, indent=2))
    print("\nOutput folder:", DATA)


if __name__ == "__main__":
    main()
