# Product Factory API

The Product Factory API is a local FastAPI backend for running and inspecting
Product Factory work from a UI or local client. It wraps the existing service
layer for prepare, render, publish, authoring, filter review, filter management,
and settings.

The API is repo-local. It does not start Docker, Redis, Celery, ecommerce-api,
web, or any other service.

## Start The API

Run this from the repo root through the root script after installing Product
Factory into the root virtual environment:

```powershell
.\scripts\dev\product-factory-api.ps1
```

The installed `product-factory-api` console script resolves to
`product_factory.dev.start:main`.

Check the service:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Local URLs:

- Base URL: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/api/health`
- Interactive docs: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

If a browser UI runs on a different local port, proxy `/api` to `http://127.0.0.1:8000` from the UI dev server or configure CORS for that local origin.

## Contract Source

The canonical API contract snapshot is:

```text
docs/contracts/openapi.product-factory.json
```

Route implementations live in `src/product_factory/api/routes_*.py`. Public request and response shapes live in `src/product_factory/api/schemas.py`.

Regenerate the OpenAPI snapshot from `apps/product-factory-api` after intentional route or schema changes:

```powershell
..\..\.venv\Scripts\python.exe -m product_factory.jobs.export_openapi_snapshot
```

Run contract tests from `apps/product-factory-api`:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -vv -ra -c src\pytest.ini -m contract
```

Snapshot diffs should be explained in commit notes. Contract coverage includes health, jobs, filters, filter review, authoring, and settings routes. Contract tests do not run full prepare/render/publish workflows.

## Runtime State

Job metadata is file-backed under `work/api/jobs/`:

- `work/api/jobs/{job_id}.json` stores the job record.
- `work/api/jobs/{job_id}.log` stores job lifecycle logs.
- `work/api/jobs/{job_id}.stdout.log` and `work/api/jobs/{job_id}.stderr.log` store captured child-process streams.

Jobs are queued and run in queue order. The default worker count is one active job at a time. If worker count is raised, jobs for the same trimmed/lowercase model are not allowed to run concurrently.

New job IDs are model-first (`{model}-{stage}-{suffix}`), so workflow screens can group prepare, render, and publish attempts by model. Use `GET /api/jobs/by-model/{model}` to open a model workflow history with the newest attempt first. Use `POST /api/jobs/{job_id}/retry` to enqueue the same payload again from a terminal job, including `full_pipeline` jobs.

Runtime knobs:

- `PRODUCT_FACTORY_MAX_JOB_WORKERS` controls job worker count and defaults to `1`.
- `PRODUCT_FACTORY_JOB_TERMINATE_TIMEOUT_SECONDS` controls graceful stop timeout and defaults to `30`.

Terminal job statuses:

- `succeeded`
- `failed`
- `cancelled`
- `killed`

## Endpoint Summary

Health:

- `GET /api/health`

Jobs:

- `POST /api/jobs/prepare`
- `POST /api/jobs/full-pipeline`
- `POST /api/jobs/render`
- `POST /api/jobs/publish`
- `POST /api/jobs/{job_id}/stop`
- `POST /api/jobs/{job_id}/retry`
- `GET /api/jobs`
- `GET /api/jobs/by-model/{model}`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/logs`
- `GET /api/jobs/{job_id}/artifacts`

Authoring:

- `GET /api/authoring/{model}`
- `POST /api/authoring/{model}/intro-text`
- `POST /api/authoring/{model}/intro-text/retry`
- `POST /api/authoring/{model}/seo-meta`
- `POST /api/authoring/{model}/seo-meta/retry`

Filter review:

- `GET /api/filter-review/{model}`
- `PUT /api/filter-review/{model}`
- `POST /api/filter-review/{model}/approve`

Filters manager:

- `GET /api/filters/categories`
- `GET /api/filters/categories/{category_id}`
- `PUT /api/filters/categories/{category_id}/groups`
- `PATCH /api/filters/categories/{category_id}/groups/{group_id}`
- `PUT /api/filters/categories/{category_id}/groups/{group_id}/values`
- `PATCH /api/filters/categories/{category_id}/groups/{group_id}/values/{value_id}`
- `GET /api/filters/status`
- `POST /api/filters/sync`
- `GET /api/filters/sync-report`
- `GET /api/filters/backups`
- `POST /api/filters/backups/restore`

Settings:

- `GET /api/settings`
- `PATCH /api/settings`

## Core Job Contracts

`POST /api/jobs/prepare` enqueues source capture and preparation work.

```json
{
  "model": "234385",
  "url": "https://www.example.com/product",
  "photos": 5,
  "sections": 0,
  "skroutz_status": 1,
  "boxnow": 0,
  "price": "798"
}
```

`POST /api/jobs/render` renders prepared artifacts for a model.

```json
{
  "model": "234385"
}
```

`POST /api/jobs/publish` starts the OpenCart publish phase for a model.

```json
{
  "model": "234385",
  "current_job_product_file": "products/234385.csv"
}
```

`POST /api/jobs/full-pipeline` enqueues the complete Product Factory pipeline for one model: prepare, intro text authoring, SEO meta authoring, render, and publish. The job stops at the first failed stage and records the failing stage in logs and terminal job metadata.

`source_url` is always the scraping source URL. `bestprice_enabled`, `skroutz_enabled`, and `boxnow_enabled` are product listing/configuration flags and do not choose or rewrite the scraping source.

```json
{
  "model": "234385",
  "product_name": "Example product",
  "source_url": "https://www.electronet.gr/example-product",
  "bestprice_enabled": false,
  "skroutz_enabled": true,
  "boxnow_enabled": false,
  "photos": 100,
  "sections": 20,
  "gallery_mode": "all",
  "trigger_source": "telegram",
  "telegram_chat_id": "123456789",
  "source_resolution": {
    "candidate_id": "source-candidate-id"
  }
}
```

Full-pipeline jobs, including Telegram-triggered jobs, default to `sections: 20`.
This is a maximum cap, not an exact required count: a source with fewer normal
presentation sections succeeds and extracts the available sections.

Full-pipeline jobs also default to `gallery_mode: "all"`, which downloads the
whole available gallery instead of treating `photos` as a cap. The `photos`
default remains numeric (`100`) because older prepare/render request models and
CSV accounting expect a numeric photo field; whole-gallery mode causes the
downloaded image count to drive the final OpenCart image list.

Manual `POST /api/jobs/prepare` defaults are unchanged (`photos: 1`,
`sections: 0`, no whole-gallery mode) unless the request explicitly sends
`gallery_mode: "all"`.

Skroutz gallery filtering is based on the actual gallery/source URL domain, not
on the `skroutz_enabled` listing flag. When the scraping URL is a Skroutz domain,
Product Factory skips the last extracted gallery image after extraction and
before final gallery ordering/deduplication output. This rule does not apply to
Electronet, BestPrice, or other non-Skroutz URLs, even when `skroutz_enabled` is
true.

`POST /api/jobs/{job_id}/stop` requests cancellation for a queued or running job.

```json
{
  "reason": "operator requested stop"
}
```

Job endpoints return `JobResponse`:

```json
{
  "job_id": "job-id",
  "job_type": "prepare",
  "status": "queued",
  "model": "234385",
  "created_at": "2026-05-03T09:00:00+00:00",
  "updated_at": "2026-05-03T09:00:00+00:00",
  "started_at": null,
  "finished_at": null,
  "message": null,
  "error": null,
  "error_code": null
}
```

## Authoring Contracts

Authoring endpoints inspect or generate the LLM-owned outputs under `work/{model}/llm/`:

- `intro_text.output.txt`
- `seo_meta.output.json`

The status response includes per-task output paths, validation state, word-count limits, trace paths, render readiness, render block reasons, and warnings.
For `intro_text`, word counts are based on visible text. Newly authored or re-authored intro artifacts may include limited safe `<strong>...</strong>` emphasis around verified facts; existing plain-text artifacts remain valid and are not migrated. The intro status also exposes emphasis diagnostics so clients can show a non-blocking warning when emphasis is missing, invalid, or overused.

## Filter Review Contracts

Filter review endpoints operate on prepared model artifacts and return the resolved category filters for review before render. Missing required filters are warnings, not render blockers. Saved reviewed values are applied by render even before approval, with a `category_filter_review_not_approved` warning until the review is approved.

`PUT /api/filter-review/{model}` accepts reviewed values, existing group rule updates, and optional new groups. Existing group updates can change `required` and `status`; values and rule updates are persisted through the global filter-map override layer.

## Filters Manager Contracts

The Filters Manager API persists global category filter edits through locked JSON writes. Backend writes update manual overrides and regenerate the effective filter map before returning.

Filter status, category detail, sync, and write responses include a `revision` token. Clients should send `expected_revision` on group/value write requests to prevent lost updates from overlapping edits. A stale `expected_revision` returns `409 Conflict` and does not modify manual overrides.

Valid filter statuses are:

- `active`
- `inactive`
- `deprecated`

## Settings Contracts

`GET /api/settings` returns the product-factory settings payload. `PATCH /api/settings` currently accepts these leaf paths:

- `authoring.intro_text.default.min_words`
- `authoring.intro_text.default.max_words`
- `authoring.intro_text.default.max_attempts`
- `authoring.intro_text.default.max_emphasized_words_percent`
- `authoring.seo_meta.default.meta_description_max_chars`

Unsupported patch paths return `422 Unprocessable Entity`.

## Error Shape

Most application errors use this shape:

```json
{
  "detail": "Error message"
}
```

FastAPI validation errors use the default FastAPI validation error shape.
