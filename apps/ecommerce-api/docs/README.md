# Ecommerce Backend Notes

Related docs:

- [API endpoints and contracts](api.md)

## Removed Marketplace Fetch

Marketplace fetch/search code has been removed. Price Monitoring must not
call marketplace MPN/search fallback or try to discover URLs during a run fetch.

New monitoring work must use existing active `source_urls`/`product_sources`.
Products without active source URLs are skipped with
`missing_active_source_url` and cannot be monitored until Find Source or an
import workflow promotes a reviewed active URL. URL discovery, candidate
review, and candidate promotion belong to Find Source / Source URL Agent. Source
URL capture,
diagnostics, and source health belong to Vendor Sources. Vendor Source Capture
has its own durable run history in `vendor_source_capture_runs`; it must not
reuse Price Monitoring run history.

## Database Setup

PostgreSQL is mandatory for Catalog and Price Monitoring workflows. `sourceCata.csv` is imported into PostgreSQL and is no longer read directly by Catalog or Price Monitoring selection. CSV/file editor, path, health, and artifact routes remain usable when no database is configured.

Set `ECOMMERCE_DATABASE_URL` before using Catalog browsing/import, Price Monitoring, alerts, observations, or history:

```text
postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce
```

Run Alembic migrations against that database before using the DB-backed endpoints:

```powershell
$env:ECOMMERCE_DATABASE_URL="postgresql+psycopg://ecommerce:ecommerce@127.0.0.1:5432/ecommerce"
alembic upgrade head
```

Import the active catalog:

```powershell
python -m ecommerce.jobs.ingest_catalog
```

Backfill known product source URLs after the active catalog is imported:

```powershell
python -m ecommerce.jobs.import_source_urls
python -m ecommerce.jobs.import_source_urls --apply
```

The importer defaults to dry-run mode. It reads DB `price_observations.product_url` and DB-referenced enriched CSV artifacts, resolves each URL to an active `catalog_products` row, and writes only when `--apply` is provided. Trusted DB observations with strong identity matches are imported as `active`. Older enriched CSV artifact URLs are imported as `needs_review` unless the artifact row exactly matches an active `catalog_source + model`, in which case they are imported as `active`.

Useful options:

```powershell
python -m ecommerce.jobs.import_source_urls --json
python -m ecommerce.jobs.import_source_urls --apply --catalog-source sourceCata
python -m ecommerce.jobs.import_source_urls --apply --observations
python -m ecommerce.jobs.import_source_urls --apply --artifacts
python -m ecommerce.jobs.import_source_urls --report-path output/source-url-import-report.json
```

The same import workflow is available through frontend-facing API endpoints:

```text
GET  /api/catalog/source-urls/summary
GET  /api/catalog/source-urls/import/options
POST /api/catalog/source-urls/import/preview
POST /api/catalog/source-urls/import/apply
POST /api/catalog/source-urls/import/product-factory/preview
POST /api/catalog/source-urls/import/product-factory/apply
```

`/import/preview` is a dry-run and returns counters plus capped candidate details without writing database rows. `/import/apply` uses the same importer and writes to `source_urls`; repeated apply calls are idempotent. Both endpoints accept `catalog_source`, `include_observations`, `include_artifacts`, `limit`, and `report_items_limit`.

Product Factory handoff API imports are limited to `ecommerce_source_handoff.json` files under allowed artifact roots or configured file editor roots. The public route path uses `/product-factory/`.

The summary endpoint reports active catalog coverage, including products with at least one active source URL, products still missing active source URLs, grouped status/source/type counts, and a coverage percentage. Use it to track import progress and review backlog.

Import Product Factory source URL handoff artifacts:

```powershell
python -m ecommerce.jobs.import_product_factory_handoff --file work\<model>\integrations\ecommerce_source_handoff.json --dry-run
python -m ecommerce.jobs.import_product_factory_handoff --file work\<model>\integrations\ecommerce_source_handoff.json --apply
```

The handoff importer resolves catalog identity without importing Product Factory code, writes active or needs-review `source_urls`, and uses the existing source convergence helpers for `product_sources`.

## Telegram Product Factory Intake

Ecommerce API exposes `POST /api/product-factory/telegram/webhook` for compact
Telegram Product Factory commands. The endpoint is disabled by default with
`PRODUCT_FACTORY_TELEGRAM_ENABLED=false`. Enable it only after setting
`PRODUCT_FACTORY_TELEGRAM_BOT_TOKEN`,
`PRODUCT_FACTORY_TELEGRAM_WEBHOOK_SECRET`,
`PRODUCT_FACTORY_TELEGRAM_ALLOWED_CHAT_IDS`, and
`PRODUCT_FACTORY_TELEGRAM_ALLOWED_USER_IDS`.

Accepted examples:

```text
012345
012345 B
012345 S
012345 B S
012345 B B
012345 S B
012345 B S B
012345 https://example.com/product
012345 B https://example.com/product
012345 S https://example.com/product
012345 B S https://example.com/product
012345 B B https://example.com/product
012345 S B https://example.com/product
012345 B S B https://example.com/product
```

The first token is always the 6-digit Product Factory model and leading zeros
are preserved. `B` before `S` enables BestPrice, `S` enables Skroutz, and a
trailing `B` after marketplace flags enables BoxNow. URLs are manual scrape
overrides and must be absolute `http` or `https`.

Marketplace/listing flags are independent from scrape-source selection.
`bestprice_enabled` and `skroutz_enabled` only affect Product Factory product
configuration.

With a manual URL, Ecommerce API looks up the product name from the CSV file at
`PRODUCT_FACTORY_WAREHOUSE_CATALOG_PATH` using
`PRODUCT_FACTORY_WAREHOUSE_CATALOG_MODEL_COLUMN` and
`PRODUCT_FACTORY_WAREHOUSE_CATALOG_NAME_COLUMN`, then calls Product Factory API
`POST /api/jobs/full-pipeline`. The Ecommerce database is not used for this
product-name lookup. Manual URLs bypass Brave/source resolution and set
`source_resolution.method=manual_url`.

Without a manual URL, Ecommerce API resolves a scrape source with Brave Search.
Search queries use the ERP warehouse product name and available metadata:
manufacturer, MPN, barcode, and category. Ranking is configured by
`config/product_factory_source_resolution.json` or the
`PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_PATH` override. The config contains
confidence thresholds, max suggestions, the pending-choice TTL, and preferred
source definitions with weights, domains, aliases, and product URL patterns.
The default config uses `minimum_confidence=70`, `suggestion_confidence=40`,
`max_suggestions=5`, and `pending_choice_ttl_minutes=15`.

High-confidence resolution echoes the selected source, Brave page title, URL,
and raw confidence before enqueueing the Product Factory job. If only
suggestion-confidence candidates exist, Telegram sends numbered inline buttons
for the candidates plus `Cancel`; no job is enqueued until the operator chooses
a candidate. Pending choices are stored server-side with the command flags,
warehouse identity, candidates, creation time, and expiry time. They expire
after 15 minutes by default. Expired or cancelled choices are deleted and never
enqueue.

Verify readiness from the repo root:

```powershell
python -m ecommerce.jobs.check_db_setup
```

Expected ready state for Catalog is `configured=true`, `reachable=true`, `required_tables_present=true`, `alembic_up_to_date=true`, and `ready_for_catalog=true`. Expected ready state for monitoring also requires `active_catalog_count > 0` and `ready_for_price_monitoring=true`.

To inspect the SQL without connecting to PostgreSQL:

```powershell
alembic upgrade head --sql
```

## Durable Ecommerce Jobs

`ecommerce_jobs` is the shared DB-backed job primitive for long Ecommerce
workflows. It stores job type, status, JSON payload/result, error message,
timestamps, heartbeat, attempts, and cancellation requests. It is intentionally
small and does not introduce Celery, Redis, RQ, or a scheduler.

Current statuses are `queued`, `running`, `succeeded`, `failed`, and
`cancelled`. New Vendor Sources capture, Source URL Agent, URL validation,
diagnostics, and Price Monitoring execution code should migrate onto this
primitive when durable inspection/cancellation is needed. Product Factory stays
separate and must not import these internals.

Operators can inspect and request cancellation through:

```text
GET  /api/jobs
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
```

The backend helper in `ecommerce.jobs.durable` includes synchronous execution
for API routes and tests. The durable worker command leases and executes queued
rows outside request handling:

```powershell
python -m ecommerce.jobs.worker --job-type catalog_update_from_opencart --poll-seconds 5 --limit 1
python -m ecommerce.jobs.worker --job-type catalog_update_from_opencart --once --dry-run
```

From the repository root, `.\scripts\dev\ecommerce-worker.ps1` runs the same
module through the root virtual environment. The worker preserves existing API
behavior: Dashboard `Update DB` can still run through a FastAPI background task,
while operators can run the worker for crash-resumable queued job execution.
Each worker pass marks stale `running` jobs older than
`--stale-running-after-minutes` as `failed` with an explanatory message before
claiming new queued jobs. `--dry-run` only reports matching stale and queued
jobs; it does not mutate state or run handlers.

OpenCart catalog update failures can write safe Playwright diagnostics under
`output/catalog_updates/{job_id}/diagnostics/`. Start with
`failure_context.json` for the failed step, redacted current URL, export
profile, timeout, browser mode, error class, and sanitized message. When a page
exists, `failure.png` is saved after credential fields are redacted. Runtime
`output/` folders are local artifacts and must not be committed.

## Testing Profiles

Codex prompts that touch only Ecommerce API backend files should prefer:

```powershell
.\scripts\test\codex-ecommerce.ps1
```

`.\scripts\test\fast.ps1` is Codex-safe aggregate fast verification for the
monorepo. Prefer `.\scripts\test\codex-ecommerce.ps1` for Ecommerce-only
patches because it is faster and narrower; root fast is appropriate when a
prompt touches multiple apps, shared contracts, or repo-wide test
infrastructure. Runtime tests are opt-in via
`.\scripts\test\ecommerce-runtime.ps1`; golden tests are deterministic fixture
regressions via `.\scripts\test\ecommerce-golden.ps1`. `db_integration`,
`postgres_required`, external, e2e, legacy, and full suites are manual unless
explicitly requested. Ecommerce DB fast coverage includes `db_contract` only.
Always run tests with verbose output so you can see whether a command is
hanging or simply taking longer.

Source capture and Vendor Sources coverage is split by profile. Parser,
scoring, sanitization, direct Skroutz endpoint, source selection, run-result,
and API response contracts use narrow golden JSON snapshots. Local source URL
and product source persistence contracts use `db_contract`. Runtime Vendor
Sources capture workflows, run history, artifact writing, scheduled capture,
and Price Monitoring capture handoff are opt-in and excluded from root fast.

## Price Monitoring Persistence

`catalog_products` stores the active imported catalog used by Catalog API browsing and Price Monitoring selection. It preserves `catalog_source + model`, MPN/name/manufacturer, raw and parsed category fields, quantity/status/marketplace flags, raw CSV row JSON, import metadata, and an `active` flag. Products missing from the latest import are marked inactive instead of hard-deleted.

`products` stores a lightweight internal product identity for the own catalog. Product identity is scoped by `catalog_source + model`; model is not globally unique. When model is missing, the backend can fall back to exact `catalog_source + mpn` matching.

`monitoring_runs` stores durable metadata for manual monitoring runs while preserving the existing local run folders and generated artifacts. New API-triggered monitoring runs are not created unless the database is ready.

`catalog_snapshots` stores the selected own catalog rows for a run, including model, MPN, name, own price, descriptive fields, and the raw row. `product_id` is nullable.

`price_observations` stores competitor/source prices parsed after a manual fetch, including model, MPN, product name, own price, competitor price, raw row, and match metadata.

`source_urls` stores known marketplace/source URLs for active catalog products. Source URLs can be backfilled from existing observations and enriched artifacts with `python -m ecommerce.jobs.import_source_urls` or through the source URL import API. This importer is conservative and idempotent: it does not create rows without a resolved `catalog_product_id`, preserves manual URLs, leaves disabled URLs disabled, and skips invalid or ambiguous candidates with counters and warnings. Imported URLs may be `active` or `needs_review` depending on match confidence.

`product_sources` and `source_capture_snapshots` store the newer shared capture path used by Product Factory initial capture, scheduled Ecommerce source capture, and legacy Product Factory artifact backfill. Product Factory backfill is best-effort: raw HTML and source JSON are preserved where discoverable, imported snapshots carry `captured_at`, `fetched_at`, `parsed_at`, `imported_at`, and `created_at`, and recovered observations set `timestamp_source` plus `timestamp_quality`.

`alert_rules` stores dashboard-only alert rules. The first supported rule type is `competitor_below_own_price`, which triggers when a competitor/source price is lower than the own catalog price. Rules target products in this priority order:

1. `product_id`
2. `catalog_source + model`
3. `catalog_source + mpn`

`alert_events` stores dashboard-visible events generated from price observations. Events are deduplicated per rule, product or fallback target, run, and source so re-evaluating the same run does not create duplicate rows. Event statuses are `open`, `acknowledged`, and `resolved`.

`product_id` is intentionally lightweight and nullable for the MVP. Observations are not rejected only because no product match is found.

Unmatched observations are included by default in observation API responses. Each observation includes `match_status`, `matched_by`, and `is_matched` so clients can show warning badges later.

Manual refetch of the same `run_id` replaces that run's previous observations instead of appending duplicates. `monitoring_runs.fetch_attempt` increments on each persisted fetch, and `last_was_refetch` is true when previous observations were replaced.

Old file-only Price Monitoring run folders are legacy artifacts and are ignored by active workflows. They are not migrated.

Price Monitoring selection preview and run creation report `source_url_coverage`. Each run requires exactly one `source`, `source_name`, `vendor_slug`, or `source_filter`; `all` is rejected for Price Monitoring. Only `status = "active"` counts as active coverage for that source/vendor. Missing active source URLs are hard eligibility exclusions for Price Monitoring, reported as `missing_active_source_url`.

Monitoring fetch uses stored active source URLs only. It calls Vendor Sources capture for the run's selected source/vendor, persists capture observations through the shared source capture/product source path with an `observation_batch_id`, and reports `fetch_input_mode = "source_urls"`.

Alerting is dashboard-only. There is no email, Slack, SMS, push, or webhook delivery. Frontend alert dashboard UI and scheduled monitoring profiles remain future work.
