# Testing Runbook

Run tests with the root virtual environment after installing Product Factory
editable support. Do not use bare `python`, `py`, a global interpreter, or an
app-local virtual environment.

## Fast Codex/local check

```powershell
.\scripts\test\product-factory-api.ps1
```

Use this as the default Codex commit check. It runs unit tests, contract tests, and small isolated stage tests without full workflow e2e, live scraping, browser automation against live pages, OpenCart, OpenAI, credentials, or long subprocess workflows.

## Contract-only

```powershell
cd apps/product-factory-api
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m contract
```

Use this when changing Product Factory API routes, public response schemas, runtime service contracts, or deterministic artifact shapes. The backend OpenAPI snapshot is canonical for the Product Factory API and lives at `docs/contracts/openapi.product-factory.json`.

Regenerate the OpenAPI snapshot from `apps/product-factory-api` after intentional backend API changes:

```powershell
..\..\.venv\Scripts\python.exe -m product_factory.jobs.export_openapi_snapshot
```

## Smoke-only

```powershell
cd apps/product-factory-api
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m smoke
```

Smoke tests cover fast local API behavior through TestClient and temporary stores. They do not require the UI, OpenCart, OpenAI, live websites, PostgreSQL, credentials, browser automation, or browser execution.

## Full local suite

```powershell
cd apps/product-factory-api
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini
```

Run this before larger merges or when changing shared runtime behavior that could affect slow regressions.

## Integration-only

```powershell
cd apps/product-factory-api
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m "integration"
```

Use this for local filesystem/subprocess behavior, job child-process handling, and fixture workflows that are intentionally outside the default fast check.

## Stage-only examples

```powershell
cd apps/product-factory-api
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m "filters"
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m "render"
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m "job_lifecycle"
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
cd apps/product-factory-api
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m "filters or contract"
```

The Filters Manager uses locked JSON persistence and returns a revision token. Clients can pass `expected_revision` on write requests; stale revisions return `409 Conflict`, while omitted revisions are accepted by the current API.

## Slow/external/e2e

```powershell
cd apps/product-factory-api
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m "slow or external or e2e"
```

Run this when validating broad workflow behavior, long taxonomy regressions, or any test intentionally excluded from the default fast profile. The default Codex check should not run full prepare/render/publish e2e.

All commands in this runbook must use the root `.venv\Scripts\python.exe`;
root scripts expect Product Factory to be installed editable with
`.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps`.
