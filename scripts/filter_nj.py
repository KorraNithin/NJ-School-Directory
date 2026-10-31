
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "extracted"
OUTPUT_DIR = DATA_DIR / "new_jersey"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_and_filter(filename, state_column="ST"):
    path = DATA_DIR / filename

    print(f"\nReading {filename}...")

    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False
    )

    # Filter only New Jersey
    df = df[df[state_column].str.strip().str.upper() == "NJ"].copy()

    print(f"New Jersey records found: {len(df)}")

    return df


# Load district records
districts = load_and_filter(
    "ccd_lea_029_2526_w_0a_050626.csv"
)

# Load school records
schools = load_and_filter(
    "ccd_sch_029_2526_w_0a_050626.csv"
)

# Select useful district columns
district_columns = [
    "SCHOOL_YEAR", "FIPST", "ST", "LEAID",
    "LEA_NAME", "MSTREET1", "MCITY",
    "MSTATE", "MZIP", "PHONE", "WEBSITE",
    "SY_STATUS_TEXT", "LEA_TYPE_TEXT"
]

# Select useful school columns
school_columns = [
    "SCHOOL_YEAR", "FIPST", "ST", "NCESSCH",
    "SCH_NAME", "LEAID", "LEA_NAME",
    "MSTREET1", "MCITY", "MSTATE", "MZIP",
    "PHONE", "WEBSITE", "SY_STATUS_TEXT",
    "SCH_TYPE_TEXT"
]

districts = districts[district_columns]
schools = schools[school_columns]

# Save filtered datasets
districts.to_csv(
    OUTPUT_DIR / "nj_districts.csv",
    index=False
)

schools.to_csv(
    OUTPUT_DIR / "nj_schools.csv",
    index=False
)

# Validate school-district relationships
district_ids = set(districts["LEAID"])

schools["DISTRICT_MATCH"] = schools["LEAID"].isin(district_ids)

print("\n========== VALIDATION ==========")
print("Total NJ districts:", len(districts))
print("Total NJ schools:", len(schools))
print("Schools with matching districts:",
      schools["DISTRICT_MATCH"].sum())
print("Schools without matching districts:",
      (~schools["DISTRICT_MATCH"]).sum())

print("\nSample districts:")
print(districts[["LEAID", "LEA_NAME"]].head(10).to_string(index=False))

print("\nSample schools:")
print(schools[["NCESSCH", "SCH_NAME", "LEA_NAME"]].head(10).to_string(index=False))

print("\nNew Jersey filtering completed!")
print("Output directory:", OUTPUT_DIR)
