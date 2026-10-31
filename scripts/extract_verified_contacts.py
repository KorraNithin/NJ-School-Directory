
import pandas as pd
import requests
import re
from pathlib import Path
from bs4 import BeautifulSoup

BASE = Path("data/extracted/new_jersey")
INPUT = BASE / "admin_contacts_clean.csv"
OUTPUT = BASE / "admin_contacts_with_contacts.csv"

EMAIL_PATTERN = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.I
)

PHONE_PATTERN = re.compile(
    r"(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SchoolDirectoryResearch/1.0)"
}

df = pd.read_csv(INPUT, dtype=str).fillna("")

session = requests.Session()
session.headers.update(HEADERS)

def normalize(value):
    return re.sub(r"[^a-z]", "", value.lower())

def extract_person_contacts(soup, person_name):
    target = normalize(person_name.replace("Dr. ", ""))
    email = ""
    phone = ""

    # Find the smallest page element containing the person's name.
    matches = soup.find_all(
        string=lambda text: text and target in normalize(str(text))
    )

    for match in matches:
        element = match.parent

        for _ in range(6):
            if element is None:
                break

            text = element.get_text(" ", strip=True)

            # Avoid large sections containing many different people.
            if len(text) > 1500:
                break

            # Collect directly linked email addresses and phone numbers.
            emails = []
            phones = []

            for link in element.find_all("a", href=True):
                href = link["href"].strip()

                if href.lower().startswith("mailto:"):
                    value = href[7:].split("?")[0].strip()
                    if EMAIL_PATTERN.fullmatch(value):
                        emails.append(value)

                elif href.lower().startswith("tel:"):
                    value = href[4:].strip()
                    if PHONE_PATTERN.search(value):
                        phones.append(value)

            # Also inspect visible text in this person's small section.
            if not emails:
                emails = EMAIL_PATTERN.findall(text)

            if not phones:
                phones = PHONE_PATTERN.findall(text)

            if emails or phones:
                email = emails[0] if emails else ""
                phone = phones[0] if phones else ""
                return email, phone

            element = element.parent

    return email, phone


for index, row in df.iterrows():
    name = row["name"]
    url = row["source_url"]

    if not url:
        continue

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        email, phone = extract_person_contacts(soup, name)

        # Only fill missing fields; never overwrite existing data.
        if not df.at[index, "email"] and email:
            df.at[index, "email"] = email

        if not df.at[index, "phone"] and phone:
            df.at[index, "phone"] = phone

        print(
            f"{name}: "
            f"Email={'Found' if email else 'Not found'}, "
            f"Phone={'Found' if phone else 'Not found'}"
        )

    except Exception as error:
        print(f"Could not process {name}: {error}")

df.to_csv(OUTPUT, index=False)

print("\n========== CONTACT EXTRACTION SUMMARY ==========")
print("Total administrators:", len(df))
print("Records with emails:", (df["email"].str.strip() != "").sum())
print("Records with phones:", (df["phone"].str.strip() != "").sum())
print("Saved to:", OUTPUT)
