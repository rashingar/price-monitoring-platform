# Product Agent UI

Product Agent UI is a React, Vite, and TypeScript dashboard for operators working with
the local Product-Agent and commerce price-fetcher services.

The UI does not run backend jobs itself. It sends requests to the Product-Agent API for
prepare, render, publish, authoring, and filter-review workflows, and to the commerce API
for catalog browsing, source URL management, CSV bridge work, price monitoring, execution
history, and alerts.

## What It Provides

- A dashboard for checking Product-Agent and commerce service health.
- Prepare, render, publish, and job detail pages for Product-Agent workflows.
- A staged Product-Agent workflow page for authoring, filter review, settings, render, and
  publish operations.
- A Filters Manager for category filter groups and values.
- A commerce catalog browser with source URL management and source URL import review.
- A CSV bridge workspace for backend-approved CSV files and bridge runs.
- Price Monitoring workflow, execution history, review actions, export, and alert pages.

This is a UI-only repository. Product-Agent job execution, commerce catalog imports,
PostgreSQL migrations, price fetching, and OpenCart-related logic stay in their backend
repositories.

## Setup

Prerequisites:

- Node.js and npm. Node.js 22 is the recommended local version for this repo.
- Product-Agent API running at `http://127.0.0.1:8000`.
- Commerce price-fetcher API running at `http://127.0.0.1:8001`.
- PostgreSQL, current backend migrations, and an active imported catalog for Catalog and
  Price Monitoring workflows.

From this repository:

```powershell
npm ci
Copy-Item .env.example .env
npm run dev
```

Open the UI at:

```text
http://127.0.0.1:5173
```

The default `.env.example` keeps browser API base URLs empty and uses Vite proxies:

```bash
VITE_API_BASE_URL=
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
VITE_COMMERCE_API_BASE_URL=
VITE_COMMERCE_API_PROXY_TARGET=http://127.0.0.1:8001
```

With this setup:

- Browser requests to `/api` are proxied to the Product-Agent API.
- Browser requests to `/commerce-api` are proxied to the commerce API and rewritten to
  `/api` on that backend.
- Set `VITE_API_BASE_URL` or `VITE_COMMERCE_API_BASE_URL` only when the browser should call
  a backend directly and that backend is configured for CORS.

## Common Commands

```powershell
npm run dev
npm run build
npm run preview
npm run test:fast
```

Useful targeted checks:

```powershell
npm run test:contracts
npm run test:smoke
npm run test:fixture-contracts
```

`test:fast` runs the mocked API client contract tests and page smoke tests. These tests do
not require either backend to be running.

## Repo Map

- `src/api`: API clients, response normalization, and shared API types.
- `src/pages`: route-level operator pages.
- `src/components`: reusable UI components and workflow panels.
- `src/hooks`: shared React hooks for jobs, state persistence, and pipeline actions.
- `src/test`: mocked API fixtures, contract tests, and smoke tests.
- `docs/api.md`: API endpoints, payload contracts, proxy behavior, and readiness contracts.
- `docs/contracts/ui-backend-contract-fixtures.md`: fixture contract policy.
- `docs/runbooks/testing.md`: testing runbook.
- `docs/legacy.md`: archived setup and historical behavior notes moved out of the README.

## Operational Notes

Catalog and Price Monitoring depend on PostgreSQL and an active imported catalog. When those
backend requirements are missing, the UI shows locked states for the affected workflows while
keeping unrelated workflows, such as CSV Bridge and artifact browsing, usable when their
commerce endpoints are available.

Price Monitoring export produces a CSV file only. The UI does not update OpenCart directly.

No authentication, websocket transport, batch upload, Redux, Zustand, or React Query is
included in this repo.
