
import pandas as pd
import requests
import re
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    BASE_DIR / "data" / "extracted" /
    "new_jersey" / "admin_pages_discovered.csv"
)

OUTPUT_FILE = (
    BASE_DIR / "data" / "extracted" /
    "new_jersey" / "admin_contacts_review.csv"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 NJSchoolDirectoryResearch/1.0"
}

ADMIN_ROLES = [
    "assistant superintendent",
    "deputy superintendent",
    "school business administrator",
    "business administrator",
    "chief operating officer",
    "chief of operations",
    "executive director",
    "clinical director",
    "assistant principal",
    "vice principal",
    "superintendent",
    "principal",
    "head of school",
    "director",
]

STOP_WORDS = {
    "september", "october", "november", "december",
    "january", "february", "march", "april",
    "may", "june", "july", "august",
    "spotlight", "welcome", "office", "staff",
    "directory", "administration", "administrator",
    "search", "clear", "close", "menu", "home",
    "contact", "school", "district", "high",
    "middle", "elementary", "board", "education",
    "information", "read", "more", "click",
    "principal", "superintendent", "director",
    "executive", "assistant", "business",
    "leadership", "team", "our", "the",
}

NAME_PATTERN = re.compile(
    r"^(?:Dr\.?\s+)?"
    r"[A-Z][A-Za-z'’-]+"
    r"(?:\s+[A-Z]\.?)?"
    r"(?:\s+[A-Z][A-Za-z'’-]+){1,2}"
    r"\.?$"
)

EMAIL_PATTERN = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.I
)

PHONE_PATTERN = re.compile(
    r"(?:\+1[-.\s]?)?"
    r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)


def valid_name(value):
    value = re.sub(r"\s+", " ", value).strip(" ,:;|")

    if not NAME_PATTERN.fullmatch(value):
        return False

    words = re.findall(r"[A-Za-z]+", value.lower())

    if len(words) < 2 or len(words) > 4:
        return False

    if any(word in STOP_WORDS for word in words):
        return False

    return True


def get_title(text):
    lower = text.lower()

    for role in ADMIN_ROLES:
        if role in lower:
            return role.title()

    return ""


def find_person_name(lines):
    # First check individual text lines.
    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()

        if valid_name(line):
            return line

    # Then check whether a name and title share a line.
    for line in lines:
        for role in ADMIN_ROLES:
            match = re.search(
                rf"(.+?)\s+{re.escape(role)}\b",
                line,
                re.I
            )

            if match:
                possible_name = match.group(1).strip()

                if valid_name(possible_name):
                    return possible_name

    return ""


def extract_contacts(page):
    results = []

    district = page["district"]
    url = page["page_url"]

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup([
            "script", "style", "noscript",
            "header", "footer", "nav"
        ]):
            element.decompose()

        # Prefer individual staff/profile blocks and table rows.
        blocks = soup.find_all([
            "article", "tr", "li",
            "h1", "h2", "h3", "h4",
            "p"
        ])

        # Include common profile/card containers.
        blocks += soup.select(
            '[class*="staff"], '
            '[class*="person"], '
            '[class*="profile"], '
            '[class*="member"], '
            '[class*="employee"]'
        )

        seen = set()

        for block in blocks:
            text = block.get_text(" ", strip=True)

            if not text or len(text) > 800:
                continue

            title = get_title(text)

            if not title:
                continue

            lines = [
                line.strip()
                for line in block.get_text("\n", strip=True).splitlines()
                if line.strip()
            ]

            name = find_person_name(lines)

            if not name:
                continue

            key = (name.lower(), title.lower(), url)

            if key in seen:
                continue

            seen.add(key)

            # Only retain an email when its address appears
            # to correspond to this person's name.
            emails = EMAIL_PATTERN.findall(text)
            email = ""

            name_parts = [
                word.lower()
                for word in re.findall(r"[A-Za-z]+", name)
                if word.lower() not in {"dr"}
            ]

            if len(emails) == 1:
                email_parts = re.split(
                    r"[._+-]",
                    emails[0].split("@")[0].lower()
                )

                if any(
                    part in email_parts
                    for part in name_parts
                    if len(part) > 2
                ):
                    email = emails[0]

            # Keep a phone only when an explicit telephone link
            # appears in this person's block.
            phone = ""

            for anchor in block.find_all("a", href=True):
                if anchor["href"].lower().startswith("tel:"):
                    numbers = PHONE_PATTERN.findall(
                        anchor.get_text(" ", strip=True)
                        + " " + anchor["href"]
                    )

                    if numbers:
                        phone = numbers[0]
                        break

            results.append({
                "district": district,
                "name": name,
                "title": title,
                "email": email,
                "phone": phone,
                "source_url": url,
                "evidence": text[:500],
                "verified": "NO"
            })

        print(
            f"Processed: {district} | "
            f"{len(results)} candidates"
        )

    except requests.RequestException as error:
        print(f"Failed: {district} | {error}")

    return results


def main():
    pages = pd.read_csv(
        INPUT_FILE,
        dtype=str
    ).fillna("")

    all_results = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(extract_contacts, row.to_dict())
            for _, row in pages.iterrows()
        ]

        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception as error:
                print("Extraction error:", error)

    output = pd.DataFrame(
        all_results,
        columns=[
            "district",
            "name",
            "title",
            "email",
            "phone",
            "source_url",
            "evidence",
            "verified"
        ]
    )

    if not output.empty:
        output = output.drop_duplicates(
            subset=["district", "name", "title", "source_url"]
        )

        output = output.sort_values(
            ["district", "name"]
        )

    output.to_csv(OUTPUT_FILE, index=False)

    print("\n========== IMPROVED EXTRACTION SUMMARY ==========")
    print("Pages checked:", len(pages))
    print("Candidates found:", len(output))

    if not output.empty:
        print("\nCandidates by title:")
        print(output["title"].value_counts())

        print("\nRecords with email:", (output["email"] != "").sum())
        print("Records with phone:", (output["phone"] != "").sum())

    print("\nSaved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
