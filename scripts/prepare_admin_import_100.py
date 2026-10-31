import csv
import re
import json
from pathlib import Path
from collections import Counter

BASE = Path("data/extracted/new_jersey")
INPUTS = [
    BASE / "admin_fast_run_raw.csv",
    BASE / "NJ_School_Admin_Directory_FINAL.csv",
    BASE / "admin_candidates_all_districts_raw.csv",
]

OUTPUT = BASE / "supabase_admin_import_100.csv"
REPORT = BASE / "admin_import_100_report.json"

FIELDS = [
    "district", "name", "title", "email", "phone",
    "location", "source_url", "evidence",
    "extraction_method", "verified"
]

PRIORITY = {
    "superintendent": 100,
    "assistant superintendent": 95,
    "principal": 90,
    "assistant principal": 85,
    "business administrator": 90,
    "school business administrator": 90,
    "director": 80,
    "chief": 80,
    "head of school": 90,
    "deputy": 75,
    "administrator": 70,
    "president": 60,
    "coordinator": 55,
    "supervisor": 55,
}

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def normalize(value):
    return re.sub(r"[^a-z0-9]", "", clean(value).lower())

def title_score(title):
    t = clean(title).lower()
    score = 0
    for role, points in PRIORITY.items():
        if role in t:
            score = max(score, points)
    return score

def valid_name(name):
    n = clean(name)
    if len(n) < 4 or len(n) > 90:
        return False
    if "@" in n or "http" in n.lower():
        return False
    if re.search(r"\d", n):
        return False
    if n.lower() in {
        "administration", "staff directory", "school directory",
        "district office", "contact us", "our schools",
        "board of education", "not available"
    }:
        return False
    return len(n.split()) >= 2

def read_rows(path):
    if not path.exists():
        print(f"Skipping missing file: {path.name}")
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item = {field: clean(row.get(field, "")) for field in FIELDS}
            if valid_name(item["name"]) and item["district"]:
                rows.append(item)
    print(f"Read {len(rows)} usable rows from {path.name}")
    return rows

all_rows = []
for file in INPUTS:
    all_rows.extend(read_rows(file))

# Keep administrator-role records first; use other named leadership
# records as a fallback if the priority group has fewer than 100.
for row in all_rows:
    row["_score"] = title_score(row["title"])
    row["_score"] += 20 if row["email"] else 0
    row["_score"] += 10 if row["phone"] else 0
    row["_score"] += 5 if row["source_url"] else 0
    row["_score"] += 5 if row["verified"].lower() in ("true", "1", "yes") else 0

# Deduplicate by district + person, preferring the most complete record.
unique = {}
for row in all_rows:
    key = (normalize(row["district"]), normalize(row["name"]))
    if key not in unique or row["_score"] > unique[key]["_score"]:
        unique[key] = row

records = list(unique.values())
records.sort(key=lambda r: (
    r["_score"],
    bool(r["email"]),
    bool(r["phone"])
), reverse=True)

# First choose clear administrator roles.
priority_records = [r for r in records if r["_score"] >= 55]

# Fill to 100 with remaining named district leadership records if needed.
selected = priority_records[:100]
if len(selected) < 100:
    selected_keys = {
        (normalize(r["district"]), normalize(r["name"])) for r in selected
    }
    for row in records:
        key = (normalize(row["district"]), normalize(row["name"]))
        if key not in selected_keys:
            selected.append(row)
            selected_keys.add(key)
        if len(selected) >= 100:
            break

for row in selected:
    row.pop("_score", None)

with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(selected)

report = {
    "source_files": [str(p) for p in INPUTS if p.exists()],
    "total_source_rows": len(all_rows),
    "unique_people_per_district": len(records),
    "priority_admin_records_available": len(priority_records),
    "records_exported": len(selected),
    "records_with_email": sum(bool(r["email"]) for r in selected),
    "records_with_phone": sum(bool(r["phone"]) for r in selected),
    "records_with_both": sum(bool(r["email"]) and bool(r["phone"]) for r in selected),
    "records_with_source_url": sum(bool(r["source_url"]) for r in selected),
    "title_distribution": dict(Counter(r["title"] or "Missing title" for r in selected)),
    "note": "Ranked CSV for review and Supabase import. Contact details and titles have not been independently verified."
}

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("\n========== EXPORT COMPLETE ==========")
print(f"CSV: {OUTPUT}")
print(f"Report: {REPORT}")
print(f"Unique records found: {len(records)}")
print(f"Records exported: {len(selected)}")
print(f"With email: {report['records_with_email']}")
print(f"With phone: {report['records_with_phone']}")
print(f"With both: {report['records_with_both']}")
print("=====================================")

if len(selected) < 100:
    print("WARNING: Fewer than 100 unique named records were available in the input files.")
