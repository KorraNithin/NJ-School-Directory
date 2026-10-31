
import pandas as pd
from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

INPUT_FILE = DATA_DIR / "admin_candidates_review.csv"
OUTPUT_FILE = DATA_DIR / "admin_candidates_clean.csv"

df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=False)

# Remove policy pages and other unsuitable sources
df = df[
    ~df["source_url"].str.contains(
        r"board-policies|policies|regulations",
        case=False,
        regex=True
    )
].copy()

def clean_name(name):
    name = str(name).strip()

    # Remove date prefixes such as "July, 2024 -"
    name = re.sub(
        r"^[A-Za-z]+,?\s+\d{4}\s*[-–]\s*",
        "",
        name
    )

    # Remove incomplete sentence endings
    name = re.sub(r"\s+is the$", "", name, flags=re.I)
    name = re.sub(r",?\s+our$", "", name, flags=re.I)

    return name.strip(" ,.-")

invalid_names = [
    "high school",
    "elementary/middle school",
    "evaluation of",
    "incapacity of",
    "employment of school",
    "duties of the school",
    "executive assistant to the"
]

cleaned = []

for _, row in df.iterrows():
    name = clean_name(row["name"])

    if name.lower() in invalid_names:
        continue

    # Names should contain 2 to 5 words
    parts = name.split()

    if len(parts) < 2 or len(parts) > 5:
        continue

    # Reject phrases containing obvious non-name words
    if re.search(
        r"\b(the|our|school|evaluation|employment|duties|incapacity)\b",
        name,
        re.I
    ):
        continue

    # Reject names containing digits or unusual characters
    if not re.fullmatch(r"[A-Za-zÀ-ÿ.' -]+", name):
        continue

    row["name"] = name
    row["review_status"] = "Needs manual verification"
    cleaned.append(row)

result = pd.DataFrame(cleaned)

if not result.empty:
    result = result.drop_duplicates(
        subset=["district", "name", "title"]
    )

    result.to_csv(OUTPUT_FILE, index=False)

print("\n========== CLEANING SUMMARY ==========")
print("Original candidates:", len(pd.read_csv(INPUT_FILE)))
print("Clean candidates:", len(result))
print("Removed candidates:", len(pd.read_csv(INPUT_FILE)) - len(result))
print("Output:", OUTPUT_FILE)

print("\nCLEANED RECORDS:")

for _, row in result.iterrows():
    print(f'{row["name"]} | {row["title"]} | {row["district"]}')
