
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

# Load credentials
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean(value):
    if value is None:
        return None

    value = str(value).strip()

    if value.lower() in ("", "nan", "none"):
        return None

    return value


def import_batches(table, records, batch_size=250):
    total = len(records)

    for start in range(0, total, batch_size):
        batch = records[start:start + batch_size]

        supabase.table(table).upsert(
            batch,
            on_conflict="nces_id"
        ).execute()

        print(f"{table}: {min(start + len(batch), total)}/{total}")


# 1. Load filtered CSV files
district_df = pd.read_csv(
    DATA_DIR / "nj_districts.csv",
    dtype=str,
    keep_default_na=False
)

school_df = pd.read_csv(
    DATA_DIR / "nj_schools.csv",
    dtype=str,
    keep_default_na=False
)

print("Loaded districts:", len(district_df))
print("Loaded schools:", len(school_df))


# 2. Prepare district records
district_records = []

for _, row in district_df.iterrows():
    district_records.append({
        "nces_id": clean(row["LEAID"]),
        "name": clean(row["LEA_NAME"]),
        "address": clean(row["MSTREET1"]),
        "city": clean(row["MCITY"]),
        "state": "NJ",
        "zip": clean(row["MZIP"]),
        "phone": clean(row["PHONE"]),
        "website": clean(row["WEBSITE"]),
        "source_url": "https://nces.ed.gov/ccd/files.asp"
    })

# 3. Import districts
print("\nImporting districts...")
import_batches("districts", district_records)


# 4. Fetch database-generated district IDs
print("\nFetching district IDs...")

response = supabase.table("districts") \
    .select("id,nces_id") \
    .execute()

district_map = {
    row["nces_id"]: row["id"]
    for row in response.data
}

print("Districts available:", len(district_map))


# 5. Prepare school records
school_records = []

unmatched = 0

for _, row in school_df.iterrows():

    lea_id = clean(row["LEAID"])

    district_id = district_map.get(lea_id)

    if district_id is None:
        unmatched += 1
        continue

    school_records.append({
        "nces_id": clean(row["NCESSCH"]),
        "district_id": district_id,
        "name": clean(row["SCH_NAME"]),
        "address": clean(row["MSTREET1"]),
        "city": clean(row["MCITY"]),
        "state": "NJ",
        "zip": clean(row["MZIP"]),
        "phone": clean(row["PHONE"]),
        "website": clean(row["WEBSITE"]),
        "source_url": "https://nces.ed.gov/ccd/files.asp"
    })


# 6. Import schools
print("\nImporting schools...")
import_batches("schools", school_records)


# 7. Final report
print("\n========== IMPORT COMPLETE ==========")
print("Districts processed:", len(district_records))
print("Schools processed:", len(school_records))
print("Unmatched schools:", unmatched)

print("\nSupabase database import finished!")
