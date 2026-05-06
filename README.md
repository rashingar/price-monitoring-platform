# Price Monitoring Platform

Price Monitoring Platform is the local operator monorepo for Product Factory,
Ecommerce API, and the web console. It contains the three app runtimes, mirrored
API contracts, generated web API type artifacts, and root setup/dev/check
scripts used for day-to-day local operation.

Monorepo migration is complete. New work should start from current
architecture, current contracts, and current operator runbooks.

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

See [Ecommerce PostgreSQL Local Setup](docs/runbooks/ecommerce-postgresql-local.md)
for backup, rename, and fresh-create procedures.

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

Operator broad fast verification:

```powershell
.\scripts\test\fast.ps1
```

`scripts\test\fast.ps1` is the human/operator broad fast verification command.
Codex prompts should prefer targeted app checks relevant to changed files and
keep automated checks under 2 minutes. Use
`.\scripts\test\codex-product-factory.ps1` for Product Factory-only backend
changes and `.\scripts\test\codex-ecommerce.ps1` for Ecommerce-only backend
changes. Broader checks are manual unless explicitly requested.

App-specific and contract checks:

```powershell
.\scripts\test\product-factory-api.ps1
.\scripts\test\ecommerce-api.ps1
.\scripts\test\product-factory-runtime.ps1
.\scripts\test\product-factory-golden.ps1
.\scripts\test\ecommerce-runtime.ps1
.\scripts\test\ecommerce-golden.ps1
.\scripts\test\web.ps1
.\scripts\contracts\check.ps1
.\scripts\contracts\check-web-types.ps1
.\scripts\check\all.ps1
```

The test scripts use verbose output and exclude live external, e2e, slow,
legacy, and runtime tests from the default fast path. Runtime tests are opt-in;
golden tests are deterministic fixture regressions. See
[Testing Strategy](docs/runbooks/testing-strategy.md).

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
