
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

FILE = DATA_DIR / "admin_candidates_clean.csv"

df = pd.read_csv(FILE, dtype=str, keep_default_na=False)

# These are the candidates we have reviewed.
# Confirm each one against its official source page.
df["verified"] = ""

print("\nMANUAL VERIFICATION")
print("=" * 65)

for index, row in df.iterrows():
    print(f"\n{index + 1}. {row['name']}")
    print("Title:", row["title"])
    print("District:", row["district"])
    print("Official source:", row["source_url"])
    print("Open the source and confirm the name and title.")

df.to_csv(FILE, index=False)

print("\nVerification column added to CSV.")
print("Open admin_candidates_clean.csv in Excel.")
print("Enter YES in the verified column only for confirmed records.")
