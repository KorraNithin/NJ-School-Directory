import csv
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

STAFF_URL = "https://www.bayheadschool.org/apps/staff/"

OUTPUT_FILE = "data/extracted/new_jersey/bay_head_edlio_test.csv"

HEADERS = {"User-Agent": "Mozilla/5.0"}

def decode_cloudflare(encoded):
    try:
        data = bytes.fromhex(encoded)
        key = data[0]
        return "".join(chr(value ^ key) for value in data[1:])
    except Exception:
        return ""

def extract_emails(element):
    emails = set()

    for link in element.select('a[href^="mailto:"]'):
        email = link.get("href", "").replace("mailto:", "").split("?")[0]
        if email:
            emails.add(email.strip())

    for item in element.select("[data-cfemail]"):
        email = decode_cloudflare(item.get("data-cfemail", ""))
        if email:
            emails.add(email.strip())

    return sorted(emails)

def extract_phones(element):
    phones = set()

    for link in element.select('a[href^="tel:"]'):
        phone = link.get("href", "").replace("tel:", "").strip()
        if phone:
            phones.add(phone)

    return sorted(phones)

def is_admin_role(title):
    title = title.lower()

    excluded = [
        "assistant to",
        "athletic",
        "coach",
        "teacher",
        "secretary",
        "custodian",
        "nurse"
    ]

    if any(word in title for word in excluded):
        return False

    relevant = [
        "superintendent",
        "chief school administrator",
        "business administrator",
        "school business administrator",
        "principal",
        "executive director",
        "assistant principal",
        "director of special services",
        "director of student services",
        "director of curriculum",
        "director of instruction",
        "assistant superintendent",
        "deputy superintendent"
    ]

    return any(role in title for role in relevant)

def main():
    print("Fetching Bay Head staff directory...")

    response = requests.get(
        STAFF_URL,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # General school contacts are collected separately.
    general_email_set = set()
    general_phone_set = set()

    for block in soup.select(".footer-info-block"):
        general_email_set.update(extract_emails(block))
        general_phone_set.update(extract_phones(block))

    general_emails = sorted(general_email_set)
    general_phones = sorted(general_phone_set)

    rows = []
    staff_cards = soup.select("li.staff")

    print("Staff cards found:", len(staff_cards))

    for staff in staff_cards:
        name_element = staff.select_one("a.name")
        title_element = staff.select_one(".user-position")

        if not name_element:
            continue

        name = name_element.get_text(" ", strip=True)
        title = title_element.get_text(" ", strip=True) if title_element else ""

        if not is_admin_role(title):
            continue

        profile_url = urljoin(
            STAFF_URL,
            name_element.get("href", "")
        )

        # Only contacts inside this person's own card
        # are treated as individual contacts.
        individual_emails = extract_emails(staff)
        individual_phones = extract_phones(staff)

        rows.append({
            "district": "Bay Head",
            "name": name,
            "title": title,
            "email": "; ".join(individual_emails),
            "email_type": "individual" if individual_emails else "",
            "phone": "; ".join(individual_phones),
            "phone_type": "individual" if individual_phones else "",
            "general_school_email": "; ".join(general_emails),
            "general_school_phone": "; ".join(general_phones),
            "profile_url": profile_url,
            "source_url": STAFF_URL,
            "verified": "NO",
            "review_status": "NEEDS_REVIEW"
        })

    columns = [
        "district", "name", "title",
        "email", "email_type",
        "phone", "phone_type",
        "general_school_email", "general_school_phone",
        "profile_url", "source_url",
        "verified", "review_status"
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print("\nADMINISTRATOR CANDIDATES:")
    for row in rows:
        print(
            row["name"],
            "|", row["title"],
            "| Individual email:", row["email"] or "Not found",
            "| Individual phone:", row["phone"] or "Not found"
        )

    print("\nGENERAL SCHOOL CONTACTS:")
    print("Emails:", general_emails)
    print("Phones:", general_phones)

    print("\nCandidates extracted:", len(rows))
    print("Saved to:", OUTPUT_FILE)
    print("No Supabase changes were made.")

if __name__ == "__main__":
    main()
