import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

INPUT_FILES = [
    DATA_DIR / "admin_pages_discovered_all.csv",
    DATA_DIR / "admin_pages_discovered.csv",
]

RAW_FILE = DATA_DIR / "admin_candidates_all_districts_raw.csv"
REVIEW_FILE = DATA_DIR / "admin_candidates_all_districts_review.csv"
ERROR_FILE = DATA_DIR / "admin_candidates_all_districts_errors.csv"
CHECKPOINT_FILE = DATA_DIR / "admin_candidates_all_districts_checkpoint.json"

RAW_FIELDS = [
    "district", "name", "title", "email", "phone", "location",
    "source_url", "evidence", "extraction_method", "verified"
]

ERROR_FIELDS = ["district", "url", "error"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
}

ADMIN_WORDS = [
    "superintendent", "principal", "assistant principal",
    "vice principal", "director", "supervisor", "administrator",
    "coordinator", "president", "chief", "business administrator",
    "business manager", "secretary", "dean", "counselor",
    "curriculum", "special education", "technology",
    "transportation", "human resources", "board secretary"
]

PERSON_SELECTORS = [
    ".fsConstituentItem",
    "article",
    ".staff-member",
    ".staff-item",
    ".person",
    ".profile",
    ".employee",
    ".administrator",
    ".directory-item",
    ".team-member",
]

TIMEOUT = 25
MAX_PAGINATION_PAGES = 30
WORKERS = 4


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def read_input():
    for path in INPUT_FILES:
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            if rows:
                print(f"Using input: {path.name} ({len(rows)} rows)")
                return rows

    raise FileNotFoundError(
        "Could not find admin_pages_discovered_all.csv "
        "or admin_pages_discovered.csv"
    )


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"completed_root_urls": []}


def save_checkpoint(data):
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    CHECKPOINT_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


def append_csv(path, fields, rows):
    if not rows:
        return

    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def fetch_page(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def same_domain(url_a, url_b):
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()


def is_valid_email(email):
    email = clean(email).lower()
    return bool(re.fullmatch(
        r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}",
        email
    ))


def name_tokens(name):
    ignored = {"mr", "mrs", "ms", "dr", "prof", "jr", "sr"}
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z]+", name)
        if token.lower() not in ignored and len(token) > 1
    }


def email_matches_name(email, name):
    if not email or not name:
        return False

    local = email.split("@", 1)[0].lower()
    tokens = name_tokens(name)

    if not tokens:
        return False

    # Require at least one meaningful name token in the email.
    return any(token in local for token in tokens)


def decode_finalsite_emails(block):
    found = []

    # Finalsite commonly reverses both the domain and local-part strings.
    pattern = re.compile(
        r"""FS\.util\.insertEmail\(\s*['"][^'"]+['"]\s*,\s*"""
        r"""['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]""",
        re.I
    )

    for script in block.find_all("script"):
        script_text = script.string or script.get_text(" ", strip=True)

        for domain_reversed, local_reversed in pattern.findall(script_text):
            domain = domain_reversed[::-1].lower()
            local = local_reversed[::-1].lower()
            email = f"{local}@{domain}"

            if is_valid_email(email):
                found.append(email)

    # Some pages place the JavaScript directly in an element attribute.
    for element in block.find_all(True):
        for attr_value in element.attrs.values():
            values = attr_value if isinstance(attr_value, list) else [attr_value]
            for value in values:
                if not isinstance(value, str):
                    continue

                for domain_reversed, local_reversed in pattern.findall(value):
                    email = (
                        f"{local_reversed[::-1]}@"
                        f"{domain_reversed[::-1]}"
                    ).lower()
                    if is_valid_email(email):
                        found.append(email)

    return list(dict.fromkeys(found))


def emails_in_block(block):
    found = []

    for link in block.select('a[href^="mailto:"]'):
        email = link.get("href", "").replace("mailto:", "").split("?")[0]
        email = clean(email).lower()
        if is_valid_email(email):
            found.append(email)

    text = block.get_text(" ", strip=True)
    for email in re.findall(
        r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",
        text,
        re.I
    ):
        email = email.lower()
        if is_valid_email(email):
            found.append(email)

    found.extend(decode_finalsite_emails(block))
    return list(dict.fromkeys(found))


def phone_in_block(block):
    for link in block.select('a[href^="tel:"]'):
        phone = clean(link.get("href", "").replace("tel:", ""))
        if phone:
            return phone
    return ""


def get_name(block):
    for selector in [
        ".fsFullName", ".name", ".staff-name",
        ".person-name", ".constituent-name",
        "h1", "h2", "h3", "h4"
    ]:
        element = block.select_one(selector)
        if element:
            value = clean(element.get_text(" ", strip=True))
            if 2 <= len(value.split()) <= 6 and not value.isdigit():
                return value

    return ""


def get_title(block):
    for selector in [
        ".fsDepartments", ".title", ".position",
        ".job-title", ".department", ".staff-title",
        ".fsConstituentDepartment"
    ]:
        element = block.select_one(selector)
        if element:
            value = clean(element.get_text(" ", strip=True))
            if value:
                return value

    return ""


def make_record(district, name, title, email, phone, location,
                source_url, evidence, method):
    return {
        "district": clean(district),
        "name": clean(name),
        "title": clean(title),
        "email": clean(email).lower(),
        "phone": clean(phone),
        "location": clean(location),
        "source_url": source_url,
        "evidence": clean(evidence)[:700],
        "extraction_method": method,
        "verified": "source_page"
    }


def extract_finalsite(soup, district, page_url):
    records = []

    for card in soup.select(".fsConstituentItem"):
        name = get_name(card)
        title = get_title(card)

        if not name:
            continue

        emails = [
            email for email in emails_in_block(card)
            if email_matches_name(email, name)
        ]

        phone = phone_in_block(card)
        evidence = card.get_text(" ", strip=True)

        # Keep the person even if the directory does not publish an email.
        if emails:
            for email in emails:
                records.append(make_record(
                    district, name, title, email, phone, "",
                    page_url, evidence, "finalsite_card"
                ))
        else:
            records.append(make_record(
                district, name, title, "", phone, "",
                page_url, evidence, "finalsite_card"
            ))

    return records


def extract_tables(soup, district, page_url):
    records = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [clean(cell.get_text(" ", strip=True)).lower()
                   for cell in header_cells]

        name_idx = next(
            (i for i, h in enumerate(headers)
             if "name" in h or "staff" in h or "administrator" in h),
            None
        )
        title_idx = next(
            (i for i, h in enumerate(headers)
             if any(word in h for word in
                    ["title", "position", "role", "job"])),
            None
        )
        location_idx = next(
            (i for i, h in enumerate(headers)
             if any(word in h for word in ["location", "school", "office"])),
            None
        )

        if name_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if name_idx >= len(cells):
                continue

            name = clean(cells[name_idx].get_text(" ", strip=True))
            if not name or len(name.split()) < 2:
                continue

            title = (
                clean(cells[title_idx].get_text(" ", strip=True))
                if title_idx is not None and title_idx < len(cells)
                else ""
            )
            location = (
                clean(cells[location_idx].get_text(" ", strip=True))
                if location_idx is not None and location_idx < len(cells)
                else ""
            )

            emails = [
                email for email in emails_in_block(row)
                if email_matches_name(email, name)
            ]
            phone = phone_in_block(row)
            evidence = row.get_text(" ", strip=True)

            if emails:
                for email in emails:
                    records.append(make_record(
                        district, name, title, email, phone, location,
                        page_url, evidence, "table_row"
                    ))
            else:
                records.append(make_record(
                    district, name, title, "", phone, location,
                    page_url, evidence, "table_row"
                ))

    return records


def extract_generic_cards(soup, district, page_url):
    records = []
    seen = set()

    for selector in PERSON_SELECTORS:
        for card in soup.select(selector):
            # Avoid treating a large parent container as one person.
            if len(card.find_all(["article", "li"])) > 8:
                continue

            name = get_name(card)
            title = get_title(card)
            if not name or not title:
                continue

            if not any(word in title.lower() for word in ADMIN_WORDS):
                continue

            key = (name.lower(), title.lower())
            if key in seen:
                continue
            seen.add(key)

            emails = [
                email for email in emails_in_block(card)
                if email_matches_name(email, name)
            ]
            phone = phone_in_block(card)
            evidence = card.get_text(" ", strip=True)

            if emails:
                for email in emails:
                    records.append(make_record(
                        district, name, title, email, phone, "",
                        page_url, evidence, "generic_card"
                    ))
            else:
                records.append(make_record(
                    district, name, title, "", phone, "",
                    page_url, evidence, "generic_card"
                ))

    return records


def pagination_links(soup, current_url):
    links = set()

    # Finalsite directory pagination
    for link in soup.select(".fsElementPagination a[href]"):
        absolute = urljoin(current_url, link["href"]).split("#")[0]

        if same_domain(current_url, absolute):
            links.add(absolute)

    # Other common pagination links
    for link in soup.select(
        '[class*=pagination] a[href], a[rel=next]'
    ):
        absolute = urljoin(current_url, link["href"]).split("#")[0]

        if same_domain(current_url, absolute):
            links.add(absolute)

    return links
    links = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        label = clean(link.get_text(" ", strip=True)).lower()
        classes = " ".join(link.get("class", [])).lower()
        rel = " ".join(link.get("rel", [])).lower()

        looks_like_pagination = (
            "next" in label or "older" in label or "last" in label
            or "next" in classes or "pagination" in classes
            or "next" in rel
            or bool(re.fullmatch(r"\d+", label))
        )

        if not looks_like_pagination:
            continue

        absolute = urljoin(current_url, href).split("#")[0]
        if (
            absolute.startswith(("http://", "https://"))
            and same_domain(current_url, absolute)
        ):
            links.add(absolute)

    return links


def extract_one_root(row):
    district = clean(row.get("district") or row.get("LEA_NAME"))
    root_url = clean(row.get("page_url"))

    if not root_url:
        return [], [], 0

    all_records = []
    errors = []

    try:
        # First check whether this is a Finalsite directory.
        html = fetch_page(root_url)
        initial_soup = BeautifulSoup(html, "html.parser")

        is_finalsite_directory = (
            initial_soup.select_one(".fsConstituentItem")
            and initial_soup.select_one(".fsElementPagination")
        )

        if is_finalsite_directory:
            print("    Finalsite directory detected. Using Chromium...")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                try:
                    page.goto(
                        root_url,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    page.locator(".fsConstituentItem").first.wait_for(
                        state="visible",
                        timeout=30000
                    )

                    visited_pages = set()
                    page_count = 0

                    while page_count < MAX_PAGINATION_PAGES:
                        label_element = page.locator(
                            ".fsPaginationLabel"
                        ).first

                        label = (
                            label_element.inner_text()
                            if label_element.count()
                            else ""
                        )

                        names = page.locator(
                            ".fsFullName"
                        ).all_inner_texts()

                        page_key = (label, tuple(names))

                        if page_key in visited_pages:
                            break

                        visited_pages.add(page_key)
                        page_count += 1

                        # Extract the currently visible directory page.
                        current_html = page.content()
                        soup = BeautifulSoup(
                            current_html,
                            "html.parser"
                        )

                        page_records = extract_finalsite(
                            soup, district, page.url
                        )

                        all_records.extend(page_records)

                        print(
                            f"    Browser page {page_count}: "
                            f"{label} | Records: {len(page_records)}"
                        )

                        next_button = page.locator(
                            ".fsNextPageLink"
                        ).first

                        if (
                            next_button.count() == 0
                            or not next_button.is_visible()
                            or next_button.get_attribute("disabled") is not None
                        ):
                            break

                        old_label = label

                        next_button.click()

                        try:
                            page.wait_for_function(
                                """oldLabel => {
                                    const el = document.querySelector(
                                        '.fsPaginationLabel'
                                    );
                                    return el && el.innerText.trim() !== oldLabel;
                                }""",
                                arg=old_label,
                                timeout=15000
                            )
                        except Exception:
                            # If the page does not change, stop safely.
                            break

                    return deduplicate(all_records), errors, page_count

                finally:
                    browser.close()

        # Ordinary non-Finalsite pages continue using requests.
        queue = [root_url]
        visited = set()

        while queue and len(visited) < MAX_PAGINATION_PAGES:
            url = queue.pop(0)

            if url in visited:
                continue

            visited.add(url)

            try:
                html = fetch_page(url)
                soup = BeautifulSoup(html, "html.parser")

                records = []
                records.extend(
                    extract_finalsite(soup, district, url)
                )
                records.extend(
                    extract_tables(soup, district, url)
                )
                records.extend(
                    extract_generic_cards(soup, district, url)
                )

                all_records.extend(records)

                for next_url in pagination_links(soup, url):
                    if next_url not in visited and next_url not in queue:
                        queue.append(next_url)

            except Exception as exc:
                errors.append({
                    "district": district,
                    "url": url,
                    "error": str(exc)[:500]
                })

        return deduplicate(all_records), errors, len(visited)

    except Exception as exc:
        errors.append({
            "district": district,
            "url": root_url,
            "error": str(exc)[:500]
        })

        return all_records, errors, 0
    district = clean(row.get("district") or row.get("LEA_NAME"))
    root_url = clean(row.get("page_url"))

    if not root_url:
        return [], [], 0

    queue = [root_url]
    visited = set()
    all_records = []
    errors = []

    while queue and len(visited) < MAX_PAGINATION_PAGES:
        url = queue.pop(0)

        if url in visited:
            continue
        visited.add(url)

        try:
            html = fetch_page(url)
            soup = BeautifulSoup(html, "html.parser")

            records = []
            records.extend(extract_finalsite(soup, district, url))
            records.extend(extract_tables(soup, district, url))
            records.extend(extract_generic_cards(soup, district, url))

            all_records.extend(records)

            for next_url in pagination_links(soup, url):
                if next_url not in visited and next_url not in queue:
                    queue.append(next_url)

        except Exception as exc:
            errors.append({
                "district": district,
                "url": url,
                "error": str(exc)[:500]
            })

    return all_records, errors, len(visited)


def deduplicate(records):
    unique = {}
    for row in records:
        key = (
            row["district"].lower(),
            row["name"].lower(),
            row["title"].lower(),
            row["email"].lower(),
            row["phone"].lower(),
            row["source_url"].lower()
        )
        unique[key] = row
    return list(unique.values())


def write_review_file():
    if not RAW_FILE.exists():
        return

    with RAW_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    rows = deduplicate(rows)
    rows.sort(key=lambda r: (
        r["district"].lower(),
        r["name"].lower(),
        r["title"].lower()
    ))

    with REVIEW_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Review CSV created: {REVIEW_FILE.name} ({len(rows)} records)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Test on the first N pages; 0 means all")
    parser.add_argument("--district", type=str, default="",
                        help="Only process rows matching this district name")
    parser.add_argument("--url", type=str, default="",
                    help="Test a specific directory URL")
    parser.add_argument("--resume", action="store_true",
                        help="Skip root URLs already in the checkpoint")
    args = parser.parse_args()

    rows = read_input()

    if args.url:
        rows = [{
            "district": args.district or "South Plainfield School District",
            "page_url": args.url,
            "status": "200"
        }]

    # Keep only successful discovery results when a status column exists.
    filtered = []
    for row in rows:
        status = clean(row.get("status")).lower()
        if status and status not in {"200", "success", "ok"}:
            continue
        filtered.append(row)

    # Remove duplicate district/page combinations.
    unique_pages = {}
    for row in filtered:
        url = clean(row.get("page_url"))
        district = clean(row.get("district") or row.get("LEA_NAME"))
        if url:
            unique_pages[(district.lower(), url.lower())] = row

    rows = list(unique_pages.values())

    if args.district:
        rows = [
            row for row in rows
            if args.district.lower() in clean(
                row.get("district") or row.get("LEA_NAME")
            ).lower()
        ]

    if args.limit > 0:
        rows = rows[:args.limit]

    checkpoint = load_checkpoint()
    completed = set(checkpoint.get("completed_root_urls", []))

    if args.resume:
        rows = [
            row for row in rows
            if clean(row.get("page_url")) not in completed
        ]

    print(f"Pages queued: {len(rows)}")
    print("Supabase: DISABLED")
    print("Output: CSV files only")

    for index, row in enumerate(rows, start=1):
        district = clean(row.get("district") or row.get("LEA_NAME"))
        url = clean(row.get("page_url"))

        print(f"[{index}/{len(rows)}] {district} | {url}")

        records, errors, page_count = extract_one_root(row)

        append_csv(RAW_FILE, RAW_FIELDS, records)
        append_csv(ERROR_FILE, ERROR_FIELDS, errors)

        completed.add(url)
        checkpoint["completed_root_urls"] = sorted(completed)
        checkpoint["last_district"] = district
        checkpoint["last_url"] = url
        checkpoint["total_pages_visited"] = (
            checkpoint.get("total_pages_visited", 0) + page_count
        )
        checkpoint["completed_root_count"] = len(completed)
        save_checkpoint(checkpoint)

        print(
            f"    Records: {len(records)} | "
            f"Pages visited: {page_count} | Errors: {len(errors)}"
        )

    write_review_file()
    print("\nExtraction finished.")
    print(f"Raw: {RAW_FILE}")
    print(f"Review: {REVIEW_FILE}")
    print(f"Errors: {ERROR_FILE}")
    print(f"Checkpoint: {CHECKPOINT_FILE}")


if __name__ == "__main__":
    main()