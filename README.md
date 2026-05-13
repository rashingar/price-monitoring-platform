# Price Monitoring Platform

Price Monitoring Platform is the local operator monorepo for:

- Product Factory product preparation and OpenCart export.
- Ecommerce catalog, source URL, capture, price monitoring, alerts, review, and
  export workflows.
- The React web console used by operators.

Most day-to-day work starts from the repository root in PowerShell. The main
exception is Alembic: Ecommerce migrations must be run from
`apps/ecommerce-api` because its `alembic.ini` uses app-relative paths.

## Operator Quick Start

For a new machine, run setup once from the repository root:

```powershell
.\scripts\setup\root-venv.ps1
.\scripts\setup\python-deps.ps1
.\scripts\setup\web.ps1
.\scripts\setup\check-local.ps1
```

For daily local work, start the three services in separate PowerShell windows:

```powershell
.\scripts\dev\product-factory-api.ps1
.\scripts\dev\ecommerce-api.ps1
.\scripts\dev\web.ps1
```

Open the operator console:

```text
http://127.0.0.1:5173
```

Useful health checks:

- Product Factory API: `http://127.0.0.1:8000/api/health`
- Ecommerce API: `http://127.0.0.1:8001/api/health`
- Ecommerce DB readiness:
  `http://127.0.0.1:8001/api/price-monitoring/db/status`

Before committing, run the check that matches your change:

```powershell
.\scripts\check\hygiene.ps1
.\scripts\test\codex-ecommerce.ps1
.\scripts\test\codex-product-factory.ps1
.\scripts\contracts\check-web-types.ps1
```

Use `.\scripts\test\fast.ps1` for a broader local smoke pass.

## App Map

- `apps/product-factory-api`: Product Factory backend for product preparation,
  source capture, authoring, rendering, category/filter review, and
  OpenCart-ready product exports. Python project/install name:
  `product-factory`. Internal Python package: `product_factory`.
- `apps/ecommerce-api`: Ecommerce API backend for catalog import, source URLs,
  source capture, price monitoring, alerts, review, exports, and database
  migrations. Internal Python package: `ecommerce`.
- `apps/web`: React/Vite operator console. Browser routes `/api` and
  `/commerce-api` are intentionally stable.
- `packages/contracts`: mirrored Product Factory and Ecommerce OpenAPI
  snapshots used for contract checks and generated web API type scaffolding.
- `scripts`: root setup, dev, test, contract, and hygiene orchestration.

The two Python APIs are separate runtimes. Do not merge Product Factory and
Ecommerce API code, packages, routes, or databases as part of local setup.

## Working Directory Rules

Use the repository root for setup, dev server scripts, contract scripts, web
commands, and most tests:

```powershell
.\scripts\dev\ecommerce-api.ps1
.\scripts\contracts\check-web-types.ps1
```

Use `apps/ecommerce-api` for Alembic:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

Running Alembic from the repository root with
`-c apps\ecommerce-api\alembic.ini` is not equivalent. The ini file contains
`script_location = migrations`, so from the root Alembic looks for a missing
root-level `migrations` folder.

## First Run

From the repository root in PowerShell:

```powershell
.\scripts\setup\root-venv.ps1
.\scripts\setup\python-deps.ps1
.\scripts\setup\web.ps1
.\scripts\setup\check-local.ps1
```

These scripts create the root `.venv` if needed, install both backend projects
into that root `.venv`, run `npm ci` in `apps/web`, and verify local setup
prerequisites. They do not create a unified Python lockfile, start servers,
mutate PostgreSQL, or commit generated dependency folders.

Manual equivalent:

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

## Local Prerequisites

- Windows PowerShell.
- Python 3.11 or newer. The `python` command must resolve to Python 3.11+.
- Native Windows PostgreSQL with `psql` on `PATH`.
- Node.js/npm for the web app.
- Playwright Chromium if you run browser-backed Product Factory workflows.

Docker is not required for the current local setup.

## Database Setup

Ecommerce API owns PostgreSQL state for catalog and price monitoring workflows.
Product Factory remains artifact/file-backed for local product runs.

Fresh local PostgreSQL setup:

```sql
CREATE USER ecommerce WITH PASSWORD 'ecommerce';
CREATE DATABASE ecommerce OWNER ecommerce;
GRANT ALL PRIVILEGES ON DATABASE ecommerce TO ecommerce;
```

PowerShell environment variable:

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

Dashboard can also refresh the active catalog from OpenCart. Configure these
private environment variables before using `Update DB`:

```powershell
$env:OPENCART_STORE_BASE = "https://your-store.example"
$env:OPENCART_ADMIN_PATH = "admin"
$env:OPENCART_ADMIN_USER = "your-admin-user"
$env:OPENCART_ADMIN_PASS = "your-admin-password"
$env:OPENCART_EXPORT_PROFILE = "sourceCata"
```

From the Dashboard, click `Update DB`. Ecommerce API creates a durable
`catalog_update_from_opencart` job, logs into OpenCart with Playwright, exports
the `sourceCata` CSV Product Export profile, runs `alembic upgrade head`, and
imports the downloaded CSV into PostgreSQL. Downloads are stored under
`output/catalog_updates/{job_id}/`; the preserved download filename remains in
that folder and the imported copy is normalized to
`output/catalog_updates/{job_id}/sourceCata.csv`.

Inspect job state with:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/catalog/update-db/latest
Invoke-RestMethod http://127.0.0.1:8001/api/jobs/{job_id}
```

Default tests mock OpenCart and Playwright. Live OpenCart export tests are
manual/opt-in only.

Verify database readiness:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.check_db_setup
```

If that command cannot import `ecommerce`, rerun:

```powershell
.\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps
```

See [Ecommerce PostgreSQL Local Setup](docs/runbooks/ecommerce-postgresql-local.md)
for backup, rename, and fresh-create procedures.

## Common Operator Tasks

Regenerate Ecommerce OpenAPI after an intentional API change:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.export_openapi_snapshot
Pop-Location
Copy-Item apps\ecommerce-api\docs\contracts\openapi.ecommerce.json packages\contracts\openapi.ecommerce.json
.\scripts\contracts\generate-web-types.ps1
.\scripts\contracts\check-web-types.ps1
```

Backfill normalized Price Monitoring listing rows from legacy offer
observations:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.backfill_price_observation_listings
Pop-Location
```

Backfill a single Price Monitoring run:

```powershell
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.backfill_price_observation_listings --run-id RUN_ID
Pop-Location
```

Run focused Price Monitoring checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -vv apps/ecommerce-api/tests/test_price_monitoring_review_export.py
Push-Location apps\ecommerce-api
..\..\.venv\Scripts\python.exe -m pytest -vv tests/test_price_monitoring_db.py tests/test_price_monitoring_db_policy.py
Pop-Location
```

## Start Commands

Run the local startup diagnostic:

```powershell
.\scripts\dev\check-local.ps1
```

Start each app in a separate PowerShell terminal:

```powershell
.\scripts\dev\product-factory-api.ps1
.\scripts\dev\ecommerce-api.ps1
.\scripts\dev\web.ps1
```

Local URLs:

- Web app: `http://127.0.0.1:5173`
- Product Factory API health: `http://127.0.0.1:8000/api/health`
- Product Factory API docs: `http://127.0.0.1:8000/docs`
- Ecommerce API health: `http://127.0.0.1:8001/api/health`
- Ecommerce API docs: `http://127.0.0.1:8001/docs`
- Ecommerce database status:
  `http://127.0.0.1:8001/api/price-monitoring/db/status`

The web dev proxy keeps browser routes stable:

- `/api` proxies to Product Factory at `http://127.0.0.1:8000`.
- `/commerce-api` proxies to Ecommerce API at `http://127.0.0.1:8001` and
  rewrites to backend `/api` routes.

Ecommerce API health is separate from database readiness. If DB-backed
workflows are not ready, check the database status URL for setup hints.

## Test And Check Commands

Run hygiene before committing:

```powershell
.\scripts\check\hygiene.ps1
```

For staged-only path and whitespace checks:

```powershell
.\scripts\check\hygiene.ps1 -Staged
```

Codex-safe aggregate fast verification:

```powershell
.\scripts\test\fast.ps1
```

`scripts\test\fast.ps1` first runs snapshot hygiene and fast marker hygiene,
then delegates to Product Factory fast, Ecommerce fast, web fast, and contract
mirror checks. It is Codex-safe because delegated app scripts exclude runtime,
Ecommerce `db_integration`, `postgres_required`, external, e2e, legacy, and
slow checks where applicable, and marker hygiene prevents those forbidden
profiles from leaking into root fast. Codex prompts should still prefer
targeted app checks relevant to changed files. Use
`.\scripts\test\codex-product-factory.ps1` for Product Factory-only backend
changes and `.\scripts\test\codex-ecommerce.ps1` for Ecommerce-only backend
changes. Full suites are manual unless explicitly requested.

App-specific and contract checks:

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

The test scripts use verbose output so you can see whether a check is hanging or
simply taking longer. Default fast paths exclude live external, e2e, slow,
legacy, runtime, Ecommerce `db_integration`, and PostgreSQL-required tests.
Runtime tests are opt-in; golden tests are deterministic fixture regressions and
reviewed contract artifacts, not auto-regenerated dumps. Snapshot expected files
must not be updated unless the prompt explicitly says
`Approve snapshot updates`.
Ecommerce DB tests are split into `db_contract`, `db_integration`, and
`postgres_required`; `db_contract` is allowed in fast/root-fast when local and
deterministic, while `db_integration` and `postgres_required` are opt-in. Python
backend pytest suites have a hard 60 second per-test timeout, and web Vitest
suites have a hard 10 second per-test timeout; tests that legitimately need
more time must explicitly override it and remain outside default fast where
appropriate. See [Testing Strategy](docs/runbooks/testing-strategy.md).

## Contracts And Generated Web Types

App-local OpenAPI snapshots are mirrored under `packages/contracts`. Check
mirrors with:

```powershell
.\scripts\contracts\check.ps1
```

After API contract changes, regenerate app-local snapshots from the owning app,
refresh the mirror if the app-local snapshot changed, then regenerate/check web
types:

```powershell
.\scripts\contracts\generate-web-types.ps1
.\scripts\contracts\check-web-types.ps1
```

Generated web API type files under `apps/web/src/api/generated` are committed
contract artifacts. Do not edit them by hand. Existing manual web clients remain
the runtime fetch implementation for now.

## Troubleshooting

`alembic upgrade head` says `Path doesn't exist: migrations`

- You are probably running Alembic from the repository root.
- Run it from `apps/ecommerce-api` with
  `..\..\.venv\Scripts\python.exe -m alembic upgrade head`.

Price Monitoring pages say the database is not ready

- Open `http://127.0.0.1:8001/api/price-monitoring/db/status`.
- Check `missing_tables`, `alembic_up_to_date`, and `blocking_reasons`.
- Apply migrations from `apps/ecommerce-api`, then recheck status.

OpenAPI contract checks fail

- Regenerate the owning app snapshot first.
- Copy the app-local snapshot into `packages/contracts`.
- Run `.\scripts\contracts\generate-web-types.ps1`.
- Run `.\scripts\contracts\check-web-types.ps1`.

Frontend type errors after backend response changes

- Update manual types in `apps/web/src/api/*Types.ts` when needed.
- Regenerate generated OpenAPI types; do not hand-edit
  `apps/web/src/api/generated/*.ts`.

## Artifact Policy

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

Do not commit `.env`, `.secrets`, credentials, tokens, local databases, DB
dumps/backups, raw provider HTML captures, generated product outputs, or private
keys. Use `.env.example` files only as safe templates.

## Current Docs

- [Current Architecture](docs/architecture/current-architecture.md)
- [Operator Startup](docs/runbooks/operator-startup.md)
- [Codex Workflow](docs/runbooks/codex-workflow.md)
- [Testing Strategy](docs/runbooks/testing-strategy.md)
- [Ecommerce PostgreSQL Local Setup](docs/runbooks/ecommerce-postgresql-local.md)
- [Contracts-First Integration](docs/decisions/0005-contracts-first-integration.md)

Historical records remain available at
[Monorepo Migration](docs/runbooks/monorepo-migration.md) and
[Target Architecture](docs/architecture/target-architecture.md), but current
operations should use the current architecture and runbooks above.
