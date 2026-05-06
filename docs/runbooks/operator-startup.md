# Operator Startup

This runbook verifies the local monorepo startup flow without changing backend
routes, frontend browser routes, package names, or database schema.

## Preflight

From the repository root:

```powershell
.\scripts\dev\check-local.ps1
```

The diagnostic checks the root `.venv`, Product Factory import, Ecommerce API
import, web `node_modules`, mirrored contracts, and generated web API type
freshness when `node_modules` exists. It does not start servers and does not
mutate the database.

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

Common DB-not-ready causes:

- `ECOMMERCE_DATABASE_URL` is missing.
- PostgreSQL is not running.
- The database/user or credentials are wrong.
- Migrations have not been applied with `alembic upgrade head`.
- The catalog has not been imported.

See [Ecommerce PostgreSQL Local Setup](ecommerce-postgresql-local.md) for the
database setup commands.
