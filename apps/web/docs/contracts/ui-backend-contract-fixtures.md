# UI Backend Contract Fixtures

The UI test suite uses mocked Product-Agent and commerce API responses so contract assumptions and critical page rendering can be checked without running either backend. These tests do not start subprocesses, open browsers, call live sites, read real CSV files, or require PostgreSQL/OpenCart/OpenAI.

Fixtures live in:

- `src/test/fixtures/productAgentApi.ts`
- `src/test/fixtures/commerceApi.ts`

The strict fetch helper in `src/test/mockFetch.ts` maps request method plus path to fixture responses and fails on any unexpected request. Fixture drift should be treated as a signal to intentionally update either the backend contract or the UI normalization layer.

Backend OpenAPI snapshots remain canonical. The UI fixture checker normalizes `/commerce-api`
fixture paths to backend `/api` paths before comparing route coverage.

## Product-Agent Endpoints

- `GET /api/health`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/logs`
- `GET /api/jobs/{job_id}/artifacts`
- `GET /api/settings`
- `GET /api/filters/status`
- `GET /api/filters/categories`
- `GET /api/filters/categories/{category_id}`
- `PUT /api/filters/categories/{category_id}/groups`
- `PATCH /api/filters/categories/{category_id}/groups/{group_id}`
- `PUT /api/filters/categories/{category_id}/groups/{group_id}/values`
- `PATCH /api/filters/categories/{category_id}/groups/{group_id}/values/{value_id}`
- `POST /api/filters/sync`
- `GET /api/filters/sync-report`
- `GET /api/filter-review/{model}`
- `GET /api/authoring/{model}`

Filters Manager fixtures include the Product-Agent backend `revision` token on status,
category detail, write responses, and sync responses. The backend revision is the source
of truth for category writes. UI write request examples include `expected_revision`, and
the fixture/OpenAPI comparison checks that the backend request schemas still expose that
field for group/value add and update routes. A mocked 409 stale revision response is kept
for page tests; operators must reload the category before saving after that conflict.

## Commerce Endpoints

- `GET /commerce-api/health`
- `GET /commerce-api/catalog/summary`
- `GET /commerce-api/catalog/brands`
- `GET /commerce-api/catalog/category-hierarchy`
- `GET /commerce-api/catalog/products`
- `GET /commerce-api/price-monitoring/db/status`
- `GET /commerce-api/price-monitoring/runs`
- `GET /commerce-api/price-monitoring/runs/{run_id}`
- `GET /commerce-api/price-monitoring/runs/{run_id}/fetch`
- `GET /commerce-api/price-monitoring/runs/{run_id}/fetch/executions`
- `GET /commerce-api/price-monitoring/runs/{run_id}/fetch/logs`
- `GET /commerce-api/price-monitoring/runs/{run_id}/review`
- `GET /commerce-api/price-monitoring/alerts/rules`
- `GET /commerce-api/price-monitoring/alerts/events`
- `GET /commerce-api/artifacts/price-monitoring/runs/{run_id}`

Price Monitoring fixtures include DB-ready, DB-not-configured, DB-unreachable, and
missing-table/migration DB status payloads. `ready_for_price_monitoring: true` is the only
state that enables Price Monitoring workflows in the UI. Structured 503 fixtures are kept for
preview, create run, fetch, review, export, alert rules, alert events, and alert evaluation
routes; those errors indicate a Price Monitoring DB lock, not a full commerce backend outage.

Catalog fixtures include separate structured 503 database/import-required responses for summary,
brands, category hierarchy, and products. Those errors indicate a Catalog database/import lock,
not a full commerce backend outage and not a Price Monitoring DB lock. An empty successful
products fixture with an active-catalog-empty warning is also kept so the UI preserves import
warnings without converting them into generic empty search results.

CSV/Bridge, file, path, artifact, and general commerce health fixtures stay independent from
Price Monitoring DB readiness and Catalog database/import readiness. Price Monitoring
DB-not-ready fixtures set `non_db_workflows_available: true` to make that contract explicit.

## Updating Fixtures

When a backend contract intentionally changes, update the backend OpenAPI snapshot first, then
update the fixture payload, related client contract test, fixture/OpenAPI checker, and page smoke
assertion. Keep payloads small but realistic, including representative Greek catalog/filter
strings, leading-zero models, terminal and active statuses, Filters Manager revision tokens,
DB-ready and DB-not-ready examples, structured Price Monitoring 503 errors, structured Catalog
database/import 503 errors, artifacts, and alert data.

Later backend prompts will add OpenAPI snapshot export and snapshot checks in the backend repositories. Those checks should complement these UI fixtures rather than replace them.
