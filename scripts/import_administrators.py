
import os
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

load_dotenv(BASE_DIR / ".env")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    raise ValueError("Supabase credentials missing in .env")

supabase = create_client(url, key)

df = pd.read_csv(
    DATA_DIR / "admin_candidates_clean.csv",
    dtype=str,
    keep_default_na=False
)

# Only import manually verified records
df = df[df["verified"].str.upper().str.strip() == "YES"]

# Fetch district IDs
response = supabase.table("districts").select(
    "id,name"
).execute()

district_map = {
    row["name"].strip(): row["id"]
    for row in response.data
}

inserted = 0
skipped = 0

for _, row in df.iterrows():

    district_name = row["district"].strip()
    district_id = district_map.get(district_name)

    if not district_id:
        print("District not found:", district_name)
        skipped += 1
        continue

    name = row["name"].strip()
    title = row["title"].strip()
    source_url = row["source_url"].strip()

    # Prevent duplicate records if script is run again
    existing = (
        supabase.table("administrators")
        .select("id")
        .eq("district_id", district_id)
        .eq("name", name)
        .eq("title", title)
        .limit(1)
        .execute()
    )

    if existing.data:
        print("Already exists:", name)
        skipped += 1
        continue

    record = {
        "district_id": district_id,
        "school_id": None,
        "name": name,
        "title": title,
        "email": None,
        "phone": None,
        "source_url": source_url,
        "verified_at": datetime.now(timezone.utc).isoformat()
    }

    supabase.table("administrators").insert(record).execute()

    print("Imported:", name, "-", title)
    inserted += 1

print("\n========== IMPORT SUMMARY ==========")
print("Verified candidates:", len(df))
print("Successfully imported:", inserted)
print("Skipped:", skipped)
