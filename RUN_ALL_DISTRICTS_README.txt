# One-run NJ administrator collection

## Run once
1. Extract this project into your existing `nj-school-directory` folder (merge/overwrite when Windows asks).
2. Make sure `backend/.env` contains `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Never put this key in the frontend or commit it to Git.
3. Open PowerShell in the project root (`nj-school-directory`).
4. Install the Python packages:
   `py -m pip install -r requirements_nj_directory.txt`
5. Run the complete collection:
   `py scripts/run_all_districts.py`

The script:
- processes all 698 NJ districts in `data/extracted/new_jersey/nj_districts.csv`;
- checks official district websites and up to 15 relevant same-domain pages per district;
- extracts a name/title only when it can pair them in a compact page block;
- only associates an email when the email local-part contains a name token; only takes a phone from a `tel:` link in the same block;
- merges the previous candidate CSVs;
- inserts missing administrator rows and fills only empty email/phone fields on existing rows;
- never overwrites existing contact details and leaves `verified_at` NULL for newly inserted records.

## Output files
- `data/extracted/new_jersey/admin_pages_discovered_all.csv`
- `data/extracted/new_jersey/admin_candidates_all.csv`
- `data/extracted/new_jersey/admin_discovery_failures.csv`
- `data/extracted/new_jersey/admin_run_summary.csv`
- `data/extracted/new_jersey/admin_database_errors.txt` (only if database writes fail)

## Important limitation
This is a best-effort automated public-web collection, not a guarantee that every district publishes an administrator directory or that every site is scrapeable. JavaScript-only directories, PDFs, blocked sites, and pages with unusual layouts may be missed. No names or contact details are invented. Review the final CSVs and source URLs after the run.

The run may take a while because it makes requests across hundreds of district websites. Keep the terminal open until it prints `FINISHED`.
