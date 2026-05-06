# Backend Contract Snapshots

The backend OpenAPI snapshot is the canonical API contract source for commerce and price-monitoring UI consumers.

Canonical snapshot:

```powershell
docs/contracts/openapi.ecommerce.json
```

Regenerate after an intentional backend API contract change:

```powershell
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.export_openapi_snapshot
```

Check contract tests:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -m contract
```

Fast local check:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -m "not slow and not external and not e2e and not legacy and not runtime"
```

Full local suite:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -vv -ra
```

Rules:

- Backend OpenAPI snapshots are canonical.
- UI mock fixtures are downstream consumers and should be updated only after an intentional backend contract change.
- Snapshot diffs must be reviewed, not blindly accepted.
- Fast contract tests must not require PostgreSQL, live websites, Playwright browser execution, OpenCart, OpenAI, Docker, or external network.
- Catalog and Price Monitoring route contracts may document database-required failures, but contract tests should use local fakes or SQLite/monkeypatched readiness rather than require a live PostgreSQL instance.
- Runtime tests are opt-in and cover fetch execution, source URL agent runs, vendor capture runs, subprocesses, database-heavy workflows, and long service orchestration.
- Golden tests are deterministic frozen input/output fixture regressions.
