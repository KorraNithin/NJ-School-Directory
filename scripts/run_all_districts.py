"""
One-run New Jersey administrator directory builder.

Run from the project root:
    python scripts/run_all_districts.py

This discovers official district staff/leadership pages for all NJ districts,
extracts clearly paired person/title records, captures only strongly associated
contact details, merges existing candidate CSVs, and inserts missing records.
Automatically collected records remain unverified (verified_at = NULL).
"""
from __future__ import annotations

import os
import re
import time
import logging
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, urldefrag

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "extracted" / "new_jersey"
DISTRICTS_CSV = DATA / "nj_districts.csv"
PAGES_CSV = DATA / "admin_pages_discovered_all.csv"
CANDIDATES_CSV = DATA / "admin_candidates_all.csv"
FAILURES_CSV = DATA / "admin_discovery_failures.csv"
SUMMARY_CSV = DATA / "admin_run_summary.csv"

MAX_PAGES_PER_DISTRICT = 15
CRAWL_DEPTH = 2
WORKERS = 10
REQUEST_TIMEOUT = 18
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NJSchoolDirectoryResearch/1.0; public-directory-indexer)"
}
KEYWORDS = (
    "administration", "administrator", "leadership", "staff directory",
    "faculty directory", "our team", "superintendent", "principal",
    "school directory", "contact directory", "directory", "staff",
    "board office", "central office", "district office", "who we are",
)
ROLES = (
    "assistant superintendent", "deputy superintendent",
    "superintendent", "school business administrator",
    "business administrator", "chief operating officer",
    "chief of operations", "executive director", "clinical director",
    "assistant principal", "vice principal", "principal",
    "head of school", "director of special services",
    "director of curriculum", "director of student services",
    "director of technology", "director",
)
ROLE_RE = re.compile("|".join(re.escape(x) for x in sorted(ROLES, key=len, reverse=True)), re.I)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}")
NAME_RE = re.compile(
    r"^(?:Dr\.?\s+|Mr\.?\s+|Mrs\.?\s+|Ms\.?\s+)?"
    r"[A-Z][A-Za-z'’.-]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][A-Za-z'’.-]+){1,2}$"
)
STOP_NAMES = {
    "staff directory", "school district", "board education",
    "superintendent office", "central office", "district administration",
    "our leadership", "administrative team", "contact information",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
session = requests.Session()
session.headers.update(HEADERS)

def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

def clean_url(url):
    if not url:
        return ""
    url = str(url).strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")

def fetch(url):
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "").lower()
        if "html" not in ctype and not r.text.lstrip().startswith(("<!DOCTYPE", "<html")):
            return None, r.url
        return BeautifulSoup(r.text, "html.parser"), r.url
    except Exception as exc:
        return None, str(exc)

def allowed_link(href, current_domain):
    p = urlparse(href)
    if p.scheme not in ("http", "https") or p.netloc.lower() != current_domain:
        return False
    if p.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".gif", ".doc", ".docx", ".xlsx", ".zip")):
        return False
    if any(x in href.lower() for x in ("mailto:", "javascript:", "calendar", "facebook", "instagram", "youtube")):
        return False
    return True

def discover_one(d):
    district = str(d.get("LEA_NAME", "")).strip()
    homepage = clean_url(d.get("WEBSITE", ""))
    if not homepage:
        return [], [(district, "", "No district website in NCES data")]
    soup, landed = fetch(homepage)
    if soup is None:
        return [], [(district, homepage, f"Homepage unavailable: {landed}")]
    domain = urlparse(landed).netloc.lower()
    queue = deque([(landed, 0)])
    visited = set()
    found = []
    errors = []
    while queue and len(visited) < MAX_PAGES_PER_DISTRICT:
        url, depth = queue.popleft()
        url = urldefrag(url)[0]
        if url in visited:
            continue
        visited.add(url)
        page_soup, final_url = fetch(url)
        if page_soup is None:
            errors.append((district, url, f"Page unavailable: {final_url}"))
            continue
        text = page_soup.get_text(" ", strip=True).lower()
        link_label = "Homepage" if depth == 0 else ""
        if depth == 0 or any(k in text for k in KEYWORDS):
            found.append({
                "district": district, "district_website": homepage,
                "page_url": final_url, "link_text": link_label or "Keyword page",
                "status": "homepage_candidate" if depth == 0 else "discovered"
            })
        if depth >= CRAWL_DEPTH:
            continue
        for a in page_soup.find_all("a", href=True):
            href = urljoin(final_url, a["href"])
            label = a.get_text(" ", strip=True)
            combined = (label + " " + href).lower()
            if not any(k in combined for k in KEYWORDS):
                continue
            if allowed_link(href, domain):
                queue.append((href, depth + 1))
    # Keep only pages likely to hold staff/admin information; homepage stays for navigation.
    dedup = {}
    for p in found:
        dedup[(district, p["page_url"])] = p
    return list(dedup.values()), errors

def valid_name(line):
    line = re.sub(r"\s+", " ", str(line)).strip(" ,:;|")
    if not NAME_RE.fullmatch(line):
        return False
    if norm(line) in {norm(x) for x in STOP_NAMES}:
        return False
    parts = re.findall(r"[A-Za-z]+", line)
    return 2 <= len(parts) <= 4 and not any(x.lower() in {
        "school", "district", "office", "staff", "principal", "director",
        "superintendent", "administration", "leadership", "contact"
    } for x in parts)

def name_from_lines(lines):
    clean = [re.sub(r"\s+", " ", x).strip(" ,:;|") for x in lines if x.strip()]
    # Common directory format: name on one line, title on another.
    for i, line in enumerate(clean):
        if valid_name(line):
            nearby = " ".join(clean[max(0, i-1):min(len(clean), i+3)])
            m = ROLE_RE.search(nearby)
            if m:
                return line, m.group(0).title()
    # Common format: "Jane Smith - Superintendent".
    for line in clean:
        m = ROLE_RE.search(line)
        if m:
            before = line[:m.start()].strip(" -|,:")
            after = line[m.end():].strip(" -|,:")
            for candidate in (before, after):
                if valid_name(candidate):
                    return candidate, m.group(0).title()
    return "", ""

def extract_page(page):
    district, url = page["district"], page["page_url"]
    soup, landed = fetch(url)
    if soup is None:
        return []
    for el in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        el.decompose()
    blocks = soup.find_all(["article", "tr", "li", "h2", "h3", "h4", "p"])
    blocks += soup.select('[class*="staff"],[class*="person"],[class*="profile"],[class*="member"],[class*="employee"],[class*="directory"]')
    results, seen = [], set()
    for block in blocks:
        txt = block.get_text(" ", strip=True)
        if not txt or len(txt) > 1000:
            continue
        lines = [x.strip() for x in block.get_text("\n", strip=True).splitlines() if x.strip()]
        name, title = name_from_lines(lines)
        if not name or not title:
            continue
        k = (norm(district), norm(name), norm(title))
        if k in seen:
            continue
        seen.add(k)
        # Only bind email if local-part contains a meaningful name token and only one email occurs in the card.
        emails = list(dict.fromkeys(EMAIL_RE.findall(txt)))
        email = ""
        name_tokens = [x.lower() for x in re.findall(r"[A-Za-z]+", name) if len(x) > 2 and x.lower() not in {"dr", "mr", "mrs", "ms"}]
        if len(emails) == 1:
            local = re.split(r"[._+-]", emails[0].split("@")[0].lower())
            if any(t in local for t in name_tokens):
                email = emails[0]
        phone = ""
        for a in block.find_all("a", href=True):
            if a["href"].lower().startswith("tel:"):
                match = PHONE_RE.search(a["href"][4:] + " " + a.get_text(" ", strip=True))
                if match:
                    phone = match.group(0)
                    break
        results.append({
            "district": district, "name": name, "title": title,
            "email": email, "phone": phone, "source_url": landed,
            "evidence": txt[:600], "verified": "NO",
            "email_type": "Individual-looking email - verify" if email else "Not found",
            "phone_type": "Phone - verify" if phone else "Not found",
        })
    return results

def load_existing_candidates():
    frames = []
    for filename in ("admin_contacts_final_review.csv", "admin_contacts_clean.csv"):
        path = DATA / filename
        if path.exists():
            try:
                df = pd.read_csv(path, dtype=str).fillna("")
                if {"district", "name", "title"}.issubset(df.columns):
                    for col in ("email", "phone", "source_url", "evidence", "email_type", "phone_type", "profile_source_url"):
                        if col not in df.columns:
                            df[col] = ""
                    df["verified"] = "NO"
                    frames.append(df)
            except Exception as exc:
                logging.warning("Could not read %s: %s", filename, exc)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True).fillna("")
    merged["key"] = merged.apply(lambda r: norm(r["district"]) + "|" + norm(r["name"]), axis=1)
    merged = merged.sort_values(
        by=["email", "phone", "evidence"],
        key=lambda s: s.astype(str).str.len(),
        ascending=False
    ).drop_duplicates("key", keep="first")
    return merged.drop(columns=["key"])

def fetch_all(table, select):
    rows, offset, page_size = [], 0, 1000
    while True:
        r = session.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=SB_HEADERS,
            params={"select": select, "limit": page_size, "offset": offset},
            timeout=30
        )
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows

def main():
    if not DISTRICTS_CSV.exists():
        raise FileNotFoundError(f"Missing {DISTRICTS_CSV}")
    districts = pd.read_csv(DISTRICTS_CSV, dtype=str).fillna("")
    logging.info("Starting discovery for %d districts", len(districts))
    all_pages, failures = [], []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(discover_one, row.to_dict()) for _, row in districts.iterrows()]
        for fut in as_completed(futures):
            try:
                pages, errs = fut.result()
                all_pages.extend(pages)
                failures.extend(errs)
            except Exception as exc:
                failures.append(("", "", f"Unexpected discovery error: {exc}"))
    pages_df = pd.DataFrame(all_pages, columns=["district","district_website","page_url","link_text","status"])
    if not pages_df.empty:
        pages_df = pages_df.drop_duplicates(["district","page_url"])
        pages_df.to_csv(PAGES_CSV, index=False)
    pd.DataFrame(failures, columns=["district","url","error"]).to_csv(FAILURES_CSV, index=False)
    logging.info("Discovery complete: %d/%d districts processed; %d pages; %d fetch errors",
                 len(districts), len(districts), len(pages_df), len(failures))

    extracted = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(extract_page, row.to_dict()) for _, row in pages_df.iterrows()]
        for fut in as_completed(futures):
            try:
                extracted.extend(fut.result())
            except Exception as exc:
                logging.warning("Page extraction failed: %s", exc)
    auto_df = pd.DataFrame(extracted)
    existing_df = load_existing_candidates()
    if not existing_df.empty:
        combined = pd.concat([existing_df, auto_df], ignore_index=True).fillna("")
    else:
        combined = auto_df
    if combined.empty:
        combined = pd.DataFrame(columns=[
            "district","name","title","email","phone","source_url","evidence","verified","email_type","phone_type"
        ])
    combined["key"] = combined.apply(lambda r: norm(r.get("district","")) + "|" + norm(r.get("name","")), axis=1)
    combined = combined.sort_values(
        by=["email","phone","evidence"],
        key=lambda s: s.astype(str).str.len(),
        ascending=False
    ).drop_duplicates("key", keep="first").drop(columns=["key"])
    combined["verified"] = "NO"
    combined.to_csv(CANDIDATES_CSV, index=False)

    logging.info("Candidates ready: %d; with email: %d; with phone: %d",
                 len(combined), (combined["email"].astype(str).str.strip() != "").sum(),
                 (combined["phone"].astype(str).str.strip() != "").sum())

    load_dotenv(ROOT / "backend" / ".env")
    global SUPABASE_URL, SB_HEADERS
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not SUPABASE_URL or not key:
        raise RuntimeError("Supabase credentials missing from backend/.env; no database changes made.")
    SB_HEADERS = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json", "Prefer": "return=minimal"
    }
    district_rows = fetch_all("districts", "id,name")
    admin_rows = fetch_all("administrators", "id,name,district_id,email,phone")
    district_map = {norm(x["name"]): x["id"] for x in district_rows}
    existing = {(x["district_id"], norm(x["name"])): x for x in admin_rows}
    inserted = updated = skipped = unmatched = 0
    errors = []
    for _, row in combined.iterrows():
        district_id = district_map.get(norm(row.get("district", "")))
        if not district_id:
            unmatched += 1
            continue
        key_tuple = (district_id, norm(row.get("name", "")))
        old = existing.get(key_tuple)
        email = str(row.get("email", "")).strip()
        phone = str(row.get("phone", "")).strip()
        if old:
            patch = {}
            # Fill only empty database fields; never overwrite existing values.
            if email and not old.get("email"):
                patch["email"] = email
                patch["email_type"] = row.get("email_type") or "Individual-looking email - verify"
            if phone and not old.get("phone"):
                patch["phone"] = phone
                patch["phone_type"] = row.get("phone_type") or "Phone - verify"
            if patch:
                r = session.patch(
                    f"{SUPABASE_URL}/rest/v1/administrators",
                    headers=SB_HEADERS,
                    params={"id": f"eq.{old['id']}"},
                    json=patch, timeout=30
                )
                if r.ok:
                    updated += 1
                    old.update(patch)
                else:
                    errors.append(f"Update {row.get('name')}: {r.status_code} {r.text[:250]}")
            else:
                skipped += 1
            continue
        payload = {
            "district_id": district_id, "school_id": None,
            "name": str(row.get("name", "")).strip(),
            "title": str(row.get("title", "")).strip(),
            "email": email or None, "phone": phone or None,
            "source_url": str(row.get("profile_source_url") or row.get("source_url") or "").strip() or None,
            "verified_at": None,
            "email_type": str(row.get("email_type") or ("Individual-looking email - verify" if email else "Not found")),
            "phone_type": str(row.get("phone_type") or ("Phone - verify" if phone else "Not found")),
        }
        if not payload["name"] or not payload["title"]:
            skipped += 1
            continue
        r = session.post(
            f"{SUPABASE_URL}/rest/v1/administrators",
            headers=SB_HEADERS, json=payload, timeout=30
        )
        if r.ok:
            inserted += 1
            existing[key_tuple] = {"id": None, **payload}
        else:
            errors.append(f"Insert {row.get('name')}: {r.status_code} {r.text[:250]}")
    pd.DataFrame([{
        "districts_in_nces": len(districts),
        "districts_with_website": int((districts["WEBSITE"].astype(str).str.strip() != "").sum()),
        "pages_discovered": len(pages_df),
        "candidate_records": len(combined),
        "inserted": inserted, "updated_empty_contacts": updated,
        "already_present_or_no_new_contact": skipped,
        "district_unmatched": unmatched, "database_errors": len(errors),
        "fetch_errors": len(failures),
    }]).to_csv(SUMMARY_CSV, index=False)
    logging.info("FINISHED: inserted=%d updated=%d skipped=%d unmatched=%d db_errors=%d",
                 inserted, updated, skipped, unmatched, len(errors))
    if errors:
        error_path = DATA / "admin_database_errors.txt"
        error_path.write_text("\n".join(errors), encoding="utf-8")
        logging.warning("Database errors saved to %s", error_path)
    logging.info("Summary saved to %s", SUMMARY_CSV)

if __name__ == "__main__":
    main()
