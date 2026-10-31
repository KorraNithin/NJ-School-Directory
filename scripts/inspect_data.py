
from pathlib import Path
from zipfile import ZipFile
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUTPUT_DIR = BASE_DIR / "data" / "extracted"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

files = {
    "districts.zip": "ccd_lea_029_2526_w_0a_050626.csv",
    "schools.zip": "ccd_sch_029_2526_w_0a_050626.csv"
}

for zip_name, csv_name in files.items():
    zip_path = RAW_DIR / zip_name

    print(f"\nExtracting {zip_name}...")

    with ZipFile(zip_path, "r") as archive:
        with archive.open(csv_name) as source:
            output_path = OUTPUT_DIR / csv_name
            output_path.write_bytes(source.read())

    print(f"Saved: {output_path}")

    # Inspect the CSV
    df = pd.read_csv(output_path, dtype=str, nrows=5)

    print("\nColumns:")
    print(df.columns.tolist())

    print("\nSample records:")
    print(df.head().to_string(index=False))

print("\nExtraction and inspection completed!")
