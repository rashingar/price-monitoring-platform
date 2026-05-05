# Backend Contract Snapshots

The backend OpenAPI snapshot is the canonical API contract source for commerce and price-monitoring UI consumers.

Canonical snapshot:

```powershell
docs/contracts/openapi.pricefetcher.json
```

Regenerate after an intentional backend API contract change:

```powershell
python -m pricefetcher.jobs.export_openapi_snapshot
```

Check contract tests:

```powershell
python -m pytest -q -m contract
```

Fast local check:

```powershell
python -m pytest -q -m "not slow and not external"
```

Full local suite:

```powershell
python -m pytest -q
```

Rules:

- Backend OpenAPI snapshots are canonical.
- UI mock fixtures are downstream consumers and should be updated only after an intentional backend contract change.
- Snapshot diffs must be reviewed, not blindly accepted.
- Fast contract tests must not require PostgreSQL, live websites, Playwright browser execution, OpenCart, OpenAI, Docker, or external network.
- Catalog and Price Monitoring route contracts may document database-required failures, but contract tests should use local fakes or SQLite/monkeypatched readiness rather than require a live PostgreSQL instance.
