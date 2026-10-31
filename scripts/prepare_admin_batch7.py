import csv, re
from pathlib import Path

BASE = Path("data/extracted/new_jersey")
FIELDS = ["district","name","title","email","phone","location","source_url","evidence","extraction_method","verified"]

def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()

def norm(v):
    return re.sub(r"[^a-z0-9]", "", clean(v).lower())

def valid_name(n):
    n = clean(n)
    return (
        4 <= len(n) <= 90
        and "@" not in n
        and "http" not in n.lower()
        and not re.search(r"\d", n)
        and len(n.split()) >= 2
        and n.lower() not in {
            "administration", "staff directory", "school directory",
            "district office", "contact us", "our schools",
            "board of education", "not available"
        }
    )

# Exclude all six previously generated batches.
previous = set()
for i in range(1, 7):
    filename = "supabase_admin_import_100.csv" if i == 1 else f"supabase_admin_import_100_batch{i}.csv"
    path = BASE / filename
    if not path.exists():
        raise SystemExit(f"Previous batch missing: {filename}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            previous.add((norm(r["district"]), norm(r["name"])))

roles = [
    ("superintendent",100), ("assistant superintendent",95),
    ("principal",90), ("assistant principal",85),
    ("business administrator",90), ("director",80),
    ("chief",80), ("head of school",90), ("deputy",75),
    ("administrator",70), ("coordinator",55), ("supervisor",55)
]

unique = {}

sources = [
    "admin_fast_run_raw.csv",
    "NJ_School_Admin_Directory_FINAL.csv",
    "admin_candidates_all_districts_raw.csv"
]

for filename in sources:
    path = BASE / filename
    if not path.exists():
        continue

    with path.open(encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            r = {k: clean(raw.get(k, "")) for k in FIELDS}

            if not r["district"] or not valid_name(r["name"]):
                continue

            key = (norm(r["district"]), norm(r["name"]))
            if key in previous:
                continue

            title = r["title"].lower()
            score = max((p for role,p in roles if role in title), default=0)
            score += 20 if r["email"] else 0
            score += 10 if r["phone"] else 0
            score += 5 if r["source_url"] else 0

            if key not in unique or score > unique[key][1]:
                unique[key] = (r, score)

ranked = sorted(unique.values(), key=lambda x: x[1], reverse=True)

# Prefer administrator titles; use remaining candidates only if necessary.
selected = [r for r,s in ranked if s >= 55][:1000]

if len(selected) < 1000:
    selected_keys = {(norm(r["district"]), norm(r["name"])) for r in selected}
    for r,s in ranked:
        key = (norm(r["district"]), norm(r["name"]))
        if key not in selected_keys:
            selected.append(r)
            selected_keys.add(key)
        if len(selected) >= 1000:
            break

output = BASE / "supabase_admin_import_1000_batch7.csv"

with output.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(selected)

print("\n========== BATCH 7 ==========")
print("Records prepared:", len(selected))
print("With email:", sum(bool(r["email"]) for r in selected))
print("With phone:", sum(bool(r["phone"]) for r in selected))
print("Output:", output)
print("=============================")

if len(selected) < 1000:
    print("Only", len(selected), "additional unique candidates were available.")
