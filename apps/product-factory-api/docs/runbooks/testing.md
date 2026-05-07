# Testing Runbook

Run tests with the root virtual environment after installing Product Factory
editable support. Do not use bare `python`, `py`, a global interpreter, or an
app-local virtual environment.

Always run tests with verbose output so you can see whether it is hanging or simply taking longer.

## Default Codex Check

```powershell
.\scripts\test\codex-product-factory.ps1
```

Use this as the default Codex check when a prompt touches only Product Factory
backend files. It runs Product Factory tests from `apps/product-factory-api`
and excludes tests marked `slow`, `external`, `legacy`, `e2e`, or `runtime`.

`.\scripts\test\fast.ps1` is Codex-safe aggregate fast verification for the
monorepo. App-specific Codex scripts are still preferred for single-app Product
Factory patches because they are faster and narrower. Root fast is appropriate
when a prompt touches multiple apps, shared contracts, or repo-wide test
infrastructure.

Full `pytest` is not the default Codex command. Do not run full
prepare/render/publish e2e, subprocess, browser, OpenCart, OpenAI, database, or
live network tests unless the prompt explicitly asks for that profile.

## Product Factory Broad Check

```powershell
.\scripts\test\product-factory-api.ps1
```

Use this for operator-requested Product Factory broad verification. It uses the
same fast exclusions as `.\scripts\test\codex-product-factory.ps1`.

## Contract-only

```powershell
.\scripts\test-contract.ps1
```

Use this when changing Product Factory API routes, public response schemas, runtime service contracts, or deterministic artifact shapes. The backend OpenAPI snapshot is canonical for the Product Factory API and lives at `docs/contracts/openapi.product-factory.json`.

Regenerate the OpenAPI snapshot from `apps/product-factory-api` after intentional backend API changes:

```powershell
..\..\.venv\Scripts\python.exe -m product_factory.jobs.export_openapi_snapshot
```

## Golden-only

```powershell
.\scripts\test\product-factory-golden.ps1
```

Golden tests are deterministic frozen input/output fixture regression tests.
They are useful when changing parser, taxonomy, render, or schema behavior that
should preserve known fixture output.

Skroutz golden coverage is kept narrow and deterministic. The old broad
prepare/render workflow fixture loop was replaced by parser, taxonomy, section
extraction, deterministic render-row, and validation JSON snapshots. These
tests use committed fixtures only and must not call live websites, browser
execution, OpenAI, OpenCart, or full workflow orchestration. Runtime/e2e
workflow coverage remains opt-in through the runtime profile.

## Runtime Profile

```powershell
.\scripts\test\product-factory-runtime.ps1
```

Runtime tests execute or simulate app runtime paths, subprocesses, workers,
process termination, browser/server/database/LLM calls, or full service
orchestration. Use this for job runner, worker, subprocess, process stop/kill,
or broad workflow behavior.

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

Run this only when explicitly requested for broad local verification or before
larger merges where the runtime cost is acceptable.

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
- Job runner changes: run `.\scripts\test\product-factory-runtime.ps1`.
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
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m "slow or external or e2e or runtime"
```

Run this when validating broad workflow behavior, long taxonomy regressions, or any test intentionally excluded from the default fast profile. The default Codex check should not run full prepare/render/publish e2e.

All commands in this runbook must use the root `.venv\Scripts\python.exe`;
root scripts expect Product Factory to be installed editable with
`.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps`.
