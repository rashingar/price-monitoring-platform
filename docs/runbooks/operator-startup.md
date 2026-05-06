# Operator Startup

This runbook verifies the local monorepo startup flow without changing backend
routes, frontend browser routes, package names, or database schema.

## Preflight

From the repository root:

```powershell
.\scripts\setup\check-local.ps1
```

This setup diagnostic checks the root `.venv`, Product Factory import,
Ecommerce API import, web `node_modules`, mirrored contracts, and generated web
API type freshness when `node_modules` exists. It does not start servers and
does not mutate the database.

The dev preflight is equivalent for startup checks:

```powershell
.\scripts\dev\check-local.ps1
```

## First-Time Setup

For a fresh clone, run the setup helpers from the repository root:

```powershell
.\scripts\setup\root-venv.ps1
.\scripts\setup\python-deps.ps1
.\scripts\setup\web.ps1
.\scripts\setup\check-local.ps1
```

What they do:

- `root-venv.ps1` checks `python --version`, requires Python 3.11 or newer,
  and creates `.venv` only when missing. Use `-Force` or `-Recreate` only when
  intentionally deleting and recreating `.venv`.
- `python-deps.ps1` installs Product Factory requirements and editable package,
  then Ecommerce API locked requirements and editable package, all into the
  root `.venv`.
- `web.ps1` runs `npm ci` in `apps/web` and fails clearly when `npm` is
  missing.
- `check-local.ps1` verifies local setup without starting servers or touching
  PostgreSQL.

The scripts do not create a unified Python lockfile, do not install unrelated
dev tools, and do not commit `.venv` or `node_modules`.

## Hygiene Checks

Before committing setup or startup changes, run:

```powershell
.\scripts\check\hygiene.ps1
```

For a staged-only pre-commit path and whitespace check:

```powershell
.\scripts\check\hygiene.ps1 -Staged
```

The hygiene script checks for accidental app gitlinks/submodules, nested `.git`
entries under `apps`, unsafe tracked files such as `.env`, `.secrets`, `.venv`,
`node_modules`, `work`, `output`, `products`, DB dumps/backups, raw provider
HTML captures, stale contract mirrors, stale generated web API types when
`apps/web/node_modules` exists, and `git diff --check` whitespace errors.

## Start Services

Use three separate PowerShell terminals from the repository root.

Terminal 1:

```powershell
.\scripts\dev\product-factory-api.ps1
```

Expected local target:

- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/health`

Terminal 2:

```powershell
.\scripts\dev\ecommerce-api.ps1
```

Expected local target:

- API: `http://127.0.0.1:8001`
- Health: `http://127.0.0.1:8001/api/health`
- DB status: `http://127.0.0.1:8001/api/price-monitoring/db/status`

Terminal 3:

```powershell
.\scripts\dev\web.ps1
```

Expected local target:

- Web UI: `http://127.0.0.1:5173`

## Proxy Routes

The web app keeps these browser routes stable:

- `/api` proxies to Product Factory API at `http://127.0.0.1:8000`.
- `/commerce-api` proxies to Ecommerce API at `http://127.0.0.1:8001` and is
  rewritten to backend `/api` routes.

Do not rename or repoint these routes for local startup.

## Database Not Ready

Ecommerce API can be running even when DB-backed workflows are not ready.
`http://127.0.0.1:8001/api/health` confirms the API process. Use
`http://127.0.0.1:8001/api/price-monitoring/db/status` for PostgreSQL setup,
migration, and catalog readiness.

PostgreSQL setup remains manual and explicit. The setup helpers do not create
users, create databases, apply migrations, import catalogs, mutate schema, or
change `ECOMMERCE_DATABASE_URL`.

Common DB-not-ready causes:

- `ECOMMERCE_DATABASE_URL` is missing.
- PostgreSQL is not running.
- The database/user or credentials are wrong.
- Migrations have not been applied with `alembic upgrade head`.
- The catalog has not been imported.

See [Ecommerce PostgreSQL Local Setup](ecommerce-postgresql-local.md) for the
database setup commands.
