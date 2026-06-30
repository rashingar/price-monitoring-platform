# Developer Setup and Operations Guide

This guide contains the local setup, runtime, database, testing, contract, and troubleshooting procedures for the Price Monitoring & eCommerce Automation Platform.

For the project overview, features, technology stack, architecture summary, and portfolio context, see the [root README](../../README.md).

## Application Map

- `apps/product-factory-api` — Product Factory backend for product preparation, source capture, authoring, rendering, category and filter review, validation, and OpenCart-ready exports.
  - Python project name: `product-factory`
  - Python package: `product_factory`
- `apps/ecommerce-api` — Ecommerce backend for catalog import, source URLs, source capture, price monitoring, alerts, review, exports, durable jobs, and PostgreSQL migrations.
  - Python package: `ecommerce`
- `apps/web` — React/Vite operator console.
  - `/api` routes target Product Factory.
  - `/commerce-api` routes target Ecommerce API.
- `packages/contracts` — Mirrored Product Factory and Ecommerce OpenAPI snapshots used for contract checks and generated frontend API types.
- `scripts` — Root setup, development, test, contract, smoke-check, and repository-hygiene commands.

The two Python APIs are separate runtimes. Do not merge their packages, routes, databases, or internal application code as part of local setup.

## Local Prerequisites

- Windows PowerShell
- Python 3.11 or newer
- Native Windows PostgreSQL with `psql` available on `PATH`
- Node.js and npm
- Playwright Chromium for browser-backed workflows

Docker is not required for the current local setup.

Confirm Python before continuing:

```powershell
python --version
```

The `python` command must resolve to Python 3.11 or newer.

## Working Directory Rules

Use the repository root for:

- setup scripts
- development-server scripts
- contract scripts
- web commands
- repository checks
- most tests

Examples:

```powershell
.\scripts\dev\ecommerce-api.ps1
.\scripts\contracts\check-web-types.ps1
```

Run Ecommerce Alembic commands from `apps/ecommerce-api`:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

Running this from the repository root is not equivalent:

```powershell
python -m alembic -c apps\ecommerce-api\alembic.ini upgrade head
```

The Ecommerce `alembic.ini` contains an app-relative `script_location = migrations`. When run from the root, Alembic looks for a missing root-level `migrations` directory.

## First-Time Setup

Run the setup scripts from the repository root:

```powershell
.\scripts\setup\root-venv.ps1
.\scripts\setup\python-deps.ps1
.\scripts\setup\web.ps1
.\scripts\setup\check-local.ps1
```

These scripts:

- create the root `.venv` when needed
- install both backend applications into the root virtual environment
- install root development tools
- run `npm ci` in `apps/web`
- verify local prerequisites

They do not:

- create a unified Python lockfile
- start the application services
- modify PostgreSQL
- commit generated dependency folders

### Manual Setup Equivalent

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe --version

.\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt
.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps

.\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps

.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

Push-Location apps\web
npm ci
Pop-Location
```

Install Playwright Chromium when browser-backed workflows are required:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Local Environment

Create one private environment file per machine at the repository root:

```powershell
Copy-Item .env.example .env
```

Use the root `.env` for machine-specific paths and private credentials.

Rules:

- do not commit `.env`
- do not create app-local `.env` files for new installations
- operating-system environment variables override root `.env` values
- root `.env` values override deprecated app-local environment files
- deprecated app-local files are fallback-only during the transition period
- diagnostics must print environment-key names only, never secret values

Only configure credentials for workflows you intend to run.

## PostgreSQL Setup

Ecommerce API owns PostgreSQL state for catalog, source, monitoring, alert, review, export, and durable-job workflows.

Product Factory remains artifact and file backed for local product runs.

### Create a Local Database

```sql
CREATE USER ecommerce WITH PASSWORD 'ecommerce';
CREATE DATABASE ecommerce OWNER ecommerce;
GRANT ALL PRIVILEGES ON DATABASE ecommerce TO ecommerce;
```

Set `ECOMMERCE_DATABASE_URL` in the root `.env` or operating-system environment.

Example:

```text
postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce
```

### Apply Migrations

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

### Import the Catalog

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog
Pop-Location
```

### Verify Database Readiness

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.check_db_setup
```

If the command cannot import `ecommerce`, reinstall the editable package:

```powershell
.\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps
```

See [Ecommerce PostgreSQL Local Setup](ecommerce-postgresql-local.md) for backup, rename, and fresh-create procedures.

## Starting the Platform

Run the local startup diagnostic:

```powershell
.\scripts\dev\check-local.ps1
```

Start each application in a separate PowerShell terminal:

```powershell
.\scripts\dev\product-factory-api.ps1
```

```powershell
.\scripts\dev\ecommerce-api.ps1
```

```powershell
.\scripts\dev\web.ps1
```

### Local URLs

- Web console: `http://127.0.0.1:5173`
- Product Factory health: `http://127.0.0.1:8000/api/health`
- Product Factory API docs: `http://127.0.0.1:8000/docs`
- Ecommerce API health: `http://127.0.0.1:8001/api/health`
- Ecommerce API docs: `http://127.0.0.1:8001/docs`
- Ecommerce database readiness: `http://127.0.0.1:8001/api/price-monitoring/db/status`

The web development proxy keeps browser routes stable:

- `/api` proxies to Product Factory at `http://127.0.0.1:8000`
- `/commerce-api` proxies to Ecommerce API at `http://127.0.0.1:8001` and rewrites requests to backend `/api` routes

Ecommerce API health is separate from database readiness. When database-backed pages are unavailable, inspect the database-readiness endpoint.

## Operator Smoke Check

After setup, migrations, catalog import, and application startup, run:

```powershell
.\scripts\check\operator-smoke.ps1
```

Options:

- `-SkipWeb` — use when the web development server is intentionally stopped
- `-Json` — emit machine-readable output

The smoke check is read-only. It does not execute:

- OpenCart export
- catalog import
- Price Monitoring fetches
- Find Source jobs
- Vendor Source captures

## Refreshing the Catalog from OpenCart

Configure the required private `OPENCART_*` values in the root `.env` or operating-system environment before using the Dashboard **Update DB** action.

The workflow:

1. creates a durable `catalog_update_from_opencart` job
2. logs into OpenCart through Playwright
3. exports the configured `sourceCata` CSV Product Export profile
4. applies Ecommerce migrations
5. imports the downloaded catalog into PostgreSQL

Downloads are stored under:

```text
output/catalog_updates/{job_id}/
```

The original downloaded filename is preserved. The normalized import copy is stored as:

```text
output/catalog_updates/{job_id}/sourceCata.csv
```

Inspect the latest catalog-update job:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/catalog/update-db/latest
```

Inspect a specific durable job:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/jobs/{job_id}
```

Default tests mock OpenCart and Playwright. Live OpenCart export tests are manual and opt-in.

## Common Maintenance Tasks

### Regenerate Ecommerce OpenAPI

After an intentional Ecommerce API change:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.export_openapi_snapshot
Pop-Location

Copy-Item apps\ecommerce-api\docs\contracts\openapi.ecommerce.json packages\contracts\openapi.ecommerce.json

.\scripts\contracts\generate-web-types.ps1
.\scripts\contracts\check-web-types.ps1
```

### Backfill Normalized Price-Monitoring Listings

Backfill all supported legacy offer observations:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.backfill_price_observation_listings
Pop-Location
```

Backfill one run:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.backfill_price_observation_listings --run-id RUN_ID
Pop-Location
```

### Focused Price-Monitoring Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -vv apps/ecommerce-api/tests/test_price_monitoring_review_export.py

Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m pytest -vv tests/test_price_monitoring_db.py tests/test_price_monitoring_db_policy.py
Pop-Location
```

## Development Checks

Run repository hygiene before committing:

```powershell
.\scripts\check\hygiene.ps1
```

Run staged-only path and whitespace checks:

```powershell
.\scripts\check\hygiene.ps1 -Staged
```

Hygiene includes Black formatting checks. Black is installed by:

```powershell
.\scripts\setup\python-deps.ps1
```

Check Python formatting:

```powershell
.\.venv\Scripts\python.exe -m black --check apps\ecommerce-api apps\product-factory-api scripts
```

Apply Python formatting:

```powershell
.\.venv\Scripts\python.exe -m black apps\ecommerce-api apps\product-factory-api scripts
```

## Test Profiles

### Fast Aggregate Verification

```powershell
.\scripts\test\fast.ps1
```

The root fast script runs:

- snapshot hygiene
- fast-marker hygiene
- Product Factory fast checks
- Ecommerce fast checks
- web fast checks
- contract-mirror checks

The fast profile excludes live external services, full end-to-end workflows, slow tests, legacy tests, runtime profiles, Ecommerce `db_integration`, and PostgreSQL-required profiles where appropriate.

For focused backend changes, prefer:

```powershell
.\scripts\test\codex-product-factory.ps1
```

```powershell
.\scripts\test\codex-ecommerce.ps1
```

### App-Specific and Contract Checks

```powershell
.\scripts\test\product-factory-api.ps1
.\scripts\test\ecommerce-api.ps1
.\scripts\test\product-factory-runtime.ps1
.\scripts\test\product-factory-golden.ps1
.\scripts\test\ecommerce-runtime.ps1
.\scripts\test\ecommerce-golden.ps1
.\scripts\test\ecommerce-db-contract.ps1
.\scripts\test\ecommerce-db-integration.ps1
.\scripts\test\ecommerce-postgres.ps1
.\scripts\test\check-snapshots.ps1
.\scripts\test\check-fast-marker-hygiene.ps1
.\scripts\test\web.ps1
.\scripts\contracts\check.ps1
.\scripts\contracts\check-web-types.ps1
.\scripts\check\all.ps1
```

### Test Policy

- test scripts use verbose output
- runtime tests are opt-in
- golden tests use deterministic fixtures and reviewed contract artifacts
- snapshot expected files must not be changed unless the work explicitly approves snapshot updates
- Ecommerce database tests are divided into:
  - `db_contract`
  - `db_integration`
  - `postgres_required`
- local deterministic `db_contract` tests may run in fast profiles
- `db_integration` and `postgres_required` remain opt-in
- Python backend tests have a default 60-second per-test timeout
- web Vitest tests have a default 10-second per-test timeout
- tests requiring longer execution must explicitly override the timeout and remain outside default fast profiles

See [Testing Strategy](testing-strategy.md).

## Contracts and Generated Frontend Types

Canonical app-local OpenAPI snapshots are mirrored under `packages/contracts`.

Check mirrors:

```powershell
.\scripts\contracts\check.ps1
```

After an API contract change:

1. regenerate the snapshot from the owning application
2. refresh the corresponding file under `packages/contracts`
3. regenerate frontend API types
4. run the contract and type checks

```powershell
.\scripts\contracts\generate-web-types.ps1
.\scripts\contracts\check-web-types.ps1
```

Generated frontend API files under:

```text
apps/web/src/api/generated/
```

are committed contract artifacts. Do not edit them manually.

Existing manual frontend API clients remain the runtime request implementation.

## Troubleshooting

### Alembic Reports `Path doesn't exist: migrations`

Cause: the command was probably run from the repository root.

Fix:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

### Price-Monitoring Pages Report That the Database Is Not Ready

Open:

```text
http://127.0.0.1:8001/api/price-monitoring/db/status
```

Inspect:

- `missing_tables`
- `alembic_up_to_date`
- `blocking_reasons`

Apply migrations from `apps/ecommerce-api`, then check readiness again.

### OpenAPI Contract Checks Fail

1. regenerate the owning application's OpenAPI snapshot
2. copy the app-local snapshot to `packages/contracts`
3. regenerate frontend types
4. rerun contract checks

```powershell
.\scripts\contracts\generate-web-types.ps1
.\scripts\contracts\check-web-types.ps1
```

### Frontend Type Errors After Backend Response Changes

- update manual types under `apps/web/src/api/*Types.ts` when required
- regenerate generated OpenAPI types
- do not manually edit `apps/web/src/api/generated/*.ts`

### Pip Reports Invalid `~...` Distributions

These are usually stale local package directories left by interrupted or replaced pip installations.

Inspect them first:

```powershell
Get-ChildItem .venv\Lib\site-packages -Force |
    Where-Object { $_.Name -like "~*" } |
    Select-Object FullName
```

After visual confirmation, remove only those stale directories:

```powershell
Get-ChildItem .venv\Lib\site-packages -Force |
    Where-Object { $_.Name -like "~*" } |
    Remove-Item -Recurse -Force
```

Do not commit changes under `.venv`.

## Artifact and Secret Policy

Generated runtime outputs must remain outside Git:

- `.venv/`
- `node_modules/`
- `work/`
- `output/`
- `runs/`
- `logs/`
- `products/`
- `__pycache__/`
- `.pytest_cache/`

Do not commit:

- `.env`
- `.secrets`
- credentials or tokens
- local databases
- database dumps or backups
- raw provider HTML captures
- generated product outputs
- private keys

Use `.env.example` as the public configuration template.

## Related Documentation

- [Root Project Overview](../../README.md)
- [Current Architecture](../architecture/current-architecture.md)
- [Operator Startup](operator-startup.md)
- [Codex Workflow](codex-workflow.md)
- [Testing Strategy](testing-strategy.md)
- [Ecommerce PostgreSQL Local Setup](ecommerce-postgresql-local.md)
- [Contracts-First Integration](../decisions/0005-contracts-first-integration.md)
- [Product Factory API](../../apps/product-factory-api/README.md)
- [Ecommerce API](../../apps/ecommerce-api/README.md)
- [Web Console](../../apps/web/README.md)

Historical material remains available in:

- [Monorepo Migration](monorepo-migration.md)
- [Target Architecture](../architecture/target-architecture.md)

Current operations should follow the active architecture and runbooks listed above.
