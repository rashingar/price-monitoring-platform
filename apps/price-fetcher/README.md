# PriceFetcher

PriceFetcher is the local backend for the Price Monitoring Platform. It is a
Python/FastAPI service that imports the product catalog, prepares monitoring
runs, fetches competitor prices from supported marketplaces, stores price
observations, exposes alert and review data, and writes manual export artifacts
for downstream commerce tools.

The current repo is API-first. The root README intentionally stays focused on
what the repo is and how to run it. Endpoint details, request contracts, and
historical CLI/file-first notes live in separate docs:

- [API endpoints and contracts](docs/api.md)
- [Backend and persistence notes](docs/README.md)
- [Source capture notes](docs/source-capture.md)
- [Legacy CLI and historical behavior](docs/legacy.md)

## What This Service Does

PriceFetcher provides a local backend for:

- importing `sourceCata.csv` into PostgreSQL as the active product catalog
- browsing catalog products, categories, brands, and known source URLs
- creating price monitoring selections and run folders
- launching supervised local fetch executions for Skroutz or BestPrice
- storing catalog snapshots, observations, alert rules, and alert events
- storing shared product source capture snapshots and Product-Agent backfills
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

Create a virtual environment and install the locked dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

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

PriceFetcher loads `.env` automatically for local commands. If the same setting
exists in both `.env` and the real Windows/PowerShell environment, the
OS environment value wins over `.env`.

Important variables:

```powershell
$env:PRICEFETCHER_DATABASE_URL = "postgresql+psycopg://pricefetcher:pricefetcher@127.0.0.1:5432/pricefetcher"
$env:PRICEFETCHER_SOURCE_CATA_PATH = "C:\path\to\sourceCata.csv"
$env:PRICEFETCHER_PRICE_IGNORE_PATH = "C:\path\to\price_ignore.csv"
$env:PRICEFETCHER_ARTIFACT_ROOTS = "D:\PriceFetcher\price_monitoring\runs"
$env:PRICEFETCHER_FILE_ROOTS = "C:\Users\user\Downloads;C:\Exports;output"
```

`PRICEFETCHER_DATABASE_URL` is required before Catalog import, Catalog browsing,
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
CREATE USER pricefetcher WITH PASSWORD 'pricefetcher';
CREATE DATABASE pricefetcher OWNER pricefetcher;
GRANT ALL PRIVILEGES ON DATABASE pricefetcher TO pricefetcher;
```

For the current PowerShell terminal:

```powershell
$env:PRICEFETCHER_DATABASE_URL = "postgresql+psycopg://pricefetcher:pricefetcher@127.0.0.1:5432/pricefetcher"
```

To persist it for the current Windows user:

```powershell
[Environment]::SetEnvironmentVariable(
  "PRICEFETCHER_DATABASE_URL",
  "postgresql+psycopg://pricefetcher:pricefetcher@127.0.0.1:5432/pricefetcher",
  "User"
)
```

Open a new PowerShell terminal after persisting user environment variables.

This repo also includes a helper script for local Windows setup:

```powershell
.\scripts\setup_postgres_windows.ps1 -PersistUserEnv
```

The script creates or reuses the local role/database, prints only a sanitized
connection URL, and can optionally write a local `.env` with `-WriteDotEnv`.

Verify configuration, apply migrations, import the active catalog, and verify
again:

```powershell
python -m pricefetcher.jobs.check_db_setup
.\.venv\Scripts\python.exe -m alembic upgrade head
python -m pricefetcher.jobs.ingest_catalog
python -m pricefetcher.jobs.check_db_setup
```

You can also run migrations with `alembic upgrade head` when the virtual
environment scripts are on `PATH`.

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

Start the local API:

```powershell
pricefetcher-api
```

Or run the development entry point directly:

```powershell
python -m pricefetcher.dev.start
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
python -m pricefetcher.dev.start --port 8002
```

## First Useful Workflow

1. Install dependencies and Playwright Chromium.
2. Configure `PRICEFETCHER_DATABASE_URL`.
3. Run `alembic upgrade head`.
4. Import the catalog with `python -m pricefetcher.jobs.ingest_catalog`.
5. Start the backend with `pricefetcher-api`.
6. Check `GET /api/price-monitoring/db/status`.
7. Use the API or frontend to create a monitoring run, launch fetch, review
   results, and export a manual price update CSV.

## Source URL Agent Mode

Source URL Agent Mode is a local, supervised discovery pipeline for finding
public product URLs across marketplaces and direct vendors. It reads products
from a CSV or the DB-backed catalog, searches configured public pages with the
manufacturer + MPN query only, extracts page evidence, scores candidates
conservatively, and writes repeatable artifacts under
`output/source_url_agent/runs/{run_id}`.

Dry-run from CSV:

```powershell
python -m pricefetcher.jobs.source_url_agent run --input input/test-1.csv --source all --limit 20 --dry-run
```

Dry-run from the DB catalog:

```powershell
python -m pricefetcher.jobs.source_url_agent from-catalog --source all --missing-only --limit 20 --dry-run
```

Write only high-confidence matches to `source_urls`:

```powershell
python -m pricefetcher.jobs.source_url_agent run --input input/test-1.csv --source all --apply-high-confidence --limit 20
```

Review weak matches by editing:

```text
output/source_url_agent/runs/{run_id}/needs_review_source_urls.csv
```

Then apply the reviewed file:

```powershell
python -m pricefetcher.jobs.source_url_agent apply-review --review-file output/source_url_agent/runs/{run_id}/needs_review_source_urls_reviewed.csv --apply
```

Accepted reviewed URLs use `url_type = discovered` and `trust_level = manual`.
Automatic high-confidence writes use `trust_level = high_confidence` only when
the match method is `exact_mpn_and_brand` and confidence is greater than `0.90`.
All other discovered candidates are exported for review. Existing manual source
URLs are not overwritten by automatic discovery.

Analyze a completed run:

```powershell
python -m pricefetcher.jobs.source_url_agent analyze --run-id {run_id}
```

Move DB-backed candidate review to another machine:

```powershell
python -m pricefetcher.jobs.source_url_agent export-candidates --output output/source_url_agent/source_url_candidates_export.json
python -m pricefetcher.jobs.source_url_agent import-candidates --input output/source_url_agent/source_url_candidates_export.json --dry-run
python -m pricefetcher.jobs.source_url_agent import-candidates --input output/source_url_agent/source_url_candidates_export.json --apply
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

Run fast local tests:

```powershell
python -m pytest -q -m "not slow and not external"
```

Run API contract tests:

```powershell
python -m pytest -q -m contract
```

Run the full test suite:

```powershell
python -m pytest -q
```

The canonical OpenAPI snapshot is
`docs/contracts/openapi.pricefetcher.json`. Regenerate it only after an
intentional API contract change:

```powershell
python -m pricefetcher.jobs.export_openapi_snapshot
```

Review snapshot diffs before committing them.

## Troubleshooting

- `Database is not configured.` Set `PRICEFETCHER_DATABASE_URL` in PowerShell
  or copy `.env.example` to `.env` for local development.
- `Database is configured but unreachable.` Confirm the native Windows
  PostgreSQL service is running and the host, port, role, password, and
  database name are correct.
- `Migrations have not been applied.` Run `alembic upgrade head` from the repo
  root after setting `PRICEFETCHER_DATABASE_URL`.
- `PostgreSQL is required for Catalog.` Import the catalog after migrations
  with `python -m pricefetcher.jobs.ingest_catalog`.
- `psql is not available on PATH.` Add the PostgreSQL `bin` directory to PATH
  or run setup from a terminal where the installer configured it.
- Environment changes persisted with `[Environment]::SetEnvironmentVariable`
  require a new terminal before PowerShell sees them.
