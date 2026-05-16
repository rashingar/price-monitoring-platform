# Operator Startup

Use this runbook to start the local platform from a clean checkout or an
already-configured workstation.

## 1. Verify Prerequisites

Required:

- Windows PowerShell.
- Python 3.11 or newer.
- Node.js/npm.
- Native Windows PostgreSQL with `psql` on `PATH`.

Optional for browser-backed Product Factory workflows:

- Playwright Chromium.

## 2. First-Time Dependency Setup

From the repository root:

```powershell
.\scripts\setup\root-venv.ps1
.\scripts\setup\python-deps.ps1
.\scripts\setup\web.ps1
.\scripts\setup\check-local.ps1
```

The setup scripts create `.venv` if needed, install backend dependencies and
editable packages into the root `.venv`, run `npm ci` in `apps/web`, and verify
local dependency/contract readiness.

They do not create PostgreSQL users or databases, apply migrations, import the
catalog, start servers, or commit generated dependency folders.

The root `.venv` is the only supported Python environment for local repo
commands. If `.venv` is missing, recreate it from the repository root:

```powershell
.\scripts\setup\root-venv.ps1
.\scripts\setup\python-deps.ps1
```

If `apps\web\node_modules` is missing, reinstall web dependencies:

```powershell
.\scripts\setup\web.ps1
```

## 3. Configure Local Environment

Create the single private local env file at the repository root:

```powershell
Copy-Item .env.example .env
```

Fill machine-specific paths and private credentials there. Do not create
app-local `.env` files for new setups. Existing app-local `.env` files are
deprecated compatibility fallback only: OS env vars override repo-root `.env`,
repo-root `.env` overrides app-local `.env`, and app-local `.env` may fill only
keys missing from both. Diagnostics print key names only, never secret values.

## 4. Configure Ecommerce Database

Create a local database if one does not already exist:

```sql
CREATE USER ecommerce WITH PASSWORD 'ecommerce';
CREATE DATABASE ecommerce OWNER ecommerce;
GRANT ALL PRIVILEGES ON DATABASE ecommerce TO ecommerce;
```

Set `ECOMMERCE_DATABASE_URL` in repo-root `.env` or the OS environment.

Apply migrations and import the catalog:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog
Pop-Location
```

For database backup, rename, or rebuild steps, see
[Ecommerce PostgreSQL Local Setup](ecommerce-postgresql-local.md).

## 5. Preflight

Run one of the setup/dev diagnostics from the repository root:

```powershell
.\scripts\setup\check-local.ps1
```

or:

```powershell
.\scripts\dev\check-local.ps1
```

These checks verify imports, editable installs, web dependencies, mirrored
contracts, and generated web type freshness when `node_modules` exists. They do
not start servers or mutate PostgreSQL.

## 6. Start Services

Use four separate PowerShell terminals from the repository root.

Terminal 1:

```powershell
.\scripts\dev\product-factory-api.ps1
```

Terminal 2:

```powershell
.\scripts\dev\ecommerce-api.ps1
```

Terminal 3:

```powershell
.\scripts\dev\ecommerce-worker.ps1 --poll-seconds 5 --limit 1
```

The Ecommerce durable worker is the canonical executor for queued DB-backed
jobs. By default, `ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE=true` preserves
local operator behavior: the Ecommerce API enqueues durable jobs and immediately
starts local FastAPI background execution. Set it to `false` when the API should
enqueue only and this worker terminal must execute queued jobs.

Terminal 4:

```powershell
.\scripts\dev\web.ps1
```

## 7. Open Local URLs

- Web UI: `http://127.0.0.1:5173`
- Product Factory API health: `http://127.0.0.1:8000/api/health`
- Product Factory API docs: `http://127.0.0.1:8000/docs`
- Ecommerce API health: `http://127.0.0.1:8001/api/health`
- Ecommerce API docs: `http://127.0.0.1:8001/docs`
- Ecommerce DB status:
  `http://127.0.0.1:8001/api/price-monitoring/db/status`

The web dev proxy keeps these browser routes stable:

- `/api` -> Product Factory API.
- `/commerce-api` -> Ecommerce API, rewritten to backend `/api` routes.

## 8. Run Operator Smoke Check

After setup, migrations, catalog import, and service startup, run:

```powershell
.\scripts\check\operator-smoke.ps1
```

The script verifies Product Factory API health, Ecommerce API health, Ecommerce
DB readiness, Alembic-at-head status when reported, Catalog summary, durable
jobs, latest catalog update job status, Vendor Sources summary, Price
Monitoring DB status, and the web dev server if it is running. It prints an
operator table with `passed`, `warn`, `failed`, or `skipped` statuses and exits
nonzero when required readiness checks fail.

Useful variants:

```powershell
.\scripts\check\operator-smoke.ps1 -SkipWeb
.\scripts\check\operator-smoke.ps1 -Json
.\scripts\check\operator-smoke.ps1 -EcommerceBaseUrl http://127.0.0.1:9001
```

This check is read-only. It does not run live OpenCart export, catalog import,
Price Monitoring fetches, Find Source runs, Vendor Source captures, browser
automation, or scraping workflows.

Common failures usually mean:

- API health failed: the corresponding dev server is not running or is on a
  different port.
- DB readiness failed: `ECOMMERCE_DATABASE_URL` is missing in the Ecommerce API
  terminal, PostgreSQL is stopped, migrations are missing, or the catalog has
  not been imported.
- Catalog or Vendor Sources summary failed: Ecommerce database readiness is
  still incomplete.
- Web warning: the Vite dev server is not running; rerun with `-SkipWeb` if
  that is intentional.

## 9. If Ecommerce DB Is Not Ready

`/api/health` only proves the Ecommerce API process is running. Use the DB
status endpoint when catalog or price monitoring screens report not ready.

DB-not-ready means the API can answer HTTP requests, but DB-backed workflows
cannot safely run yet. Catalog browsing, price monitoring, observation history,
alerts, and DB-backed exports may stay locked until the status endpoint reports
the database configured, reachable, migrated, and populated with an active
catalog.

Common causes:

- `ECOMMERCE_DATABASE_URL` is missing from OS env and repo-root `.env`.
- PostgreSQL is stopped.
- Database/user credentials are wrong.
- Alembic migrations have not been applied.
- Catalog import has not run.

Recovery path:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.check_db_setup
Pop-Location
```

## 10. Before Committing Startup Changes

```powershell
.\scripts\check\hygiene.ps1
.\scripts\contracts\check.ps1
git diff --check
git status --short
```

If `apps/web/node_modules` exists:

```powershell
.\scripts\contracts\check-web-types.ps1
```
