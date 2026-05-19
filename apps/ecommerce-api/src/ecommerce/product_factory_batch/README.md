# Product Factory Batch Intake

This package implements CSV Batch Intake for Product Factory source URL
resolution and manual Product Factory job enqueue.

Resolution is started asynchronously through FastAPI background tasks. The
request commits `status=resolving` and selected source metadata before the
background worker starts. The worker commits each row after marking it
`resolving_source` and again after storing candidates/status, so the UI can poll
`GET /api/product-factory-batches/{batch_id}/rows` for live progress.

Supported search sources remain fixed to:

- `skroutz`
- `bestprice`
- `electronet`

`POST /api/product-factory-batches/{batch_id}/resolve` accepts optional
`source_names`. Omitting it preserves the default all-source behavior. Selected
sources are persisted in batch metadata as `selected_source_names`,
`selected_source_labels`, and `source_selection_updated_at`.

The operator workflow is:

1. `Resolve URLs`
2. Review or override rows that need operator judgment.
3. `Enqueue selected` or enqueue one eligible row.
4. `Refresh PF statuses` to update Product Factory job state.

Enqueue remains manual. URL resolution never starts Product Factory jobs by
itself.

Rows are enqueueable only when they have a selected URL and are either:

- `manually_selected`
- `auto_selected` with confidence greater than or equal to
  `PRODUCT_FACTORY_BATCH_AUTO_ENQUEUE_CONFIDENCE_THRESHOLD`

The default auto-selected enqueue threshold is `85`. Invalid environment values
fall back to `85`; accepted values are integers in the range `1..100`.

Before any enqueue request starts Product Factory jobs, the backend normalizes
low-confidence `auto_selected` rows into `needs_review`. It preserves their
selected URL, source, confidence, and candidates for operator visibility, and
marks selection metadata with `auto_selected_below_enqueue_threshold`. These
rows must be manually reviewed or overridden before enqueue.

The enqueue routes reuse the existing Product Factory full-pipeline API:

- `POST /api/product-factory-batches/{batch_id}/enqueue-selected`
- `POST /api/product-factory-batches/{batch_id}/rows/{row_id}/enqueue`
- `POST /api/product-factory-batches/{batch_id}/refresh-job-statuses`
