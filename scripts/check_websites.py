import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted" / "new_jersey"

districts = pd.read_csv(
    DATA_DIR / "nj_districts.csv",
    dtype=str,
    keep_default_na=False
)

schools = pd.read_csv(
    DATA_DIR / "nj_schools.csv",
    dtype=str,
    keep_default_na=False
)

def check_data(name, df):
    websites = df["WEBSITE"].str.strip()

    available = websites.ne("") & websites.ne("-")

    print(f"\n{name}")
    print("-" * 35)
    print("Total records:", len(df))
    print("Records with websites:", available.sum())
    print("Records without websites:", (~available).sum())
    print("\nSample websites:")

    print(
        df.loc[available, ["LEA_NAME", "WEBSITE"]]
        .head(10)
        .to_string(index=False)
    )

check_data("DISTRICTS", districts)
check_data("SCHOOLS", schools)