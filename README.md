# Price Monitoring Platform

Price Monitoring Platform is a monorepo for product creation, ecommerce catalog
and price monitoring, and the operator console that coordinates those workflows.

## Apps

Current app folders:

- `apps/product-factory-api`: Product Factory backend runtime.
- `apps/ecommerce-api`: Ecommerce catalog and monitoring backend runtime.
- `apps/web`: React/Vite/TypeScript operator console frontend.

These are separate runtimes. The monorepo coordinates source code,
documentation, scripts, and contracts, but the two Python APIs are not merged
and the web app remains UI-only.

`apps/product-factory-api/src` contains the old Product-Agent Python pipeline.
The internal Python package remains `pipeline`.

`apps/ecommerce-api` owns ecommerce catalog, source URL, source capture, price
monitoring, review/export, alert, and database migration workflows. Its
internal Python package is `src/ecommerce`.

## Architecture

- [Target architecture](docs/architecture/target-architecture.md)
- [0001: Monorepo with Separate Apps](docs/decisions/0001-monorepo-with-separate-apps.md)
- [0002: App Naming and Domain Boundaries](docs/decisions/0002-app-naming-and-domain-boundaries.md)
- [0003: Database Ownership](docs/decisions/0003-database-ownership.md)
- [0004: Staged Package Renames](docs/decisions/0004-staged-package-renames.md)
- [0005: Contracts-First Integration](docs/decisions/0005-contracts-first-integration.md)
- [Monorepo migration runbook](docs/runbooks/monorepo-migration.md)

## Migration Status

The mechanical app folder migration is complete. Root helper scripts live under
`scripts/`, and mirrored OpenAPI snapshots live under `packages/contracts`.
Generated clients, Dockerization, worker changes, database ownership changes,
and Product Factory package renames remain out of scope for this migration.

## Local Setup

Python tooling uses one monorepo virtual environment at the repository root:

```powershell
py -3.13 -m venv .venv
```

Install Python dependencies into that root `.venv` from the app-specific
requirements files you need. Dependency setup is still app-aware and manual for
now; there is no unified Python package layout or monorepo lockfile yet.
Product Factory still keeps the internal `pipeline` package under
`apps/product-factory-api/src`, and ecommerce-api still keeps the internal
`ecommerce` package under `apps/ecommerce-api/src`.

Root scripts fail clearly when `.venv\Scripts\python.exe` is missing. Web
scripts run from `apps/web` and fail clearly when `node_modules` is missing;
use `npm ci` in `apps/web` to install frontend dependencies.

Generated runtime outputs stay out of Git, including `work/`, `output/`,
`runs/`, `logs/`, and `products/`. Raw scraped marketplace, vendor, or provider
HTML captures must not be committed; future examples should be sanitized under
`docs/examples` or `tests/fixtures`, not under generated output folders.
