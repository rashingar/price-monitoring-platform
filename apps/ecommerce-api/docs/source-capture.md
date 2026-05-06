# Unified Source Capture

Vendor Sources owns first-class product source discovery, source URL review,
source URL capture, and source health. Price Monitoring calls Vendor Sources
capture services during fetch and requires existing active source URLs; it does
not discover URLs or fall back to marketplace MPN/search fetch.
Price Monitoring requires exactly one source/vendor per run. All-source capture
is retained only as an explicit admin diagnostic Vendor Sources operation.

The `/api/products/from-source` endpoint accepts a product model and one or more source URLs. It creates or reuses a canonical `products` row, stores each URL in `product_sources`, detects the vendor, and optionally runs the shared capture layer. Capture failures are persisted as source health diagnostics and do not roll back product/source creation.

The shared vendor capture implementation lives in `ecommerce.source_capture`:

- `canonicalize_url.py` normalizes URLs and strips common tracking parameters.
- `detect_vendor.py` maps vendor hosts to registered vendors.
- `runner.py` owns vendor capture strategy dispatch.
- `skroutz_xhr.py` captures Skroutz through direct `filter_products.json` and `shops_details.json` endpoints derived from the product URL.
- `parsing.py` contains normalized Electronet price and Skroutz direct JSON offer parsers.
- `scheduled.py` lets Vendor Sources refresh due `product_sources` without duplicating vendor logic.

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

Price Monitoring reports source URL coverage during selection and skips products
without active source URLs using `missing_active_source_url`. Products without
active source URLs are not eligible for Price Monitoring until Vendor Sources
discovers or imports a reviewed active URL.

## Removed Marketplace Fetch

Marketplace fetch/search code has been removed from Price Monitoring run fetch.
Monitoring work must use active `source_urls`/`product_sources`; Vendor Sources
owns URL discovery, candidate review, capture, and source health.

Product Factory source URL handoff artifacts can be imported directly from:

```powershell
python -m ecommerce.jobs.import_product_factory_handoff --file work\<model>\integrations\ecommerce_source_handoff.json --dry-run
python -m ecommerce.jobs.import_product_factory_handoff --file work\<model>\integrations\ecommerce_source_handoff.json --apply
```

The handoff importer resolves catalog identity by `catalog_product_id`, then model, then MPN. Ambiguous identity and invalid or unsupported URLs are reported without writes. Active source URLs are mirrored into `product_sources` through the normal convergence path, and initial price evidence can seed a source capture snapshot plus price observation.

Live smoke notes from 2026-05-03:

- Electronet direct HTML capture succeeded against a current Electronet product URL and parsed a price observation.
- Skroutz capture uses direct JSON endpoints only. Anti-bot/challenge responses from those endpoints are persisted as source health diagnostics instead of breaking product/source creation.
