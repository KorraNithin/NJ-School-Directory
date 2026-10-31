
import pandas as pd
from pathlib import Path

BASE = Path("data/extracted/new_jersey")

INPUT = BASE / "admin_profile_contacts_review.csv"
OUTPUT = BASE / "admin_contacts_final_review.csv"

df = pd.read_csv(INPUT, dtype=str).fillna("")

generic_emails = {
    "webadmin@shsd.org",
    "office@ecsnj.org"
}

shared_phones = {
    "2017954400",
    "2015699765",
    "2014332288",
    "2013930475"
}

def normalize_phone(value):
    return "".join(ch for ch in str(value) if ch.isdigit())

def classify_email(email):
    if not email.strip():
        return "Not found"
    if email.lower().strip() in generic_emails:
        return "General organization email"
    return "Individual-looking email - verify"

def classify_phone(phone):
    if not phone.strip():
        return "Not found"
    if normalize_phone(phone) in shared_phones:
        return "Shared office phone"
    return "Phone - verify"

df["email_type"] = df["email"].apply(classify_email)
df["phone_type"] = df["phone"].apply(classify_phone)

df.to_csv(OUTPUT, index=False)

print("Classification complete.")
print("Total records:", len(df))
print("\nEmail classification:")
print(df["email_type"].value_counts().to_string())
print("\nPhone classification:")
print(df["phone_type"].value_counts().to_string())
print("\nSaved:", OUTPUT)
