
import pandas as pd
import requests
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "extracted" / "new_jersey"

from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials missing from backend/.env")

INPUT = BASE / "admin_contacts_final_review.csv"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def normalize(value):
    return " ".join(str(value).split()).strip().lower()

def get_records(table, params):
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        timeout=30
    )
    response.raise_for_status()
    return response.json()

def insert_record(payload):
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/administrators",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    return response.json()

df = pd.read_csv(INPUT, dtype=str).fillna("")

districts = get_records(
    "districts",
    {"select": "id,name"}
)

admins = get_records(
    "administrators",
    {"select": "id,name,district_id"}
)

district_lookup = {
    normalize(d["name"]): d["id"]
    for d in districts
}

existing = {
    (a["district_id"], normalize(a["name"]))
    for a in admins
}

inserted = 0
skipped = 0
errors = []

for _, row in df.iterrows():

    district_name = normalize(row["district"])
    district_id = district_lookup.get(district_name)

    if not district_id:
        errors.append(f"{row['name']}: District not found")
        continue

    key = (district_id, normalize(row["name"]))

    if key in existing:
        skipped += 1
        print("Already exists:", row["name"])
        continue

    email = row["email"].strip() or None
    phone = row["phone"].strip() or None

    source_url = (
        row.get("profile_source_url", "").strip()
        or row["source_url"].strip()
    )

    payload = {
        "district_id": district_id,
        "school_id": None,
        "name": row["name"].strip(),
        "title": row["title"].strip(),
        "email": email,
        "phone": phone,
        "source_url": source_url,
        "verified_at": None,
        "email_type": row["email_type"].strip() or None,
        "phone_type": row["phone_type"].strip() or None
    }

    try:
        insert_record(payload)
        existing.add(key)
        inserted += 1
        print("Inserted:", row["name"])

    except Exception as error:
        errors.append(f"{row['name']}: {error}")
        print("Failed:", row["name"], error)

print("\n========== INSERT SUMMARY ==========")
print("New administrators inserted:", inserted)
print("Already existing:", skipped)
print("Errors:", len(errors))

for error in errors:
    print(error)

print("\nNew records remain unverified.")
