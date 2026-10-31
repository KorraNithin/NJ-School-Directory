import os
import csv
import re
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"
CSV_FILE = DATA_DIR / "supabase_admin_import_100.csv"

load_dotenv(BASE_DIR / ".env")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    raise ValueError("Supabase credentials missing in .env")

supabase = create_client(url, key)

def normalize(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()

with CSV_FILE.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

district_response = supabase.table("districts").select("id,name").execute()

district_map = {
    normalize(d["name"]): d["id"]
    for d in district_response.data
}

inserted = 0
skipped = 0
failed = 0

print(f"CSV records found: {len(rows)}")
print(f"Districts loaded: {len(district_map)}")
print("\nStarting import...\n")

for row in rows:
    district_name = row.get("district", "").strip()
    name = row.get("name", "").strip()
    title = row.get("title", "").strip()

    district_id = district_map.get(normalize(district_name))

    if not district_id or not name:
        print("SKIPPED - District not found or name missing:", name)
        skipped += 1
        continue

    try:
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
            print("ALREADY EXISTS:", name)
            skipped += 1
            continue

        record = {
            "district_id": district_id,
            "school_id": None,
            "name": name,
            "title": title or None,
            "email": row.get("email", "").strip() or None,
            "phone": row.get("phone", "").strip() or None,
            "source_url": row.get("source_url", "").strip() or None,
            "verified_at": None
        }

        supabase.table("administrators").insert(record).execute()

        print("IMPORTED:", name, "-", title)
        inserted += 1

    except Exception as e:
        print("FAILED:", name, "-", str(e))
        failed += 1

print("\n========== IMPORT SUMMARY ==========")
print("CSV records:", len(rows))
print("Successfully imported:", inserted)
print("Skipped:", skipped)
print("Failed:", failed)
print("====================================")
