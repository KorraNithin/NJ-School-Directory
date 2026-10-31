
import pandas as pd
import re
from pathlib import Path

folder = Path("data/extracted/new_jersey")
input_file = folder / "admin_candidates_all_districts_raw.csv"

df = pd.read_csv(input_file, dtype=str).fillna("")

# Remove whitespace
for col in df.columns:
    df[col] = df[col].astype(str).str.strip()

def norm(value):
    return re.sub(r"\s+", " ", str(value).lower().strip())

# Keep records with a name
df = df[df["name"].str.strip() != ""].copy()

# Group repeated entries by district and name.
# Retain the most complete record and fill missing fields from duplicates.
df["_key"] = (
    df["district"].map(norm) + "|" + df["name"].map(norm)
)

columns = [c for c in df.columns if c != "_key"]

def merge_records(group):
    group = group.copy()
    group["_completeness"] = (
        group[columns].ne("").sum(axis=1)
    )
    group = group.sort_values("_completeness", ascending=False)
    best = group.iloc[0].copy()

    for col in columns:
        if best[col] == "":
            values = group.loc[group[col] != "", col]
            if not values.empty:
                best[col] = values.iloc[0]

    return best[columns]

clean = (
    df.groupby("_key", sort=False, group_keys=False)
      .apply(merge_records)
      .reset_index(drop=True)
)

# Save final outputs
csv_path = folder / "NJ_School_Admin_Directory_FINAL.csv"
excel_path = folder / "NJ_School_Admin_Directory_FINAL.xlsx"

clean.to_csv(csv_path, index=False)
clean.to_excel(excel_path, index=False)

print("===== FINAL DATASET =====")
print("Original rows:", len(df))
print("Clean rows:", len(clean))
print("Unique districts:", clean["district"].nunique())
print("Names:", clean["name"].ne("").sum())

for col in ["title", "email", "phone"]:
    if col in clean.columns:
        print(f"{col} available:", clean[col].ne("").sum())

print("\nSaved:")
print(csv_path)
print(excel_path)
