# Process: Add i18n Translation Fields to blogs Table

## Overview
Add French, Spanish, and Korean translations for `title`, `description`, and `content` to the `blogs` table, then populate them using Google Translate.

---

## Step 1 — Add columns to the schema

Run the migration script to add the nine new nullable columns:

**File:** `db_script/0002_add_i18n_fields.sql`

```sql
ALTER TABLE blogs ADD COLUMN title_fr       TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN title_es       TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN title_ko       TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN description_fr TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN description_es TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN description_ko TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN content_fr     TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN content_es     TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN content_ko     TEXT NOT NULL DEFAULT '';
```

Execute against the target database:

```bash
# dev
npx -y wrangler d1 execute thrj-blogs-dev --remote --file db_script/0002_add_i18n_fields.sql

# production
npx -y wrangler d1 execute thrj-blogs --remote --file db_script/0002_add_i18n_fields.sql
```

> **Verify** columns were added:
> ```bash
> npx -y wrangler d1 execute <db-name> --remote --command "PRAGMA table_info(blogs);"
> ```

---

## Step 2 — Install the translation dependency

The script uses `deep-translator` (wraps Google Translate, no API key needed).

```bash
pip install deep-translator
# or, if using the project venv:
.venv-workers/Scripts/pip install deep-translator
```

---

## Step 3 — Run the translation script

**File:** `scripts/translate_blogs.py`

```bash
# From the project root, with the venv active:
python scripts/translate_blogs.py
```

What the script does:

1. Reads `id`, `title`, `description`, and `content` from `blogs` via `wrangler d1 execute --remote --json`.
2. Translates each field to French (`fr`), Spanish (`es`), and Korean (`ko`) using `GoogleTranslator`.
   - Short fields (≤ 4900 chars) are translated in a single call.
   - Long HTML content fields are split on HTML block-close tags (`</p>`, `</li>`, `</h2>`, etc.) and hard-capped at 4900 chars per chunk, then translated chunk-by-chunk and reassembled.
3. Builds `UPDATE` statements for all rows.
4. Saves the generated SQL to `db_script/0004_i18n_content_data.sql` for review/audit.
5. Executes the SQL file against the remote D1 database.

---

## Step 4 — Apply to a different database

To target a different database (e.g. `thrj-blogs` for production):

1. Open `scripts/translate_blogs.py` and change the `DB_NAME` constant at the top:

   ```python
   DB_NAME = "thrj-blogs"   # was "thrj-blogs-dev"
   ```

2. Update the SQL output path if you want a separate audit file:

   ```python
   SQL_OUTPUT = WRANGLER_ROOT / "db_script" / "0003_i18n_data_prod.sql"
   ```

3. Re-run the script:

   ```bash
   python scripts/translate_blogs.py
   ```

---

## Artefacts produced

| File | Purpose |
|------|---------|
| `db_script/0002_add_i18n_fields.sql` | DDL — adds the six locale columns |
| `db_script/0003_i18n_data.sql` | DML — UPDATE statements for title + description (dev run) |
| `db_script/0004_i18n_content_data.sql` | DML — UPDATE statements for all nine fields incl. content (dev run) |
| `scripts/translate_blogs.py` | Reusable translation + update script |

---

## Notes

- The script retries each translation up to 3 times with back-off on transient errors.
- Single quotes in translated text are escaped (`''`) before insertion.
- Long HTML content is automatically split into ≤ 4900-char chunks on HTML tag boundaries (Google Translate's free endpoint enforces a 5000-char limit); chunks are translated individually and reassembled.
- `wrangler` wraps the file execution in an atomic import; the DB is rolled back automatically if the upload fails mid-flight.
- The `deep-translator` package uses the free Google Translate endpoint — no API key is required, but very large tables may hit rate limits. Add a `time.sleep` between rows if needed.
