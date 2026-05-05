# Product Factory API Contracts

The backend OpenAPI snapshot is the canonical Product Factory API contract. See `docs/api.md` for endpoint groups, request/response summaries, runtime state, and local API startup.

Snapshot path:

```text
docs/contracts/openapi.product-factory.json
```

Prepare also emits a file-based source URL evidence contract for ecommerce-api:

```text
work/{model}/integrations/ecommerce_source_handoff.json
```

See `docs/contracts/ecommerce-api-source-handoff.md`. Product Factory writes this artifact; ecommerce-api owns importing it and persisting any database records.

Regenerate from `apps/product-factory-api`:

```powershell
..\..\.venv\Scripts\python.exe -m pipeline.jobs.export_openapi_snapshot
```

Run contract tests from `apps/product-factory-api`:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m contract
```

Fast local check from repo root:

```powershell
.\scripts\test\product-factory-api.ps1
```

Full suite from `apps/product-factory-api`:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini
```

Snapshot diffs should be explained in commit output. There is no separate manual approval gate; the contract change is made explicit by the snapshot diff, backend tests, and commit notes.

Current Product Factory contract coverage includes health, jobs, filters, filter review, authoring, and settings routes. Contract tests are intentionally fast and do not run full prepare/render/publish workflows.

## Filters Manager Persistence

The Filters Manager API persists global category filter edits through locked JSON writes. Backend write operations take a short-lived lock beside `filter_map.manual_overrides.json`, reload the latest filter maps inside the lock, write manual overrides, and regenerate the effective filter map before returning.

Filter status, category detail, sync, and write responses include a `revision` token. Clients should send `expected_revision` on group/value write requests to prevent lost updates from concurrent tabs or overlapping calls. When it is stale, the backend returns `409 Conflict` and does not modify manual overrides.

Future UI edit forms should read the latest category/status revision and submit it as `expected_revision` with each save.
