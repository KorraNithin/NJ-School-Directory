
import pandas as pd
import re
from pathlib import Path

BASE = Path("data/extracted/new_jersey")

input_file = BASE / "admin_contacts_review.csv"
output_file = BASE / "admin_contacts_clean.csv"

df = pd.read_csv(input_file).fillna("")

# Remove trailing commas and extra spaces from names
df["name"] = df["name"].astype(str).str.strip().str.rstrip(",").str.strip()

# Correct titles using the actual evidence text
corrections = {
    "Mia Bivaletz": "Executive Assistant to the Superintendent",
    "Annika Gruters": "Principal's Secretary",
    "Fanny Lopez": "Assistant Director",
}

for name, title in corrections.items():
    df.loc[df["name"] == name, "title"] = title

# Remove category labels that are not people
invalid_names = {
    "Speciality Teachers",
    "Specialty Teachers",
}

df = df[~df["name"].isin(invalid_names)]

# Remove rows without a plausible first and last name
def valid_name(name):
    words = name.replace("Dr. ", "").split()
    return (
        len(words) >= 2
        and len(words) <= 4
        and all(re.search(r"[A-Za-z]", word) for word in words)
    )

df = df[df["name"].apply(valid_name)]

# Normalize names for duplicate detection
def normalize_name(name):
    return re.sub(r"[^a-z]", "", name.lower().replace("dr.", ""))

df["name_key"] = df["name"].apply(normalize_name)

# Prefer the record with the most useful evidence
df["evidence_length"] = df["evidence"].astype(str).str.len()
df = df.sort_values("evidence_length", ascending=False)

# Keep one record per district and person
df = df.drop_duplicates(
    subset=["district", "name_key"],
    keep="first"
)

df = df.drop(columns=["name_key", "evidence_length"])

# Keep records marked for manual verification
df["verified"] = "NO"

df.to_csv(output_file, index=False)

print("Cleaned records:", len(df))
print("\nRecords by district:")
print(df.groupby("district").size().to_string())

print("\nCleaned administrator list:")
print(df[["district", "name", "title"]].to_string(index=False))

print("\nSaved to:", output_file)
