
import pandas as pd
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "extracted" / "new_jersey"

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

df = pd.read_csv(INPUT, dtype=str).fillna("")

def get_records(table, params):
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        timeout=30
    )
    response.raise_for_status()
    return response.json()

def update_record(record_id, payload):
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/administrators",
        headers=headers,
        params={"id": f"eq.{record_id}"},
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    return response.json()

districts = get_records(
    "districts",
    {"select": "id,name"}
)

admins = get_records(
    "administrators",
    {"select": "id,name,district_id,email,phone"}
)

district_lookup = {
    " ".join(d["name"].split()).lower(): d["id"]
    for d in districts
}

admin_lookup = {}

for admin in admins:
    key = (
        admin["district_id"],
        admin["name"].strip().lower()
    )
    admin_lookup[key] = admin

updated = 0
skipped = 0
not_found = []

for _, row in df.iterrows():
    district_name = " ".join(row["district"].split()).lower()
    district_id = district_lookup.get(district_name)

    if not district_id:
        not_found.append(row["name"] + " (district not found)")
        continue

    key = (district_id, row["name"].strip().lower())
    admin = admin_lookup.get(key)

    if not admin:
        not_found.append(row["name"] + " (administrator not found)")
        continue

    # Do not overwrite existing contacts.
    payload = {}

    email = row["email"].strip()
    phone = row["phone"].strip()

    if email and not admin.get("email"):
        payload["email"] = email
        payload["email_type"] = row["email_type"]

    if phone and not admin.get("phone"):
        payload["phone"] = phone
        payload["phone_type"] = row["phone_type"]

    # Preserve existing verified records.
    if payload:
        update_record(admin["id"], payload)
        updated += 1
        print("Updated:", row["name"])
    else:
        skipped += 1
        print("Skipped (already populated):", row["name"])

print("\n========== UPDATE SUMMARY ==========")
print("Records updated:", updated)
print("Records skipped:", skipped)
print("Records not matched:", len(not_found))

for item in not_found:
    print("Not matched:", item)

print("\nExisting contacts were not overwritten.")
print("Automatically extracted contacts were not marked verified.")
