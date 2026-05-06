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

## 3. Configure Ecommerce Database

Create a local database if one does not already exist:

```sql
CREATE USER ecommerce WITH PASSWORD 'ecommerce';
CREATE DATABASE ecommerce OWNER ecommerce;
GRANT ALL PRIVILEGES ON DATABASE ecommerce TO ecommerce;
```

Set the database URL in each terminal that runs Ecommerce commands:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
```

Apply migrations and import the catalog:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog
Pop-Location
```

For database backup, rename, or rebuild steps, see
[Ecommerce PostgreSQL Local Setup](ecommerce-postgresql-local.md).

## 4. Preflight

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

## 5. Start Services

Use three separate PowerShell terminals from the repository root.

Terminal 1:

```powershell
.\scripts\dev\product-factory-api.ps1
```

Terminal 2:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
.\scripts\dev\ecommerce-api.ps1
```

Terminal 3:

```powershell
.\scripts\dev\web.ps1
```

## 6. Open Local URLs

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

## 7. If Ecommerce Is Not Ready

`/api/health` only proves the Ecommerce API process is running. Use the DB
status endpoint when catalog or price monitoring screens report not ready.

Common causes:

- `ECOMMERCE_DATABASE_URL` is missing in the running terminal.
- PostgreSQL is stopped.
- Database/user credentials are wrong.
- Alembic migrations have not been applied.
- Catalog import has not run.

## 8. Before Committing Startup Changes

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
