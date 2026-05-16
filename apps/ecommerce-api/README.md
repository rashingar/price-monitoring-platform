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
- storing durable Ecommerce job state for long workflow inspection/cancellation
- reviewing fetched prices and exporting manual OpenCart price-update CSV files
- safely reading/writing approved local CSV files for browser UI workflows
- exposing generated artifacts through safe API download and preview endpoints

Generated run files are written under `output/` by default. Catalog and Price
Monitoring workflows require PostgreSQL. Health, safe file editing,
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

The repo-root `.env.example` file is the canonical template with safe local
defaults and placeholders. Copy it to the repository root for private local
development:

```powershell
Copy-Item .env.example .env
```

Do not commit `.env` or any file containing real credentials. Do not create
app-local `.env` files for new setups.

Ecommerce loads `.env` automatically for local commands. If the same setting
exists in both `.env` and the real Windows/PowerShell environment, the
OS environment value wins over `.env`. Repo-root `.env` wins over deprecated
app-local `.env` files. Existing app-local `.env` files are fallback only for
keys missing from both OS env and repo-root `.env`, and diagnostics print key
names only, never secret values.

Important variables:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
$env:ECOMMERCE_SOURCE_CATA_PATH = "C:\path\to\sourceCata.csv"
$env:ECOMMERCE_PRICE_IGNORE_PATH = "C:\path\to\price_ignore.csv"
$env:CATALOG_UPDATE_EXCLUDED_MODELS_PATH = "C:\path\to\codes_not_in_entersoft.csv"
$env:ECOMMERCE_ARTIFACT_ROOTS = "D:\Ecommerce\output\ecommerce\monitoring\runs"
$env:ECOMMERCE_FILE_ROOTS = "C:\Users\user\Downloads;C:\Exports;output"
```

`ECOMMERCE_DATABASE_URL` is required before Catalog import, Catalog browsing,
Price Monitoring runs, observations, history, or alerts are ready.

Telegram Product Factory intake is hosted by Ecommerce API but starts jobs in
Product Factory API. It is disabled by default and requires Telegram's webhook
secret header plus allowed chat/user IDs:

```powershell
$env:PRODUCT_FACTORY_TELEGRAM_ENABLED = "true"
$env:PRODUCT_FACTORY_TELEGRAM_BOT_TOKEN = "your-telegram-bot-token"
$env:PRODUCT_FACTORY_TELEGRAM_WEBHOOK_SECRET = "your-shared-webhook-secret"
$env:PRODUCT_FACTORY_TELEGRAM_ALLOWED_CHAT_IDS = "-1001234567890"
$env:PRODUCT_FACTORY_TELEGRAM_ALLOWED_USER_IDS = "123456789"
$env:PRODUCT_FACTORY_WAREHOUSE_CATALOG_PATH = "\\ERPSERVER\Share\warehouse.csv"
$env:PRODUCT_FACTORY_WAREHOUSE_CATALOG_MODEL_COLUMN = "model"
$env:PRODUCT_FACTORY_WAREHOUSE_CATALOG_NAME_COLUMN = "name"
$env:PRODUCT_FACTORY_WAREHOUSE_CATALOG_ENCODING = "utf-8-sig"
$env:PRODUCT_FACTORY_API_BASE_URL = "http://127.0.0.1:8000"
$env:PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_PATH = "C:\path\to\product_factory_source_resolution.json"
```

The Telegram intake looks up the Product Factory product name only from the ERP
warehouse CSV at `PRODUCT_FACTORY_WAREHOUSE_CATALOG_PATH`. It does not use the
Ecommerce database for this product-name lookup.

When a command omits a manual URL, the intake resolves the scrape source with
Brave Search using ERP warehouse identity fields: product name, manufacturer,
MPN, barcode, and category. The default resolver config is
`config/product_factory_source_resolution.json`; override it with
`PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_PATH`. The config owns source weights,
domains, aliases, product URL patterns, confidence thresholds, max suggestions,
and the pending-choice TTL. BestPrice and Skroutz command flags only affect the
Product Factory product configuration; they do not choose the scrape source.

If the best candidate reaches `minimum_confidence`, Telegram receives the
resolved model, product name, source, Brave page title, URL, and raw confidence
before the Product Factory job is enqueued. If no candidate reaches that
threshold but at least one reaches `suggestion_confidence`, the bot sends
numbered inline buttons for the candidates and does not enqueue until the
operator selects one. Pending choices expire after 15 minutes by default.
Manual URLs bypass Brave resolution and are sent as `manual_url` source
resolution metadata.

Dashboard `Update DB` also requires OpenCart export settings. Keep these only
in private `.env` or OS environment variables:

```powershell
$env:OPENCART_STORE_BASE = "https://your-store.example"
$env:OPENCART_ADMIN_PATH = "admin"
$env:OPENCART_ADMIN_USER = "your-admin-user"
$env:OPENCART_ADMIN_PASS = "your-admin-password"
$env:OPENCART_EXPORT_PROFILE = "sourceCata"
```

`OPENCART_EXPORT_PROFILE` defaults to `sourceCata` when unset. Do not use
`OPENCART_IMPORT_PROFILE` for this workflow; this feature exports from
OpenCart before importing into Ecommerce PostgreSQL.

## Dashboard Update DB

The Dashboard `Update DB` button calls `POST /api/catalog/update-db` through
the web `/commerce-api` proxy. The backend creates a durable
`catalog_update_from_opencart` job and runs the workflow in a background task:

1. load OpenCart export config from env
2. run `alembic upgrade head` from `apps/ecommerce-api`
3. log into OpenCart with Playwright
4. export the configured CSV Product Export profile
5. save the download under `output/catalog_updates/{job_id}/`
6. copy the imported CSV to `output/catalog_updates/{job_id}/sourceCata.csv`
7. remove hard-excluded models and write `sourceCata.filtered.csv`
8. import the filtered CSV with the existing catalog ingestion logic
9. purge excluded models from catalog-owned DB state

Use these endpoints to inspect durable state:

```text
GET /api/catalog/update-db/latest
GET /api/jobs/{job_id}
GET /api/jobs?job_type=catalog_update_from_opencart
```

Job results include artifact paths, export profile, downloaded file size,
migration output, exclusion counts, purge counts, and ingest counts. Responses
and job results must not contain OpenCart credentials. Default automated tests
mock Playwright/OpenCart; live OpenCart export verification is manual/opt-in
only.

`config/catalog/codes_not_in_entersoft.csv` is the default hard pre-import
denylist for Dashboard `Update DB`. The file may contain a `model` header or a
single model column. Matching is exact after trimming whitespace, so leading
zeros are significant. Set `CATALOG_UPDATE_EXCLUDED_MODELS_PATH` only when a
different denylist file is required. If the default file is missing the job
continues with zero exclusions; if an explicit override is missing the job
fails before import.

Excluded models are removed from the normalized OpenCart export before import
and are purged from catalog-owned state such as `catalog_products`,
`source_urls`, and Source URL Agent task/candidate rows. This is a backend
business rule, not an operator review workflow.

When the OpenCart export fails after Playwright has opened a page, the job
writes safe diagnostics under:

```text
output/catalog_updates/{job_id}/diagnostics/
```

Inspect `failure_context.json` first for the failed step, redacted current URL,
export profile, timeout, headed mode, error class, and sanitized error message.
If available, `failure.png` captures the browser state with credential fields
redacted before screenshot capture. Do not commit files under `output/`; they
are runtime artifacts and may describe local operator state.

### Durable job worker

The API still starts Dashboard `Update DB` jobs in a FastAPI background task by
default so local Dashboard behavior is unchanged. For crash-resumable operator
execution, run the DB-backed worker in a separate terminal from the repository
root:

```powershell
.\scripts\dev\ecommerce-worker.ps1 --job-type catalog_update_from_opencart --poll-seconds 5 --limit 1
```

Useful one-shot inspection and execution commands:

```powershell
.\scripts\dev\ecommerce-worker.ps1 --job-type catalog_update_from_opencart --once --dry-run
.\scripts\dev\ecommerce-worker.ps1 --job-type catalog_update_from_opencart --once
```

The worker loads `.env`, uses `ECOMMERCE_DATABASE_URL`, selects the oldest
queued matching jobs, claims them in the database, and runs registered handlers
through the same durable `execute_job` finalization path as API-triggered work.
On PostgreSQL it uses row locking with `SKIP LOCKED` to reduce duplicate local
worker execution.

By default, each worker pass marks `running` jobs with no heartbeat for more
than 60 minutes as `failed` before claiming new queued jobs:

```powershell
.\scripts\dev\ecommerce-worker.ps1 --job-type catalog_update_from_opencart --once --stale-running-after-minutes 60
```

Use the existing job endpoints to inspect and recover state:

```text
GET /api/jobs?job_type=catalog_update_from_opencart
GET /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
```

`--dry-run` reports stale and queued matches without marking stale jobs failed,
claiming queued jobs, or executing handlers.

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
The helper script `scripts\setup_postgres_windows.ps1` can generate the same
local Windows setup commands without using Docker.

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
from a CSV or the DB-backed catalog, searches configured public pages with a
bounded ranked query strategy, extracts page evidence, scores candidates
conservatively, and writes repeatable artifacts under
`output/ecommerce/source-url-agent/runs/{run_id}`.

The default query order is manufacturer + MPN, MPN only, manufacturer + model,
model only, manufacturer + product name, then product name only. Source
definitions can prepend `query_templates`, and all variants are deduplicated
case-insensitively before the source-specific `max_searches_per_product` limit
is applied.

Source configuration is split by responsibility. `config/source_url_agent/sources.json`
owns source identity and source URL/search rules: source names, domains, public
search URL templates, product URL patterns, blocked URL patterns, query
templates, rate limits, and per-source search/candidate limits.
`config/source_url_agent/search_providers.json` owns provider definitions and
provider cascade order. The only implemented provider is `browser_fallback`,
which wraps the existing public source search behavior. It fetches configured
source search pages through the browser session, extracts product-looking URLs
with existing source rules, then fetches candidate product pages for evidence.
External providers can be added later behind the same abstraction. Provider
provenance is stored in candidate evidence/details JSON and run artifacts for
debugging and future quality metrics.

Automatic writes remain conservative: only exact MPN and brand matches above
`0.90` can be high-confidence. Title-only matches, marketplace body-only MPN
evidence, and competing plausible candidates stay out of auto-apply and require
review. Composite mismatch detection rejects single catalog products when a
candidate looks like a bundle, including Greek/local markers such as
`με εστίες`, `με επαγωγικές`, `με κεραμικές`, `φούρνος με εστίες`, `σετ`,
`πακέτο`, `μαζί με`, or double-MPN forms such as `HBA514BS3 + PKE61RBA2E`.
Catalog rows that are themselves composite/bundle products are not rejected for
those markers.

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

For Codex prompts that touch only Ecommerce API backend files, prefer:

```powershell
.\scripts\test\codex-ecommerce.ps1
```

Runtime tests are opt-in:

```powershell
.\scripts\test\ecommerce-runtime.ps1
```

Golden tests are deterministic fixture regressions:

```powershell
.\scripts\test\ecommerce-golden.ps1
```

Source capture and Vendor Sources golden tests use narrow JSON snapshots for
parser, scoring, sanitization, direct Skroutz endpoint, source selection,
run-result serialization, and API response contracts. DB source URL/product
source persistence belongs in `db_contract`; run history, artifacts, scheduled
capture, and vendor capture orchestration stay in the runtime profile.
Snapshots must not include timestamps, temp paths, secrets, full raw payload
dumps, or live service side effects.

For targeted checks, run the specific pytest file or node that maps to the
change:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m pytest tests\path\to\relevant_test.py -vv -ra
Pop-Location
```

The direct module form is `python -m ecommerce.jobs.check_db_setup`; use the
repo `.venv` Python executable for this project.

`.\scripts\test\fast.ps1` is Codex-safe aggregate fast verification for the
monorepo. Prefer `.\scripts\test\codex-ecommerce.ps1` for Ecommerce-only
patches because it is faster and narrower; root fast is appropriate when a
prompt touches multiple apps, shared contracts, or repo-wide test
infrastructure. Full suites, runtime profiles, `db_integration`,
`postgres_required`, external, e2e, and legacy tests are manual unless
explicitly requested. Ecommerce DB fast coverage includes `db_contract` only.

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

- `Database is not configured.` Set `ECOMMERCE_DATABASE_URL` in repo-root
  `.env` or in the OS environment.
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
