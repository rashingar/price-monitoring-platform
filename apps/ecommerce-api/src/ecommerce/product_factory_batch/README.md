# Product Factory Batch Intake

This package implements the first CSV Batch Intake phase as a resolve-only backend flow.
It intentionally does not enqueue Product Factory jobs.

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

Next phase TODOs:

- `POST /api/product-factory-batches/{batch_id}/enqueue-selected`
- `POST /api/product-factory-batches/{batch_id}/rows/{row_id}/enqueue`

Those routes should enqueue only rows with reviewed or selected source URLs and must reuse the existing Product Factory full-pipeline execution behavior instead of adding a separate execution path.
