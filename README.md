# Price Monitoring Platform

Price Monitoring Platform is a local operator platform for creating product
content, managing an ecommerce catalog, monitoring competitor prices, and
reviewing/exporting updates through a browser UI.

The active commerce backend is the Ecommerce API. No legacy Ecommerce backend
naming should exist in active code, docs, scripts, tests, or paths.

## App Map

- `apps/product-factory-api`: Product Factory backend for product preparation,
  capture, authoring, rendering, and OpenCart-ready product exports.
- `apps/ecommerce-api`: Ecommerce API backend for catalog import, source URLs,
  source capture, price monitoring, alerts, review, exports, and database
  migrations.
- `apps/web`: React/Vite operator console. Browser routes `/api` and
  `/commerce-api` are intentionally stable.

The two Python APIs are separate runtimes. Do not merge Product Factory and
Ecommerce API code or databases as part of local setup.

## First Run After Clone

Preferred setup path from the repository root in PowerShell:

```powershell
.\scripts\setup\root-venv.ps1
.\scripts\setup\python-deps.ps1
.\scripts\setup\web.ps1
.\scripts\setup\check-local.ps1
```

These scripts create the root `.venv` if needed, install the two backend
projects into that root `.venv`, run `npm ci` in `apps/web`, and verify local
setup prerequisites. They do not create a unified Python lockfile, start
servers, or mutate PostgreSQL.

The equivalent manual commands remain:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt
.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps
.\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps
Push-Location apps\web
npm ci
Pop-Location
```

Then configure PostgreSQL for Ecommerce API, apply migrations, and import the
catalog:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.ingest_catalog
Pop-Location
```

Start the apps in separate PowerShell terminals:

```powershell
.\scripts\dev\product-factory-api.ps1
.\scripts\dev\ecommerce-api.ps1
.\scripts\dev\web.ps1
```

Open the web UI at `http://127.0.0.1:5173`. Backend health endpoints are
`http://127.0.0.1:8000/api/health` for Product Factory and
`http://127.0.0.1:8001/api/health` for Ecommerce API.

## Quick Start Checklist

1. Create the root `.venv`.
2. Install backend dependencies into the root `.venv`.
3. Run `npm ci` in `apps/web`.
4. Create or rename the local PostgreSQL database/user to `ecommerce`.
5. Set `ECOMMERCE_DATABASE_URL`.
6. Run Ecommerce API migrations.
7. Import the catalog.
8. Start Product Factory API.
9. Start Ecommerce API.
10. Start the web app and open the local UI.

## Local Prerequisites

- Windows PowerShell.
- Python 3.11 or newer. The `python` command must resolve to Python 3.11+.
  If `python` is not found or is too old, install a supported Python version
  and reopen PowerShell.
- Native Windows PostgreSQL with `psql` on `PATH`.
- Node.js/npm for the web app.
- Playwright Chromium if you run browser-backed backend workflows.

Docker is not required for the current local setup.

## Root Virtual Environment Setup

Root scripts use one repository-level Python environment:

```powershell
.\scripts\setup\root-venv.ps1
```

Manual equivalent:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe --version
```

`root-venv.ps1` requires Python 3.11 or newer and creates `.venv` only when it
is missing. Use `-Force` or `-Recreate` only when you intentionally want to
delete and recreate the root `.venv`. The script does not install app
dependencies.

Runtime and test scripts call `.venv\Scripts\python.exe` and fail clearly when
it is missing. They do not install dependencies automatically.

If you intentionally manage multiple Python versions with the Windows `py`
launcher, you may use a supported version explicitly, for example
`py -3.12 -m venv .venv`. The default operator command remains
`python -m venv .venv`.

## Python Dependency Setup

Install backend dependencies with:

```powershell
.\scripts\setup\python-deps.ps1
```

Manual equivalent:

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt
.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps
.\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps
```

Product Factory app name is `product-factory-api`. Its Python project
package/install name is `product-factory`, and its internal import package
remains `pipeline` under `apps/product-factory-api/src`; this does not rename
`pipeline`. Ecommerce API uses the `ecommerce` package under
`apps/ecommerce-api/src`. Root scripts expect the root `.venv` and do not use
app-local virtual environments.

The setup script uses the existing app requirement files and editable installs.
It does not create a unified Python lockfile and does not install unrelated dev
tools.

## Frontend Dependency Setup

Install web dependencies with:

```powershell
.\scripts\setup\web.ps1
```

Manual equivalent:

```powershell
Push-Location apps\web
npm ci
Pop-Location
```

Web scripts run from `apps/web` and fail clearly when `node_modules` is
missing.

Run the setup diagnostic after dependency setup:

```powershell
.\scripts\setup\check-local.ps1
```

This finite check verifies root `.venv`, backend imports, web dependencies,
mirrored contracts, and generated web API type freshness when `node_modules`
exists. It does not start servers and does not touch PostgreSQL.

## PostgreSQL Setup Or Rename

Ecommerce API uses PostgreSQL for catalog and price monitoring workflows.
PostgreSQL setup remains manual and explicit. The setup scripts do not create
users, create databases, apply migrations, import catalogs, or change schema.

Fresh local setup:

```sql
CREATE USER ecommerce WITH PASSWORD 'ecommerce';
CREATE DATABASE ecommerce OWNER ecommerce;
GRANT ALL PRIVILEGES ON DATABASE ecommerce TO ecommerce;
```

PowerShell environment variable:

```powershell
$env:ECOMMERCE_DATABASE_URL = "postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
```

For a detailed backup, local database rename, and fresh-create runbook, see
[Ecommerce PostgreSQL Local Setup](docs/runbooks/ecommerce-postgresql-local.md).

## Start Commands

Run the local startup diagnostic before starting long-running servers:

```powershell
.\scripts\dev\check-local.ps1
```

Then run each app in a separate PowerShell terminal:

```powershell
# Terminal 1: Product Factory API
.\scripts\dev\product-factory-api.ps1

# Terminal 2: Ecommerce API
.\scripts\dev\ecommerce-api.ps1

# Terminal 3: Web
.\scripts\dev\web.ps1
```

The backend scripts use the root `.venv`. Product Factory starts on
`http://127.0.0.1:8000` and serves health at
`http://127.0.0.1:8000/api/health`. Ecommerce API starts on
`http://127.0.0.1:8001` and serves health at
`http://127.0.0.1:8001/api/health`. The web script runs from `apps/web`,
requires `apps/web/node_modules`, and starts Vite on
`http://127.0.0.1:5173`.

The web dev proxy keeps browser routes stable:

- `/api` proxies to Product Factory at `http://127.0.0.1:8000`.
- `/commerce-api` proxies to Ecommerce API at `http://127.0.0.1:8001` and
  rewrites to backend `/api` routes.

Ecommerce API health is separate from database readiness. If
`ECOMMERCE_DATABASE_URL` is missing, PostgreSQL is stopped, credentials are
wrong, migrations are missing, or catalog data has not been imported, the API
can still be running while DB-backed workflows report not ready. Check
`http://127.0.0.1:8001/api/price-monitoring/db/status` for setup hints.

## Test Commands

The default Codex-safe test command is:

```powershell
.\scripts\test\fast.ps1
```

Run app-specific tests through the root scripts:

```powershell
.\scripts\test\product-factory-api.ps1
.\scripts\test\ecommerce-api.ps1
.\scripts\test\web.ps1
.\scripts\test\fast.ps1
.\scripts\contracts\check.ps1
.\scripts\contracts\check-web-types.ps1
```

The test scripts use verbose output. They should not run live external scraping
tests by default. See [Testing Strategy](docs/runbooks/testing-strategy.md) for
the category definitions and fast-suite rules.

## Contract And Generated Type Commands

Mirrored OpenAPI contracts live under `packages/contracts` and are checked
against app-local snapshots with:

```powershell
.\scripts\contracts\check.ps1
```

Web API type scaffolding is generated from those mirrors into
`apps/web/src/api/generated`:

```powershell
.\scripts\contracts\generate-web-types.ps1
.\scripts\contracts\check-web-types.ps1
```

The generated web API type files are committed source-facing contract artifacts
and should not be edited by hand. The existing manual web clients remain the
runtime source of truth for now. Selected web type aliases consume generated
OpenAPI schema types for compile-time drift checks, but generated clients are
not used for fetch behavior.

## Local URLs

- Web app: `http://127.0.0.1:5173`
- Product Factory API health: `http://127.0.0.1:8000/api/health`
- Ecommerce API health: `http://127.0.0.1:8001/api/health`
- Ecommerce API docs: `http://127.0.0.1:8001/docs`
- Ecommerce database status:
  `http://127.0.0.1:8001/api/price-monitoring/db/status`

## Generated And Ignored Folders

Generated runtime outputs stay out of Git:

- `.venv/`
- `node_modules/`
- `work/`
- `output/`
- `runs/`
- `logs/`
- `products/`
- `__pycache__/`
- `.pytest_cache/`

Ecommerce generated outputs use `output/ecommerce/...` by default.
Generated web API types under `apps/web/src/api/generated` are an exception:
they are committed contract artifacts, not runtime outputs.

## Safety Notes

- Do not commit `.env`, `.secrets`, credentials, tokens, or local secrets.
- Do not commit database files, dumps, or backups.
- Do not commit raw provider HTML captures.
- Do not commit generated product folders or runtime output folders.
- Use `.env.example` files only as safe templates.
- Keep real local credentials in private environment variables or private
  ignored `.env` files.

## Architecture And Runbooks

- [Target Architecture](docs/architecture/target-architecture.md)
- [Testing Strategy](docs/runbooks/testing-strategy.md)
- [Operator Startup](docs/runbooks/operator-startup.md)
- [Monorepo Migration Runbook](docs/runbooks/monorepo-migration.md)
- [Ecommerce PostgreSQL Local Setup](docs/runbooks/ecommerce-postgresql-local.md)
- [App Naming and Domain Boundaries](docs/decisions/0002-app-naming-and-domain-boundaries.md)
- [Contracts-First Integration](docs/decisions/0005-contracts-first-integration.md)

The active backend name is Ecommerce API. Do not introduce compatibility aliases
or old Ecommerce backend names in code, scripts, docs, tests, or filenames.
