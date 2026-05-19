# Product Factory Batch Intake

This package implements the first CSV Batch Intake phase as a resolve-only backend flow.
It intentionally does not enqueue Product Factory jobs.

Next phase TODOs:

- `POST /api/product-factory-batches/{batch_id}/enqueue-selected`
- `POST /api/product-factory-batches/{batch_id}/rows/{row_id}/enqueue`

Those routes should enqueue only rows with reviewed or selected source URLs and must reuse the existing Product Factory full-pipeline execution behavior instead of adding a separate execution path.
