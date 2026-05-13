# Ecommerce Monitoring Service Boundaries

Price Monitoring FastAPI routes are thin HTTP adapters under
`ecommerce.api.routes_price_monitoring`. They parse request payloads, call
`ecommerce.price_monitoring.service` or `review_service`, and map domain/DB
errors to `HTTPException`.

Price Monitoring workflow code is split by responsibility:

- `run_payloads.py` owns API request models and request-to-domain mapping.
- `service.py` owns run selection, creation, DB-backed run payloads, and fetch
  execution orchestration.
- `review_service.py` owns review loading, action application, listing
  backfill responses, and price update export responses.
- `artifact_refs.py` owns persisted run artifact and DB status payload shapes.

Vendor Sources capture keeps `ecommerce.vendor_sources.capture` as a
compatibility import surface. Workflow code lives in `capture_service.py`,
payload serialization in `payloads.py`, and durable run row persistence in
`run_repository.py`. Durable capture runs are marked `failed` when exceptions
occur after the run row is created.

Product source persistence keeps public imports from
`db.product_source_repository` compatible, while capture persistence is split
into:

- `capture_persistence.py` for snapshots and top-level capture result writes.
- `observation_persistence.py` for price, offer, and listing rows.
- `source_health.py` for product source health updates.
