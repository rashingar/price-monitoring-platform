# Current Architecture

The monorepo migration is complete. The repository is the current operating
home for Product Factory, Ecommerce API, the web console, shared contracts, and
root development scripts.

## Repository Layout

```text
apps/
  product-factory-api/
  ecommerce-api/
  web/
packages/
  contracts/
scripts/
  check/
  contracts/
  dev/
  setup/
  test/
docs/
  architecture/
  decisions/
  runbooks/
```

## Apps

`apps/product-factory-api` owns Product Factory workflows: product preparation,
source capture handoff, authoring, deterministic rendering, filter/category
review, validation, and OpenCart-ready CSV/image handoff. Its Python
project/install name is `product-factory`; its internal package is
`product_factory`.

`apps/ecommerce-api` owns catalog, source URLs, vendor sources, source capture,
price observations, monitoring runs, review actions, exports, alert rules, and
database migrations. Its internal Python package is `ecommerce`.

`apps/web` is the React/Vite operator console. It calls backend APIs through
explicit clients and keeps browser proxy routes stable:

- `/api` for Product Factory.
- `/commerce-api` for Ecommerce API.

The backend apps remain separate runtimes. Do not directly import one backend's
internals from the other backend or from the web app.

## Local Environment

The repo uses one root Python virtual environment at `.venv`. Root scripts and
direct backend commands should use `.\.venv\Scripts\python.exe` or installed
console scripts from that environment after editable app installs are complete.
App-local virtual environments are not part of the current operator setup.

The web app owns its own dependency install under `apps/web/node_modules`.
`node_modules` is required for web development, web tests, and generated API
type checks, but it is never committed.

## Contracts

`packages/contracts` mirrors the canonical app-local OpenAPI snapshots:

- `apps/product-factory-api/docs/contracts/openapi.product-factory.json`
- `apps/ecommerce-api/docs/contracts/openapi.ecommerce.json`

Run `.\scripts\contracts\check.ps1` to verify mirrors. After API contract
changes, regenerate the owning app snapshot, refresh the mirror when it changes,
then regenerate/check web API types.

## Generated Web Types

Generated web API type scaffolding lives under `apps/web/src/api/generated`.
These files are committed contract artifacts and are generated from
`packages/contracts`; do not edit them by hand.

The generated types are used for compile-time drift checks. The current runtime
fetch behavior remains in the existing manual web clients.

## Database Ownership

Ecommerce API owns PostgreSQL and all database migrations for catalog, source,
monitoring, alert, review, and export data.

Product Factory is artifact/file-backed for local product run state. Product
Factory must not write into Ecommerce API database tables directly. Any future
durable Product Factory database state needs an explicit architecture decision
for schema/database ownership.

## Artifact Policy

Generated runtime outputs are not source:

- `.venv/`
- `node_modules/`
- `work/`
- `output/`
- `runs/`
- `logs/`
- `products/`
- `__pycache__/`
- `.pytest_cache/`

Raw provider HTML captures, DB files, dumps, backups, secrets, `.env` files,
private keys, and generated product folders must stay out of Git. Committed
fixtures must be sanitized and intentionally placed under test or docs fixture
paths.

## Root Scripts

Root scripts preserve app boundaries while making local operations repeatable:

- `scripts/setup/*`: install local dependencies and run setup diagnostics.
- `scripts/dev/*`: start local app servers and run startup diagnostics.
- `scripts/test/*`: run verbose app test suites.
- `scripts/contracts/*`: check mirrors and generated web API types.
- `scripts/check/*`: run hygiene and aggregate checks.

Scripts use the root `.venv` for Python and fail clearly when dependencies are
missing. They do not silently install dependencies while running dev or test
commands.

## Test Policy

Use verbose test output. Operator broad fast verification should avoid live
external services, browser-live workflows, e2e product runs, and slow tests
unless the change needs that scope. Runtime tests are opt-in and excluded from
default fast backend checks.

Operator broad verification:

```powershell
.\scripts\check\hygiene.ps1
.\scripts\contracts\check.ps1
.\scripts\contracts\check-web-types.ps1
.\scripts\test\fast.ps1
```

Codex prompts should default to targeted checks relevant to changed files and
keep automated check runtime under 2 minutes. Codex must always run
`git diff --check` and `git status --short`, avoid broad suites unless the
operator explicitly requests them, and report useful broader verification under
`Manual verification needed`. See `docs/runbooks/codex-workflow.md`.

When `apps/web/node_modules` is missing, web type checks and web tests cannot
run until `.\scripts\setup\web.ps1` or `npm ci` has been run in `apps/web`.
