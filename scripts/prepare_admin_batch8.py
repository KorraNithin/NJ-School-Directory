import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "extracted" / "new_jersey"
OUTPUT = DATA / "supabase_admin_import_100_batch8.csv"

sources = [
    "admin_fast_run_raw.csv",
    "NJ_School_Admin_Directory_FINAL.csv",
    "admin_candidates_all_districts_raw.csv",
]

previous_batches = [
    "supabase_admin_import_100.csv",
    *[f"supabase_admin_import_100_batch{i}.csv" for i in range(2, 7)],
    "supabase_admin_import_1000_batch7.csv",
]

def norm(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())

def valid_name(name):
    name = (name or "").strip()
    if len(name) < 4 or len(name) > 90:
        return False
    if re.search(r"[\d@]|https?://", name, re.I):
        return False
    if len(name.split()) < 2:
        return False
    bad = [
        "our vision", "photo album", "close menu", "search clear",
        "superintendent's office", "business administrator",
        "administration office", "staff directory"
    ]
    return not any(x in norm(name) for x in bad)

priority = {
    "superintendent": 100,
    "assistant superintendent": 95,
    "principal": 90,
    "business administrator": 90,
    "head of school": 90,
    "assistant principal": 85,
    "director": 80,
    "chief": 80,
    "deputy": 75,
    "administrator": 70,
    "coordinator": 55,
    "supervisor": 55,
}

excluded = set()
for filename in previous_batches:
    path = DATA / filename
    if not path.exists():
        print(f"WARNING: Previous batch not found: {filename}")
        continue
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            excluded.add((norm(row.get("district")), norm(row.get("name"))))

candidates = {}
for filename in sources:
    path = DATA / filename
    if not path.exists():
        print(f"WARNING: Source not found: {filename}")
        continue

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            district = (row.get("district") or "").strip()
            name = (row.get("name") or "").strip()
            title = (row.get("title") or "").strip()

            key = (norm(district), norm(name))
            if not district or not valid_name(name) or key in excluded:
                continue

            score = 0
            title_lower = norm(title)
            for role, points in priority.items():
                if role in title_lower:
                    score = max(score, points)

            score += 20 if row.get("email") else 0
            score += 10 if row.get("phone") else 0
            score += 5 if row.get("source_url") else 0

            row["_score"] = score
            if key not in candidates or score > candidates[key]["_score"]:
                candidates[key] = row

ranked = sorted(
    candidates.values(),
    key=lambda r: r["_score"],
    reverse=True
)

if len(ranked) < 100:
    raise SystemExit(
        f"Only {len(ranked)} new candidates remain. No batch created."
    )

selected = ranked[:100]
fields = [
    "district", "name", "title", "email", "phone",
    "location", "source_url", "evidence",
    "extraction_method", "verified"
]

with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(selected)

print(f"Batch 8 created: {OUTPUT}")
print(f"Records: {len(selected)}")
print(f"With email: {sum(bool(r.get('email')) for r in selected)}")
print(f"With phone: {sum(bool(r.get('phone')) for r in selected)}")
