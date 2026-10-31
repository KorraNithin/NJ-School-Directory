import os
import csv
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

load_dotenv(BASE_DIR / "backend" / ".env")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    raise ValueError("Existing Supabase credentials could not be loaded.")

supabase = create_client(url, key)

with (DATA_DIR / "supabase_admin_import_100_batch4.csv").open(
    encoding="utf-8-sig", newline=""
) as f:
    rows = list(csv.DictReader(f))

districts = supabase.table("districts").select("id,name").execute().data
district_map = {d["name"].strip().lower(): d["id"] for d in districts}

inserted = skipped = failed = 0

for row in rows:
    district_id = district_map.get(row["district"].strip().lower())
    name = row["name"].strip()
    title = row["title"].strip()

    if not district_id or not name:
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
            skipped += 1
            continue

        supabase.table("administrators").insert({
            "district_id": district_id,
            "school_id": None,
            "name": name,
            "title": title or None,
            "email": row["email"].strip() or None,
            "phone": row["phone"].strip() or None,
            "source_url": row["source_url"].strip() or None,
            "verified_at": None
        }).execute()

        inserted += 1
        print("Imported:", name)

    except Exception as e:
        failed += 1
        print("Failed:", name, str(e))

print("\nIMPORT SUMMARY")
print("Total CSV rows:", len(rows))
print("Imported:", inserted)
print("Skipped:", skipped)
print("Failed:", failed)


