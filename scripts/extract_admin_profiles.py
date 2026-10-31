
import pandas as pd
import requests
import re
import time
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

BASE = Path("data/extracted/new_jersey")
INPUT = BASE / "admin_contacts_auto_extracted.csv"
OUTPUT = BASE / "admin_profile_contacts_review.csv"

HEADERS = {"User-Agent": "Mozilla/5.0"}

EMAIL_RE = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I
)
PHONE_RE = re.compile(
    r"(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}"
)

df = pd.read_csv(INPUT, dtype=str).fillna("")

def normalize(value):
    return re.sub(r"[^a-z]", "", str(value).lower())

def fetch(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as error:
        print("Could not open:", url, error)
        return None

def extract_contacts(soup):
    emails = []
    phones = []

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if EMAIL_RE.fullmatch(email):
                emails.append(email)

        if href.lower().startswith("tel:"):
            phone = href[4:].strip()
            if PHONE_RE.search(phone):
                phones.append(phone)

    text = soup.get_text(" ", strip=True)

    emails.extend(EMAIL_RE.findall(text))
    phones.extend(PHONE_RE.findall(text))

    return (
        list(dict.fromkeys(emails)),
        list(dict.fromkeys(phones))
    )

def find_profile_links(soup, name, source_url):
    target = normalize(name)
    matches = []

    for link in soup.find_all("a", href=True):
        label = normalize(link.get_text(" ", strip=True))
        href = urljoin(source_url, link["href"])

        if target in label or label in target and len(label) > 5:
            if urlparse(href).netloc == urlparse(source_url).netloc:
                matches.append(href)

    return list(dict.fromkeys(matches))

def process(index):
    row = df.loc[index]
    name = row["name"]
    source = row["source_url"]

    print("\nChecking:", name)

    source_soup = fetch(source)

    if source_soup is None:
        return index, "", "", ""

    # First inspect the original official page.
    emails, phones = extract_contacts(source_soup)

    # Find individual profile links.
    profile_links = find_profile_links(source_soup, name, source)

    used_url = source

    # Inspect matching profile pages.
    for profile_url in profile_links[:5]:
        print("  Profile:", profile_url)
        profile_soup = fetch(profile_url)

        if profile_soup is None:
            continue

        found_emails, found_phones = extract_contacts(profile_soup)

        if found_emails or found_phones:
            emails.extend(found_emails)
            phones.extend(found_phones)
            used_url = profile_url
            break

        time.sleep(0.3)

    email = emails[0] if emails else ""
    phone = phones[0] if phones else ""

    return index, email, phone, used_url

# Only process records with missing contact information.
targets = [
    i for i, row in df.iterrows()
    if not row["email"].strip() or not row["phone"].strip()
]

results = []

with ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(process, targets))

output_rows = []

for index, email, phone, used_url in results:
    row = df.loc[index].copy()

    # Preserve existing contacts.
    if not row["email"].strip():
        row["email"] = email

    if not row["phone"].strip():
        row["phone"] = phone

    row["profile_source_url"] = used_url
    output_rows.append(row)

# Keep every original record.
result_df = df.copy()
for index, email, phone, used_url in results:
    if not result_df.at[index, "email"].strip():
        result_df.at[index, "email"] = email
    if not result_df.at[index, "phone"].strip():
        result_df.at[index, "phone"] = phone

    result_df.at[index, "profile_source_url"] = used_url

result_df.to_csv(OUTPUT, index=False)

print("\n========== RESULTS ==========")
print("Profiles checked:", len(targets))
print("Output file:", OUTPUT)
print(
    "Records with email:",
    (result_df["email"].str.strip() != "").sum()
)
print(
    "Records with phone:",
    (result_df["phone"].str.strip() != "").sum()
)
