# Testing Runbook

Run tests from `apps/product-factory-api/src` and always use the repo virtual environment. Do not use bare `python`, `py`, or a global interpreter.

## Fast Codex/local check

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q -m "not slow and not external and not legacy and not e2e"
```

Use this as the default Codex commit check. It runs unit tests, contract tests, and small isolated stage tests without full workflow e2e, live scraping, browser automation against live pages, OpenCart, OpenAI, credentials, or long subprocess workflows.

## Contract-only

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q -m contract
```

Use this when changing Product-Agent API routes, public response schemas, runtime service contracts, or deterministic artifact shapes. The backend OpenAPI snapshot is canonical for the Product-Agent API and lives at `docs/contracts/openapi.product-agent.json`.

Regenerate the OpenAPI snapshot from `apps/product-factory-api/src` after intentional backend API changes:

```powershell
..\.venv\Scripts\python.exe -m pipeline.jobs.export_openapi_snapshot
```

## Smoke-only

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q -m smoke
```

Smoke tests cover fast local API behavior through TestClient and temporary stores. They do not require the UI, OpenCart, OpenAI, live websites, PostgreSQL, credentials, browser automation, or browser execution.

## Full local suite

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q
```

Run this before larger merges or when changing shared runtime behavior that could affect slow regressions.

## Integration-only

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q -m "integration"
```

Use this for local filesystem/subprocess behavior, job child-process handling, and fixture workflows that are intentionally outside the default fast check.

## Stage-only examples

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q -m "filters"
..\.venv\Scripts\python.exe -m pytest -q -m "render"
..\.venv\Scripts\python.exe -m pytest -q -m "job_lifecycle"
```

Run affected-stage tests during development:

- Filter changes: run `filters` and relevant unit tests.
- Render changes: run `render` and contract tests.
- Job runner changes: run `job_lifecycle`; add `integration` when process handling changed.
- API changes: run `contract`.
- Source acquisition changes: run `source_acquisition`.
- Authoring artifact changes: run `authoring`.
- Publish handoff changes: run `publish`.

Filters Manager persistence changes should run both contract and filters selections:

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q -m "filters or contract"
```

The Filters Manager uses locked JSON persistence and returns a revision token. New clients can pass `expected_revision` on write requests; stale revisions return `409 Conflict`, while omitted revisions remain backward-compatible for current clients.

## Slow/external/e2e

```powershell
cd apps/product-factory-api/src
..\.venv\Scripts\python.exe -m pytest -q -m "slow or external or e2e"
```

Run this when validating broad workflow behavior, long taxonomy regressions, or any test intentionally excluded from the default fast profile. The default Codex check should not run full prepare/render/publish e2e.

All commands in this runbook must use `..\.venv\Scripts\python.exe` from `apps/product-factory-api/src`; do not use bare `python`, `py`, or a global interpreter.
