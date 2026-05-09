# Unified Source Capture

Find Source / Source URL Agent owns product source discovery, source URL
candidate review, and candidate promotion. Vendor Sources owns source URL
capture, diagnostics, source health, and capture run history. Price Monitoring
calls Vendor Sources capture services during fetch and requires existing active
source URLs; it does not discover URLs or fall back to marketplace MPN/search
fetch.
Price Monitoring requires exactly one source/vendor per run. All-source capture
is retained only as an explicit admin diagnostic Vendor Sources operation.

The `/api/products/from-source` endpoint accepts a product model and one or more source URLs. It creates or reuses a canonical `products` row, stores each URL in `product_sources`, detects the vendor, and optionally runs the shared capture layer. Capture failures are persisted as source health diagnostics and do not roll back product/source creation.

The shared vendor capture implementation lives in `ecommerce.source_capture`:

- `canonicalize_url.py` normalizes URLs and strips common tracking parameters.
- `detect_vendor.py` maps vendor hosts to registered vendors.
- `runner.py` owns vendor capture strategy dispatch.
- `skroutz_xhr.py` captures Skroutz through direct `filter_products.json` and `shops_details.json` endpoints derived from the product URL.
- `skroutz_network_diagnostic.py` is an operator-triggered browser network diagnostic for Skroutz product pages.
- `parsing.py` contains normalized Electronet price and Skroutz direct JSON offer parsers.
- `scheduled.py` lets Vendor Sources refresh due `product_sources` without duplicating vendor logic.

Testing is split by profile. Parser, scoring, sanitization, direct Skroutz
endpoint, selection, run-result, and API response behavior uses small golden
JSON snapshots under `tests/fixtures/golden_snapshots/`. Local source URL and
product source persistence uses `db_contract` tests. Runtime Vendor Sources
capture workflows, run history, artifact writing, scheduled capture, and Price
Monitoring capture handoff are opt-in and must not be part of root fast.

The DB-backed selected source URL capture service lives in
`ecommerce.vendor_sources.capture`.

Current vendors are seeded in `vendors`: `electronet`, `skroutz`, `plaisio`, `public`, and `kotsovolos`. Electronet and Skroutz are active. Plaisio, Public, and Kotsovolos are scaffolded for future parsers.

Raw capture records are stored in `source_capture_snapshots`. Request and response metadata is sanitized; cookies, auth headers, CSRF/session tokens, and fingerprinting-sensitive headers are not persisted. Price and offer observations are append-only and reference the snapshot that produced them.

Product Factory can hand off initial capture to this API by setting `ECOMMERCE_API_BASE_URL`, for example `http://127.0.0.1:8001`. Product Factory treats failures as warnings so product preparation does not fail because source capture failed.

Recurring capture is available through:

- API: `POST /api/vendor-sources/captures/runs`
- API: `GET /api/vendor-sources/captures/runs`
- API: `GET /api/vendor-sources/captures/runs/{run_id}`
- API: `GET /api/vendor-sources/captures/runs/{run_id}/artifacts`
- CLI: `ecommerce capture-sources`

Vendor Source Capture runs are stored in `vendor_source_capture_runs`, separate
from `monitoring_runs` and `price_monitoring_runs` workflow state. Capture runs
select active `source_urls` and active `product_sources`, excluding broken,
disabled, needs-review, and redirected URLs. Each capture run has one
`observation_batch_id`; by default it is the capture `run_id`, and price/offer
observations created by that run share the same batch id. The canonical capture
route is `POST /api/vendor-sources/captures/runs`.

Vendor Sources exposes source URL coverage and source health through:

- `GET /api/vendor-sources/source-urls/summary`
- `GET /api/vendor-sources/source-health`

Skroutz browser network diagnostics are available for active Skroutz source URLs:

- API: `POST /api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network`
- API: `GET /api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network/latest`
- CLI: `python apps/ecommerce-api/tools/probe_skroutz_network.py --url "https://www.skroutz.gr/s/65005733/xiaomi-poco-m8-5g-dual-sim-8-256gb-prasino.html" --output work/skroutz_65005733_network.json`

This is an admin diagnostic workflow only. It launches Chromium with Playwright,
opens the operator-provided Skroutz product URL, captures JSON/XHR/fetch-like
responses, classifies likely product/offer endpoints, and compares browser
observations with the currently derived `filter_products.json` and
`shops_details.json` URLs. It does not replace direct JSON production capture,
does not run from scheduled monitoring, does not create price observations, and
does not mutate source capture strategy.

Persisted reports store sanitized endpoint summaries only: method, sanitized
URL, status, resource type, content type, body size, JSON key summaries,
classification, derived-endpoint match, capped body sample, and parse errors.
The workflow never persists request headers, cookies, auth headers, CSRF/session
tokens, fingerprint-sensitive headers, or full unbounded response bodies.
Operators can launch the diagnostic from Find Source for a
linked Skroutz source URL and then inspect whether `filter_products.json`,
`shops_details.json`, another product-data endpoint, or a block/challenge was
observed.

Price Monitoring reports source URL coverage during selection and skips products
without active source URLs using `missing_active_source_url`. Products without
active source URLs are not eligible for Price Monitoring until Find Source or
an import workflow promotes a reviewed active URL.

## Removed Marketplace Fetch

Marketplace fetch/search code has been removed from Price Monitoring run fetch.
Monitoring work must use active `source_urls`/`product_sources`; Vendor Sources
owns capture and source health, while Find Source owns URL discovery and
candidate review.

Product Factory source URL handoff artifacts can be imported directly from:

```powershell
python -m ecommerce.jobs.import_product_factory_handoff --file work\<model>\integrations\ecommerce_source_handoff.json --dry-run
python -m ecommerce.jobs.import_product_factory_handoff --file work\<model>\integrations\ecommerce_source_handoff.json --apply
```

The handoff importer resolves catalog identity by `catalog_product_id`, then model, then MPN. Ambiguous identity and invalid or unsupported URLs are reported without writes. Active source URLs are mirrored into `product_sources` through the normal convergence path, and initial price evidence can seed a source capture snapshot plus price observation.

Live smoke notes from 2026-05-03:

- Electronet direct HTML capture succeeded against a current Electronet product URL and parsed a price observation.
- Skroutz capture uses direct JSON endpoints only. Anti-bot/challenge responses from those endpoints are persisted as source health diagnostics instead of breaking product/source creation.
