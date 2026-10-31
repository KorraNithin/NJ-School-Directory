
import pandas as pd
import requests
import re
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor

BASE = Path("data/extracted/new_jersey")

INPUT = BASE / "admin_contacts_with_contacts.csv"
OUTPUT = BASE / "admin_contacts_auto_extracted.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

EMAIL_RE = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I
)

PHONE_RE = re.compile(
    r"(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}"
)

# Only process records outside South Bergen.
df = pd.read_csv(INPUT, dtype=str).fillna("")

def clean_name(name):
    return re.sub(r"[^a-z]", "", name.lower().replace("dr.", ""))

def get_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print("Page error:", url, e)
        return None

def find_person_block(soup, name):
    target = clean_name(name)

    for element in soup.find_all(
        string=lambda x: x and target in clean_name(str(x))
    ):
        node = element.parent

        # Search progressively larger surrounding elements.
        for _ in range(5):
            if node is None:
                break

            text = node.get_text(" ", strip=True)

            if len(text) > 1800:
                break

            if target in clean_name(text):
                return node

            node = node.parent

    return None

def extract_from_block(block):
    email = ""
    phone = ""

    if block is None:
        return email, phone

    for link in block.find_all("a", href=True):
        href = link["href"].strip()

        if href.lower().startswith("mailto:"):
            candidate = href[7:].split("?")[0].strip()
            if EMAIL_RE.fullmatch(candidate):
                email = email or candidate

        elif href.lower().startswith("tel:"):
            candidate = href[4:].strip()
            if PHONE_RE.search(candidate):
                phone = phone or candidate

    text = block.get_text(" ", strip=True)

    if not email:
        emails = EMAIL_RE.findall(text)
        if emails:
            email = emails[0]

    if not phone:
        phones = PHONE_RE.findall(text)
        if phones:
            phone = phones[0]

    return email, phone

def process_row(index):
    row = df.loc[index]

    # Do not overwrite already populated contacts.
    if row["email"].strip() and row["phone"].strip():
        return index, "", ""

    soup = get_page(row["source_url"])

    if soup is None:
        return index, "", ""

    block = find_person_block(soup, row["name"])

    email, phone = extract_from_block(block)

    return index, email, phone

remaining = [
    i for i, row in df.iterrows()
    if "South Bergen" not in row["district"]
]

print("Processing administrators:", len(remaining))

with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(process_row, remaining))

for index, email, phone in results:
    if email and not df.at[index, "email"].strip():
        df.at[index, "email"] = email

    if phone and not df.at[index, "phone"].strip():
        df.at[index, "phone"] = phone

    print(
        df.at[index, "name"],
        "| Email:", "Found" if email else "Not found",
        "| Phone:", "Found" if phone else "Not found"
    )

df.to_csv(OUTPUT, index=False)

print("\n========== FINAL SUMMARY ==========")
print("Total records:", len(df))
print("Emails found:", (df["email"].str.strip() != "").sum())
print("Phones found:", (df["phone"].str.strip() != "").sum())
print("Output:", OUTPUT)
