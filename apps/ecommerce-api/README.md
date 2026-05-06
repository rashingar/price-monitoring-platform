# ecommerce-api

`ecommerce-api` is the ecommerce catalog and price monitoring backend for the
Price Monitoring Platform. It is a Python/FastAPI service that imports the
product catalog, prepares monitoring runs, fetches competitor prices from
supported marketplaces, stores price observations, exposes alert and review
data, and writes manual export artifacts for downstream commerce tools.

The app folder is `apps/ecommerce-api`. Its internal Python package is
`src/ecommerce`, and its local console scripts are `ecommerce` and
`ecommerce-api`.

The current repo is API-first. The root README intentionally stays focused on
what the repo is and how to run it. Endpoint details, request contracts, and
historical CLI/file-first notes live in separate docs:

- [API endpoints and contracts](docs/api.md)
- [Backend and persistence notes](docs/README.md)
- [Source capture notes](docs/source-capture.md)

## What This Service Does

Ecommerce provides a local backend for:

- importing `sourceCata.csv` into PostgreSQL as the active product catalog
- browsing catalog products, categories, brands, and known source URLs
- creating price monitoring selections and run folders
- launching supervised local fetch executions for Skroutz or BestPrice
- storing catalog snapshots, observations, alert rules, and alert events
- storing shared product source capture snapshots and Product Factory backfills
- reviewing fetched prices and exporting manual OpenCart price-update CSV files
- safely reading/writing approved local CSV files for browser UI workflows
- exposing generated artifacts through safe API download and preview endpoints

Generated run files are written under `output/` by default. Catalog and Price
Monitoring workflows require PostgreSQL. Health, bridge, safe file editing,
paths, and artifact routes can still be useful while the database is being set
up.

## Requirements

- Python 3.11 or newer
- Native Windows PostgreSQL for Catalog and Price Monitoring workflows
- Chromium installed through Playwright for live marketplace fetches
- PowerShell commands below assume Windows

Docker is not used by this project setup.

## Installation

From the repository root, create the root virtual environment and install the
locked Ecommerce API dependencies:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps
```

The `python` command must resolve to Python 3.11 or newer. If it is not found
or is too old, install a supported Python version and reopen PowerShell.

Install Chromium for Playwright:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

`pyproject.toml` is the source of direct dependencies. Refresh
`requirements-lock.txt` only when dependency versions intentionally change.

## Environment

The repo-root `.env.example` file is a template with safe local defaults and
placeholders. Copy it only for private local development:

```powershell
Copy-Item .env.example .env
```

Do not commit `.env` or any file containing real credentials.

Ecommerce loads `.env` automatically for local commands. If the same setting
exists in both `.env` and the real Windows/PowerShell environment, the
OS environment value wins over `.env`.

Important variables:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
$env:ECOMMERCE_SOURCE_CATA_PATH = "C:\path\to\sourceCata.csv"
$env:ECOMMERCE_PRICE_IGNORE_PATH = "C:\path\to\price_ignore.csv"
$env:ECOMMERCE_ARTIFACT_ROOTS = "D:\Ecommerce\output\ecommerce\monitoring\runs"
$env:ECOMMERCE_FILE_ROOTS = "C:\Users\user\Downloads;C:\Exports;output"
```

`ECOMMERCE_DATABASE_URL` is required before Catalog import, Catalog browsing,
Price Monitoring runs, observations, history, or alerts are ready.

## Native Windows PostgreSQL setup and first-run verification

Install PostgreSQL natively on Windows with the official PostgreSQL Windows
installer:

```text
https://www.postgresql.org/download/windows/
```

Keep port `5432` unless another local PostgreSQL instance already uses it.
Create a local role and database from `psql` as the `postgres` admin user:

```sql
CREATE USER ecommerce WITH PASSWORD 'ecommerce';
CREATE DATABASE ecommerce OWNER ecommerce;
GRANT ALL PRIVILEGES ON DATABASE ecommerce TO ecommerce;
```

For the current PowerShell terminal:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
```

To persist it for the current Windows user:

```powershell
[Environment]::SetEnvironmentVariable(
  "ECOMMERCE_DATABASE_URL",
  "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce",
  "User"
)
```

Open a new PowerShell terminal after persisting user environment variables.

Current PostgreSQL setup, backup, rename, and rebuild steps are maintained in
[Ecommerce PostgreSQL Local Setup](../../docs/runbooks/ecommerce-postgresql-local.md).

### Renaming an older local PostgreSQL database

If an older local PostgreSQL setup still uses the previous application
database and role names, stop the Ecommerce API before renaming. Close active
database sessions first, back up the database if the data matters, and run the
commands from a `postgres` admin PowerShell or `psql` session.

```sql
ALTER DATABASE <previous_database_name> RENAME TO ecommerce;
ALTER ROLE <previous_role_name> RENAME TO ecommerce;
ALTER ROLE ecommerce WITH PASSWORD 'ecommerce';
```

If the previous role or database does not exist, use the fresh setup above to
create `ecommerce` directly.

For backup commands, session cleanup, rename steps, and fresh setup details,
see [Ecommerce PostgreSQL Local Setup](../../docs/runbooks/ecommerce-postgresql-local.md).

Verify configuration, apply migrations, import the active catalog, and verify
again from the repository root:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.check_db_setup
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.check_db_setup
Pop-Location
```

You can also run migrations with `alembic upgrade head` from
`apps/ecommerce-api` when the virtual environment scripts are on `PATH`.

Expected ready state for Catalog and Price Monitoring:

- `configured=true`
- `reachable=true`
- `required_tables_present=true`
- `alembic_up_to_date=true`
- `ready_for_catalog=true`
- `active_catalog_count > 0`
- `ready_for_price_monitoring=true`

Tables exist but monitoring row counts are zero before first run. That is valid
after the catalog has been imported and before the first Price Monitoring run.

## Run The Backend

Start the local API from the repository root:

```powershell
.\scripts\dev\ecommerce-api.ps1
```

Or run the development entry point directly:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.dev.start
```

The default server URL is:

```text
http://127.0.0.1:8001
```

Useful local URLs:

- `http://127.0.0.1:8001/api/health`
- `http://127.0.0.1:8001/docs`
- `http://127.0.0.1:8001/api/price-monitoring/db/status`

If the default port is already used by another service, start on a free port:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.dev.start --port 8002
```

## First Useful Workflow

1. Install dependencies and Playwright Chromium.
2. Configure `ECOMMERCE_DATABASE_URL`.
3. Run `.\.venv\Scripts\python.exe -m alembic upgrade head` from
   `apps/ecommerce-api`.
4. Import the catalog with `.\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog`.
5. Start the backend with `.\scripts\dev\ecommerce-api.ps1`.
6. Check `GET /api/price-monitoring/db/status`.
7. Use the API or frontend to create a monitoring run, launch fetch, review
   results, and export a manual price update CSV.

## Source URL Agent Mode

Source URL Agent Mode is a local, supervised discovery pipeline for finding
public product URLs across marketplaces and direct vendors. It reads products
from a CSV or the DB-backed catalog, searches configured public pages with the
manufacturer + MPN query only, extracts page evidence, scores candidates
conservatively, and writes repeatable artifacts under
`output/ecommerce/source-url-agent/runs/{run_id}`.

Dry-run from CSV:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent run --input input/test-1.csv --source all --limit 20 --dry-run
```

Dry-run from the DB catalog:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent from-catalog --source all --missing-only --limit 20 --dry-run
```

Write only high-confidence matches to `source_urls`:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent run --input input/test-1.csv --source all --apply-high-confidence --limit 20
```

Review weak matches by editing:

```text
output/ecommerce/source-url-agent/runs/{run_id}/needs_review_source_urls.csv
```

Then apply the reviewed file:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent apply-review --review-file output/ecommerce/source-url-agent/runs/{run_id}/needs_review_source_urls_reviewed.csv --apply
```

Accepted reviewed URLs use `url_type = discovered` and `trust_level = manual`.
Automatic high-confidence writes use `trust_level = high_confidence` only when
the match method is `exact_mpn_and_brand` and confidence is greater than `0.90`.
All other discovered candidates are exported for review. Existing manual source
URLs are not overwritten by automatic discovery.

Analyze a completed run:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent analyze --run-id {run_id}
```

Move DB-backed candidate review to another machine:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent export-candidates --output output/ecommerce/source-url-agent/source_url_candidates_export.json
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent import-candidates --input output/ecommerce/source-url-agent/source_url_candidates_export.json --dry-run
.\.venv\Scripts\python.exe -m ecommerce.jobs.source_url_agent import-candidates --input output/ecommerce/source-url-agent/source_url_candidates_export.json --apply
```

The import matches candidates back to `catalog_products` by
`catalog_source + model`, so import the catalog on the target database before
applying the candidate export.

The analysis summarizes blocked sources, repeated not-found patterns, missing
identifier evidence, category mismatches, and generic rule suggestions. These
artifacts prepare DB-first monitoring by filling the existing `source_urls`
table without changing fetch behavior for products that still lack reviewed
URLs.

## Verification

For operator-requested broad app verification from the repository root:

```powershell
.\scripts\test\ecommerce-api.ps1
```

For targeted checks, run the specific pytest file or node that maps to the
change:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m pytest tests\path\to\relevant_test.py -q
Pop-Location
```

Run API contract checks only after intentional route/schema/snapshot changes:

```powershell
.\scripts\contracts\check.ps1
```

The canonical OpenAPI snapshot is
`docs/contracts/openapi.ecommerce.json`. Regenerate it only after an
intentional API contract change:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.export_openapi_snapshot
```

Review snapshot diffs before committing them.

## Troubleshooting

- `Database is not configured.` Set `ECOMMERCE_DATABASE_URL` in PowerShell
  or copy `.env.example` to `.env` for local development.
- `Database is configured but unreachable.` Confirm the native Windows
  PostgreSQL service is running and the host, port, role, password, and
  database name are correct.
- `Migrations have not been applied.` Run `alembic upgrade head` from the repo
  root after setting `ECOMMERCE_DATABASE_URL`.
- `PostgreSQL is required for Catalog.` Import the catalog after migrations
  with `.\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog`.
- `psql is not available on PATH.` Add the PostgreSQL `bin` directory to PATH
  or run setup from a terminal where the installer configured it.
- Environment changes persisted with `[Environment]::SetEnvironmentVariable`
  require a new terminal before PowerShell sees them.
