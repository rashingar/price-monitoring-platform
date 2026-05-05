# PriceFetcher Backend Notes

Related docs:

- [API endpoints and contracts](api.md)

## Deprecated Legacy Marketplace Fetch

Legacy marketplace fetch/search code has been removed. Price Monitoring must not
call marketplace MPN/search fallback or try to discover URLs during a run fetch.

New monitoring work must use existing active `source_urls`/`product_sources`.
Products without active source URLs are skipped with
`missing_active_source_url` and cannot be monitored until Vendor Sources
discovers, imports, or reviews an active URL. URL discovery, source URL review,
source URL capture, and source health belong to Vendor Sources. Vendor Source
Capture has its own durable run history in `vendor_source_capture_runs`; it must
not reuse Price Monitoring run history.

## Database Setup

PostgreSQL is mandatory for Catalog and Price Monitoring workflows. `sourceCata.csv` is imported into PostgreSQL and is no longer read directly by Catalog or Price Monitoring selection. Bridge, CSV/file editor, path, health, and artifact routes remain usable when no database is configured.

Set `PRICEFETCHER_DATABASE_URL` before using Catalog browsing/import, Price Monitoring, alerts, observations, or history:

```text
postgresql+psycopg://pricefetcher:pricefetcher@127.0.0.1:5432/pricefetcher
```

Run Alembic migrations against that database before using the DB-backed endpoints:

```powershell
$env:PRICEFETCHER_DATABASE_URL="postgresql+psycopg://pricefetcher:pricefetcher@127.0.0.1:5432/pricefetcher"
alembic upgrade head
```

Import the active catalog:

```powershell
python -m pricefetcher.jobs.ingest_catalog
```

Backfill known product source URLs after the active catalog is imported:

```powershell
python -m pricefetcher.jobs.import_source_urls
python -m pricefetcher.jobs.import_source_urls --apply
```

The importer defaults to dry-run mode. It reads DB `price_observations.product_url` and DB-referenced enriched CSV artifacts, resolves each URL to an active `catalog_products` row, and writes only when `--apply` is provided. Trusted DB observations with strong identity matches are imported as `active`. Older enriched CSV artifact URLs are imported as `needs_review` unless the artifact row exactly matches an active `catalog_source + model`, in which case they are imported as `active`.

Useful options:

```powershell
python -m pricefetcher.jobs.import_source_urls --json
python -m pricefetcher.jobs.import_source_urls --apply --catalog-source sourceCata
python -m pricefetcher.jobs.import_source_urls --apply --observations
python -m pricefetcher.jobs.import_source_urls --apply --artifacts
python -m pricefetcher.jobs.import_source_urls --legacy-runs-dir output/price_monitoring/runs
python -m pricefetcher.jobs.import_source_urls --report-path output/source-url-import-report.json
```

The same import workflow is available through frontend-facing API endpoints:

```text
GET  /api/catalog/source-urls/summary
GET  /api/catalog/source-urls/import/options
POST /api/catalog/source-urls/import/preview
POST /api/catalog/source-urls/import/apply
POST /api/catalog/source-urls/import/product-agent/preview
POST /api/catalog/source-urls/import/product-agent/apply
```

`/import/preview` is a dry-run and returns counters plus capped candidate details without writing database rows. `/import/apply` uses the same importer and writes to `source_urls`; repeated apply calls are idempotent. Both endpoints accept `catalog_source`, `include_observations`, `include_artifacts`, `include_legacy_runs`, `legacy_runs_dir`, `limit`, and `report_items_limit`. Legacy run scanning is disabled by default and only accepts artifact-root paths.

Product-Agent handoff API imports are limited to `price_fetcher_source_handoff.json` files under allowed artifact roots or configured file editor roots.

The summary endpoint reports active catalog coverage, including products with at least one active source URL, products still missing active source URLs, grouped status/source/type counts, and a coverage percentage. Use it to track import progress and review backlog.

Backfill Product-Agent scrape artifacts into first-class source capture snapshots:

```powershell
python -m pricefetcher.jobs.import_product_agent_artifacts --root ..\Product-Agent\work
python -m pricefetcher.jobs.import_product_agent_artifacts --root ..\Product-Agent\work --apply
```

The importer scans `work\<model>\scrape\<model>.source.json`, sibling `.report.json`, and `.raw.html` files. It creates or reuses `products` and `product_sources`, stores a sanitized raw `source_capture_snapshots` row, and only creates a `price_observations` row when the Product-Agent price diagnostics are strong enough. Re-running the importer skips snapshots with the same artifact reference and content hash. Use `PRICEFETCHER_PRODUCT_AGENT_WORK_ROOT` or `--root` to point at a different Product-Agent work folder.

Import Product-Agent source URL handoff artifacts:

```powershell
python -m pricefetcher.jobs.import_product_agent_handoff --file work\<model>\integrations\price_fetcher_source_handoff.json --dry-run
python -m pricefetcher.jobs.import_product_agent_handoff --file work\<model>\integrations\price_fetcher_source_handoff.json --apply
```

The handoff importer resolves catalog identity without importing Product-Agent code, writes active or needs-review `source_urls`, and uses the existing source convergence helpers for `product_sources`.

Verify readiness from the repo root:

```powershell
python -m pricefetcher.jobs.check_db_setup
```

Expected ready state for Catalog is `configured=true`, `reachable=true`, `required_tables_present=true`, `alembic_up_to_date=true`, and `ready_for_catalog=true`. Expected ready state for monitoring also requires `active_catalog_count > 0` and `ready_for_price_monitoring=true`.

To inspect the SQL without connecting to PostgreSQL:

```powershell
alembic upgrade head --sql
```

## Price Monitoring Persistence

`catalog_products` stores the active imported catalog used by Catalog API browsing and Price Monitoring selection. It preserves `catalog_source + model`, MPN/name/manufacturer, raw and parsed category fields, quantity/status/marketplace flags, raw CSV row JSON, import metadata, and an `active` flag. Products missing from the latest import are marked inactive instead of hard-deleted.

`products` stores a lightweight internal product identity for the own catalog. Product identity is scoped by `catalog_source + model`; model is not globally unique. When model is missing, the backend can fall back to exact `catalog_source + mpn` matching.

`monitoring_runs` stores durable metadata for manual monitoring runs while preserving the existing local run folders and generated artifacts. New API-triggered monitoring runs are not created unless the database is ready.

`catalog_snapshots` stores the selected own catalog rows for a run, including model, MPN, name, own price, descriptive fields, and the raw row. `product_id` is nullable.

`price_observations` stores competitor/source prices parsed after a manual fetch, including model, MPN, product name, own price, competitor price, raw row, and match metadata.

`source_urls` stores known marketplace/source URLs for active catalog products. Source URLs can be backfilled from existing observations and enriched artifacts with `python -m pricefetcher.jobs.import_source_urls` or through the source URL import API. This importer is conservative and idempotent: it does not create rows without a resolved `catalog_product_id`, preserves manual URLs, leaves disabled URLs disabled, and skips invalid or ambiguous candidates with counters and warnings. Imported URLs may be `active` or `needs_review` depending on match confidence.

`product_sources` and `source_capture_snapshots` store the newer shared capture path used by Product-Agent initial capture, scheduled PriceFetcher source capture, and Product-Agent artifact backfill. Product-Agent backfill is best-effort: raw HTML and source JSON are preserved where discoverable, imported snapshots carry `captured_at`, `fetched_at`, `parsed_at`, `imported_at`, and `created_at`, and recovered observations set `timestamp_source` plus `timestamp_quality`.

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

Monitoring fetch uses stored active source URLs only. It calls Vendor Sources capture for the run's selected source/vendor, persists capture observations through the shared source capture/product source path with an `observation_batch_id`, and reports `fetch_input_mode = "source_urls"` with `legacy_marketplace_fetch_used = false`.

Alerting is dashboard-only. There is no email, Slack, SMS, push, or webhook delivery. Frontend alert dashboard UI and scheduled monitoring profiles remain future work.
