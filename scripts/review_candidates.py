
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

FILE = (
    BASE_DIR
    / "data"
    / "extracted"
    / "new_jersey"
    / "admin_candidates_review.csv"
)

df = pd.read_csv(FILE, dtype=str, keep_default_na=False)

print("\nTOTAL CANDIDATES:", len(df))

for index, row in df.iterrows():
    print("\n-----------------------------------")
    print("Record:", index + 1)
    print("District:", row["district"])
    print("Name:", row["name"])
    print("Title:", row["title"])
    print("Source:", row["source_url"])
