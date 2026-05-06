# Ecommerce API

This document is the human-readable API map for the Ecommerce backend. The
exact machine contract is the OpenAPI snapshot at
`docs/contracts/openapi.ecommerce.json`.

## Running The API

Start the local FastAPI service:

```powershell
ecommerce-api
```

Development entry point:

```powershell
python -m ecommerce.dev.start
```

Default base URL:

```text
http://127.0.0.1:8001
```

Interactive FastAPI docs are available at:

```text
http://127.0.0.1:8001/docs
```

## Contract Source

Canonical OpenAPI snapshot:

```text
docs/contracts/openapi.ecommerce.json
```

Regenerate after an intentional API shape change:

```powershell
..\..\.venv\Scripts\python.exe -m ecommerce.jobs.export_openapi_snapshot
```

Run contract tests:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -m contract
```

Rules for API changes:

- Treat the OpenAPI snapshot as the backend contract source.
- Review snapshot diffs before accepting them.
- Keep frontend mocks and fixtures downstream of the backend contract.
- Contract tests should stay local and should not require PostgreSQL, live
  websites, Playwright browser execution, Docker, OpenCart, or external network.
- Run runtime and full suites only when explicitly requested. Runtime tests are
  opt-in; golden tests are deterministic fixture regressions.

## Runtime Boundaries

Catalog, Price Monitoring, observations, history, and alerts require a
configured, reachable, migrated PostgreSQL database.

These routes are useful without PostgreSQL:

- `GET /api/health`
- bridge routes
- safe CSV file routes
- paths and artifact diagnostics
- artifact preview and download for files under allowed roots

Safe filesystem access is intentionally root-limited. Browser clients should
use API-provided `read_url` and `download_url` values instead of opening local
paths directly.

Important environment variables:

```text
ECOMMERCE_DATABASE_URL
ECOMMERCE_ARTIFACT_ROOTS
ECOMMERCE_FILE_ROOTS
ECOMMERCE_PRICE_IGNORE_PATH
ECOMMERCE_SOURCE_CATA_PATH
ECOMMERCE_MAX_FETCH_WORKERS
ECOMMERCE_FETCH_STALE_AFTER_MINUTES
ECOMMERCE_SUBPROCESS_TERMINATE_TIMEOUT_SECONDS
```

## Endpoint Map

### Health

```text
GET /api/health
```

Returns a lightweight service health payload. This endpoint does not require
catalog files, artifact folders, or PostgreSQL.

### Bridge

```text
POST /api/bridge/run
```

Runs the local OpenCart stock bridge and writes bridge artifacts. Request body:

```json
{
  "opencart_export_path": "C:\\Exports\\export_2026-04-28.csv",
  "stock_csv_path": null,
  "output_dir": null
}
```

When `output_dir` is empty, artifacts are written under
`output/ecommerce/bridge/runs/{run_id}`.

### Paths And Artifacts

```text
GET /api/paths/roots
GET /api/artifacts/roots
GET /api/artifacts/bridge/runs/{run_id}
GET /api/artifacts/price-monitoring/runs/{run_id}
GET /api/artifacts/read
GET /api/artifacts/download
```

Artifact listing responses include access metadata such as `is_allowed`,
`can_read`, `can_download`, `read_url`, `download_url`, and `warning`.
Read and download endpoints accept a `path` query parameter.

### Safe CSV Files

```text
GET  /api/files/roots
GET  /api/files/list
POST /api/files/read
POST /api/files/save
POST /api/files/save-copy
```

Read request:

```json
{
  "path": "C:\\Users\\user\\Downloads\\sourceCata.csv",
  "delimiter": null,
  "max_rows": 1000
}
```

Save-copy request:

```json
{
  "source_path": "C:\\Users\\user\\Downloads\\sourceCata.csv",
  "target_path": "C:\\Users\\user\\Downloads\\sourceCata_edited.csv",
  "columns": ["model", "mpn", "name"],
  "rows": [
    {"model": "005606", "mpn": "ABC123", "name": "Product name"}
  ],
  "delimiter": ","
}
```

CSV values are treated as strings so identifiers such as `005606` keep leading
zeroes.

### Catalog

```text
GET /api/catalog/products
GET /api/catalog/categories
GET /api/catalog/category-hierarchy
GET /api/catalog/brands
GET /api/catalog/summary
```

The Catalog API reads from PostgreSQL `catalog_products`. `sourceCata.csv` is an
import input, not the runtime read source.

Product filtering supports text search, manufacturer, marketplace, automation
eligibility, raw serialized category, and parsed category hierarchy filters.
Ignored products are excluded by default unless requested.

### Catalog Source URLs

```text
GET   /api/catalog/products/{catalog_product_id}/source-urls
POST  /api/catalog/products/{catalog_product_id}/source-urls
PATCH /api/catalog/source-urls/{source_url_id}
POST  /api/catalog/source-urls/{source_url_id}/validate
```

Manual source URLs attach to a catalog product. Known domains infer source names
such as `skroutz`, `bestprice`, `public`, `kotsovolos`, and `plaisio`.

### Source URL Import

```text
GET  /api/catalog/source-urls/summary
GET  /api/catalog/source-urls/import/options
POST /api/catalog/source-urls/import/preview
POST /api/catalog/source-urls/import/apply
POST /api/catalog/source-urls/import/product-factory/preview
POST /api/catalog/source-urls/import/product-factory/apply
```

Preview is a dry-run. Apply writes resolved candidates into `source_urls` and is
intended to be idempotent.

Product Factory handoff import accepts `ecommerce_source_handoff.json` files
only from allowed artifact roots or configured file editor roots. The canonical
route path uses `/product-factory/`.

### Vendor Sources

```text
GET   /api/vendor-sources/sources
GET   /api/vendor-sources/source-urls/summary
GET   /api/vendor-sources/source-health
POST  /api/vendor-sources/captures/runs
GET   /api/vendor-sources/captures/runs
GET   /api/vendor-sources/captures/runs/{run_id}
GET   /api/vendor-sources/captures/runs/{run_id}/artifacts
POST  /api/vendor-sources/agent/runs
GET   /api/vendor-sources/agent/runs
GET   /api/vendor-sources/agent/runs/{run_id}
GET   /api/vendor-sources/agent/runs/{run_id}/artifacts
GET   /api/vendor-sources/candidates
GET   /api/vendor-sources/candidates/{candidate_id}
PATCH /api/vendor-sources/candidates/{candidate_id}/review
GET   /api/vendor-sources/candidates/review-layout
PUT   /api/vendor-sources/candidates/review-layout
POST  /api/vendor-sources/candidates/review-layout/reset
```

This namespace is the direct-vendor workflow surface. Use Vendor Sources
directly for discovery runs, candidate review, capture, and source health.
`GET /api/vendor-sources/sources` returns discovery and capture capabilities so
clients can distinguish marketplace monitoring sources from direct vendor
sources and avoid assuming capture support for discovery-only vendors.
Vendor Sources owns source URL capture and health through
`POST /api/vendor-sources/captures/runs`. Vendor Source Capture history is
stored separately from Price Monitoring run history.

### Product Ignore

```text
GET    /api/ignore/products
POST   /api/ignore/products
DELETE /api/ignore/products/{model}
```

Create or update request:

```json
{
  "model": "005606",
  "name": "Product name",
  "manufacturer": "Bosch",
  "mpn": "MPN-1",
  "reason": "do not price monitor",
  "notes": ""
}
```

Ignore entries are product-level and keyed by six-digit atomic `model`.

### Price Monitoring Selection And Runs

```text
POST /api/price-monitoring/selection/preview
POST /api/price-monitoring/runs
GET  /api/price-monitoring/runs
GET  /api/price-monitoring/runs/{run_id}
GET  /api/price-monitoring/db/status
```

Selection request:

```json
{
  "source": "skroutz",
  "source_name": null,
  "vendor_slug": null,
  "source_filter": null,
  "filters": {
    "q": null,
    "category": null,
    "family": null,
    "category_name": null,
    "sub_category": null,
    "manufacturer": "Bosch",
    "marketplace": null,
    "has_mpn": true,
    "atomic_only": true,
    "automation_eligible_only": true
  },
  "selected_models": [],
  "excluded_models": [],
  "include_ignored": false,
  "dry_run": false
}
```

Run creation writes `input.csv` and `selection_summary.json` under
`output/ecommerce/monitoring/runs/{run_id}` and records durable run metadata in
PostgreSQL. Price Monitoring requires active source URLs. Products without an
active source URL are skipped with `missing_active_source_url`; run creation
returns `400` when no selected product remains eligible. Each run must specify
exactly one source/vendor with `source`, `source_name`, `vendor_slug`, or
`source_filter`; `all` is rejected for Price Monitoring. Valid sources include
stored Vendor Sources such as `skroutz`, `bestprice`, or `electronet`.

### Price Monitoring Fetch Execution

```text
POST /api/price-monitoring/runs/{run_id}/fetch
GET  /api/price-monitoring/runs/{run_id}/fetch
GET  /api/price-monitoring/runs/{run_id}/fetch/logs
POST /api/price-monitoring/runs/{run_id}/fetch/cancel
GET  /api/price-monitoring/runs/{run_id}/fetch/executions
GET  /api/price-monitoring/runs/{run_id}/fetch/{execution_id}
GET  /api/price-monitoring/runs/{run_id}/fetch/{execution_id}/logs
POST /api/price-monitoring/runs/{run_id}/fetch/{execution_id}/cancel
```

Start request:

```json
{
  "source": null,
  "catalog_url": null
}
```

Fetch work is subprocess-backed and returns quickly with HTTP `202 Accepted`.
Execution statuses are `queued`, `running`, `succeeded`, `failed`, `cancelled`,
and `killed`.

Price Monitoring fetch uses stored source URLs only. It calls Vendor Sources
capture for the run's selected active URLs, reports `fetch_input_mode:
"source_urls"`, and persists the Vendor Sources `observation_batch_id`. The old
marketplace MPN/search fetch implementation has been removed.

### Observations, History, Review, And Export

```text
GET  /api/price-monitoring/observations
GET  /api/price-monitoring/runs/{run_id}/observations
GET  /api/price-monitoring/runs/{run_id}/catalog-snapshot
GET  /api/price-monitoring/products/by-model/{model}/price-history
GET  /api/price-monitoring/products/{product_id}/price-history
GET  /api/price-monitoring/runs/{run_id}/review
POST /api/price-monitoring/runs/{run_id}/review/actions
POST /api/price-monitoring/runs/{run_id}/export-price-update
```

Review action request:

```json
{
  "enriched_csv_path": null,
  "actions": [
    {"model": "005606", "selected_action": "undercut", "undercut_amount": 1.0},
    {"model": "123456", "selected_action": "ignore", "reason": "manual ignore from price review"}
  ]
}
```

Export request:

```json
{
  "review_csv_path": null,
  "output_path": null
}
```

The price update export contains only `model,price` rows for valid reviewed
updates.

### Alerts

```text
GET  /api/price-monitoring/alerts/rules
POST /api/price-monitoring/alerts/rules
GET  /api/price-monitoring/alerts/rules/{rule_id}
PATCH /api/price-monitoring/alerts/rules/{rule_id}
POST /api/price-monitoring/alerts/rules/{rule_id}/deactivate
GET  /api/price-monitoring/alerts/events
POST /api/price-monitoring/alerts/events/{event_id}/acknowledge
POST /api/price-monitoring/alerts/events/{event_id}/resolve
POST /api/price-monitoring/alerts/evaluate/{run_id}
```

The first supported alert rule type is `competitor_below_own_price`. Alerts are
dashboard-visible database records; notification delivery is outside this
backend.

### Source Capture And Product Source Helpers

```text
POST /api/products/from-source
```

`POST /api/products/from-source` supports product source creation for known
source URLs. Capture callers should use
`POST /api/vendor-sources/captures/runs`. See [source-capture.md](source-capture.md)
for current behavior and boundaries.
