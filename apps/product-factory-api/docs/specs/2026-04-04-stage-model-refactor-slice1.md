# Stage Model Refactor Slice 1

Date: 2026-04-04

## Scope

This slice establishes an explicit internal `source_acquisition -> prepare` boundary without changing the public CLI or downstream output contracts.

Public runtime behavior remains:
- `python -m pipeline.workflow prepare ...`
- `python -m pipeline.workflow render --model ...`

Compatibility constraints remain:
- scrape artifacts stay under `work/{model}/scrape/`
- render, publish, media upload, and catalog import behavior do not change
- taxonomy, schema, filter/category support, HTML structure, and CSV contracts do not change

## Stage Ownership

Internal stage flow for the current `prepare` command:

`interface -> initialize -> source_acquisition -> prepare`

Ownership in this slice:

- `interface`
  - CLI entrypoints in `pipeline.workflow`
- `initialize`
  - request parsing, defaults, validation, model-dir/bootstrap setup
- `source_acquisition`
  - source detection
  - provider resolution/bootstrap
  - fetch
  - raw snapshot provenance
  - provider parse/normalize into the shared `ParsedProduct` shape
  - plain gallery acquisition
  - acquisition warnings/provenance
- `prepare`
  - taxonomy resolution
  - manufacturer enrichment
  - section/Besco preparation
  - schema matching
  - deterministic prepared-context assembly
  - scrape compatibility artifact persistence

Later stages remain unchanged in this slice:

`authoring -> render -> publish -> media_upload -> catalog_import`

## Contract

`pipeline.source_acquisition_models.SourceAcquisitionResult` is the stage handoff object for the front block.

It intentionally carries only acquisition-owned outputs:

- `model_dir`
- `source`
- `provider_id`
- `fetch`
- `parsed`
- `extracted_gallery_count`
- `requested_gallery_photos`
- `downloaded_gallery`
- `gallery_warnings`
- `gallery_files`
- `snapshot_provenance`

It intentionally does not embed `CLIInput`.

Request-owned state such as `model`, `url`, `photos`, `sections`, `skroutz_status`, `boxnow`, and `price` stays outside the acquisition result and is passed explicitly by `prepare`.

## Implementation Notes

- `pipeline.source_acquisition_stage.execute_source_acquisition_stage(...)` now owns the full acquisition front block.
- `pipeline.prepare_stage.execute_prepare_stage(...)` remains the public internal prepare entrypoint.
- `pipeline.prepare_stage.execute_prepare_from_acquisition(...)` starts the prepare stage from a prebuilt `SourceAcquisitionResult`.
- `prepare` still returns the same downstream-facing result shape as before this slice. Acquisition provenance is kept inside the stage seam rather than widening the prepare-stage return contract.

## Tests

This slice adds focused regression coverage for:

- `SourceAcquisitionResult` carrying only acquisition-owned fields
- acquisition-stage provenance and gallery behavior
- `prepare` starting from a prebuilt acquisition result
- unchanged prepare result shape for downstream callers
