import pandas as pd
import requests
import re
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data" / "extracted" / "new_jersey"

INPUT = DATA / "admin_pages_priority.csv"
OUTPUT = DATA / "admin_contacts_priority_test.csv"
FAILURES = DATA / "admin_extraction_test_failures.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NJSchoolDirectoryResearch/1.0)"
}

ROLES = [
    "assistant superintendent",
    "deputy superintendent",
    "superintendent",
    "school business administrator",
    "business administrator",
    "chief operating officer",
    "chief of operations",
    "executive director",
    "assistant principal",
    "vice principal",
    "principal",
    "head of school",
    "director of special services",
    "director of curriculum",
    "director of education",
    "director",
]

ROLE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(r) for r in ROLES) + r")\b",
    re.I
)

EMAIL_PATTERN = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I
)

PHONE_PATTERN = re.compile(
    r"(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)

STOP = {
    "staff", "directory", "administration", "administrator",
    "school", "district", "principal", "superintendent",
    "director", "assistant", "business", "education",
    "contact", "office", "board", "faculty", "leadership",
    "team", "welcome", "home", "search", "menu"
}

def clean_name(value):
    value = re.sub(r"\s+", " ", value).strip(" ,:;|.-")
    value = re.sub(r"^(Dr\.?|Mr\.?|Mrs\.?|Ms\.?)\s+", "", value, flags=re.I)

    words = re.findall(r"[A-Za-z][A-Za-z'-]*", value)

    if not 2 <= len(words) <= 4:
        return ""

    if any(word.lower() in STOP for word in words):
        return ""

    if not all(word[0].isupper() for word in words):
        return ""

    return value


def extract_name(lines, role_match):
    # First look for a name on a separate line.
    for line in lines:
        name = clean_name(line)
        if name:
            return name

    # Then look for a name immediately before the job title.
    before_role = role_match.string[:role_match.start()]
    before_role = before_role.split("\n")[-1].strip()

    name = clean_name(before_role)
    if name:
        return name

    return ""


def extract_page(page):
    results = []
    failure = None

    try:
        response = requests.get(
            page["page_url"],
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

        selectors = [
            "article", "tr", "li",
            '[class*="staff"]',
            '[class*="person"]',
            '[class*="profile"]',
            '[class*="employee"]',
            '[class*="directory"]',
            '[class*="card"]'
        ]

        blocks = []
        seen_text = set()

        for selector in selectors:
            for block in soup.select(selector):
                text = block.get_text("\n", strip=True)
                if text and text not in seen_text:
                    seen_text.add(text)
                    blocks.append(block)

        for block in blocks:
            text = block.get_text("\n", strip=True)

            if len(text) < 15 or len(text) > 1200:
                continue

            role_match = ROLE_PATTERN.search(text)
            if not role_match:
                continue

            lines = [
                re.sub(r"\s+", " ", line).strip()
                for line in text.splitlines()
                if line.strip()
            ]

            name = extract_name(lines, role_match)
            if not name:
                continue

            title = role_match.group(1).title()

            emails = list(dict.fromkeys(EMAIL_PATTERN.findall(text)))
            phones = list(dict.fromkeys(PHONE_PATTERN.findall(text)))

            # Only associate a single email when it appears to match
            # the person's name. Otherwise leave it blank for review.
            email = ""
            name_parts = [
                p.lower() for p in re.findall(r"[A-Za-z]+", name)
            ]

            for candidate in emails:
                local_parts = re.split(
                    r"[._+-]",
                    candidate.split("@")[0].lower()
                )

                if any(
                    part in local_parts
                    for part in name_parts
                    if len(part) > 2
                ):
                    email = candidate
                    break

            # A phone is retained only when there is exactly one
            # phone number in this candidate's block.
            phone = phones[0] if len(phones) == 1 else ""

            results.append({
                "district": page["district"],
                "name": name,
                "title": title,
                "email": email,
                "phone": phone,
                "source_url": page["page_url"],
                "evidence": re.sub(r"\s+", " ", text)[:600],
                "verified": "NO",
                "review_status": "NEEDS_REVIEW"
            })

        print(
            f"Checked: {page['district']} | "
            f"Candidates: {len(results)}"
        )

    except Exception as error:
        failure = {
            "district": page["district"],
            "page_url": page["page_url"],
            "error": str(error)[:500]
        }
        print(f"Failed: {page['district']} | {error}")

    return results, failure


def main():
    pages = pd.read_csv(INPUT, dtype=str).fillna("")

    # Use the highest-priority page from each district.
    pages["priority_score"] = pd.to_numeric(
        pages["priority_score"], errors="coerce"
    ).fillna(0)

    pages = pages.sort_values(
        "priority_score", ascending=False
    )

    pages = pages.drop_duplicates(
        subset=["district"], keep="first"
    ).head(30)

    print("TESTING PAGES:", len(pages))
    print("DISTRICTS:", pages["district"].nunique())

    all_results = []
    all_failures = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(extract_page, row.to_dict())
            for _, row in pages.iterrows()
        ]

        for future in as_completed(futures):
            results, failure = future.result()
            all_results.extend(results)

            if failure:
                all_failures.append(failure)

    columns = [
        "district", "name", "title", "email", "phone",
        "source_url", "evidence", "verified", "review_status"
    ]

    output = pd.DataFrame(all_results, columns=columns)

    if not output.empty:
        output = output.drop_duplicates(
            subset=["district", "name", "title", "source_url"]
        )
        output = output.sort_values(["district", "name"])

    output.to_csv(OUTPUT, index=False)
    pd.DataFrame(all_failures).to_csv(FAILURES, index=False)

    print("\n========== TEST SUMMARY ==========")
    print("Pages checked:", len(pages))
    print("Candidates found:", len(output))
    print("Pages failed:", len(all_failures))

    if not output.empty:
        print("Records with email:", (output["email"] != "").sum())
        print("Records with phone:", (output["phone"] != "").sum())
        print("\nCandidates by district:")
        print(output.groupby("district").size().to_string())

    print("\nSaved candidates:", OUTPUT)
    print("Saved failures:", FAILURES)


if __name__ == "__main__":
    main()
