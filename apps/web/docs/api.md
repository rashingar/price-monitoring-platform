# API Reference

This UI talks to two local HTTP services:

- Product Factory API through browser path `/api`.
- Commerce ecommerce-api API through browser path `/commerce-api`.

During local Vite development, `/api` proxies to `VITE_API_PROXY_TARGET` and
`/commerce-api` proxies to `VITE_COMMERCE_API_PROXY_TARGET`. The commerce proxy rewrites
`/commerce-api/...` to `/api/...` on the backend.

The TypeScript contract references are:

- Product Factory types: `src/api/types.ts`
- Commerce types: `src/api/commerceTypes.ts`
- Product Factory client: `src/api/client.ts`
- Commerce client: `src/api/commerceClient.ts`
- Generated OpenAPI type scaffolding: `src/api/generated`
- Fixture contract notes: `docs/contracts/ui-backend-contract-fixtures.md`

The generated files in `src/api/generated` are refreshed from mirrored OpenAPI
contracts with `.\scripts\contracts\generate-web-types.ps1` from the repository
root and checked with `.\scripts\contracts\check-web-types.ps1`. They are
committed source-facing contract artifacts and should not be manually edited.
Selected aliases in `src/api/types.ts` and `src/api/commerceTypes.ts` consume
generated schema types for compile-time drift checks. The manual clients listed
above remain the runtime clients for now, and generated clients are not used for
fetch behavior.

## Product Factory API

Regenerate this generated section from the OpenAPI mirror:

```powershell
Push-Location apps\web
npm run generate:api-docs
Pop-Location
```

Check that the generated docs are current:

```powershell
Push-Location apps\web
npm run check:api-docs
Pop-Location
```

<!-- product-factory-api:generated:start -->
Generated from `packages/contracts/openapi.product-factory.json`.

| Method | Browser path | Request body | Success response |
| --- | --- | --- | --- |
| GET | `/api/authoring/{model}` | - | `AuthoringStatusResponse` |
| POST | `/api/authoring/{model}/intro-text` | - | `JobResponse` |
| POST | `/api/authoring/{model}/intro-text/retry` | - | `JobResponse` |
| POST | `/api/authoring/{model}/seo-meta` | - | `JobResponse` |
| POST | `/api/authoring/{model}/seo-meta/retry` | - | `JobResponse` |
| GET | `/api/filter-review/{model}` | - | `FilterReviewResponse` |
| PUT | `/api/filter-review/{model}` | `FilterReviewUpdateRequest` | `FilterReviewResponse` |
| POST | `/api/filter-review/{model}/approve` | - | `FilterReviewResponse` |
| GET | `/api/filters/backups` | - | `FilterBackupsResponse` |
| POST | `/api/filters/backups/restore` | `RestoreFilterBackupRequest` | `FilterBackupRestoreResponse` |
| GET | `/api/filters/categories` | - | `FilterCategoriesResponse` |
| GET | `/api/filters/categories/{category_id}` | - | `FilterCategoryResponse` |
| PUT | `/api/filters/categories/{category_id}/groups` | `AddFilterGroupRequest` | `FilterCategoryResponse` |
| PATCH | `/api/filters/categories/{category_id}/groups/{group_id}` | `UpdateFilterGroupRequest` | `FilterCategoryResponse` |
| PUT | `/api/filters/categories/{category_id}/groups/{group_id}/values` | `AddFilterValueRequest` | `FilterCategoryResponse` |
| PATCH | `/api/filters/categories/{category_id}/groups/{group_id}/values/{value_id}` | `UpdateFilterValueRequest` | `FilterCategoryResponse` |
| GET | `/api/filters/status` | - | `FilterStatusResponse` |
| POST | `/api/filters/sync` | - | `FilterSyncResponse` |
| GET | `/api/filters/sync-report` | - | `FilterSyncReportResponse` |
| GET | `/api/health` | - | `HealthResponse` |
| GET | `/api/jobs` | - | `JobListResponse` |
| GET | `/api/jobs/{job_id}` | - | `JobResponse` |
| GET | `/api/jobs/{job_id}/artifacts` | - | `JobArtifactsResponse` |
| GET | `/api/jobs/{job_id}/logs` | - | `JobLogsResponse` |
| POST | `/api/jobs/{job_id}/retry` | - | `JobResponse` |
| POST | `/api/jobs/{job_id}/stop` | - | `JobResponse` |
| POST | `/api/jobs/authoring/intro-text` | `AuthoringIntroJobRequest` | `JobResponse` |
| POST | `/api/jobs/authoring/seo-meta` | `AuthoringSeoJobRequest` | `JobResponse` |
| GET | `/api/jobs/by-model/{model}` | - | `JobListResponse` |
| POST | `/api/jobs/prepare` | `PrepareJobRequest` | `JobResponse` |
| POST | `/api/jobs/publish` | `PublishJobRequest` | `JobResponse` |
| POST | `/api/jobs/render` | `RenderJobRequest` | `JobResponse` |
| GET | `/api/settings` | - | `SettingsResponse` |
| PATCH | `/api/settings` | `SettingsPatchRequest` | `SettingsResponse` |

## Product Factory Request Schemas

### PrepareJobRequest

```ts
{
  boxnow?: number; // default: 0
  characteristics_url?: string | null;
  gallery_url?: string | null;
  model: string;
  photos?: number; // default: 1
  price?: string | number; // default: 0
  second_opencart_image_index?: number | null;
  sections?: number; // default: 0
  skroutz_status?: number; // default: 0
  url: string;
}
```

### AddFilterGroupRequest

```ts
{
  expected_revision?: string | null;
  name: string;
  required?: boolean; // default: true
  status?: "active" | "inactive" | "deprecated"; // default: "active"
}
```

### AddFilterValueRequest

```ts
{
  expected_revision?: string | null;
  status?: "active" | "inactive" | "deprecated"; // default: "active"
  value: string;
}
```

### AuthoringIntroJobRequest

```ts
{
  model: string;
  retry?: boolean; // default: false
}
```

### AuthoringSeoJobRequest

```ts
{
  model: string;
  retry?: boolean; // default: false
}
```

### FilterReviewUpdateRequest

```ts
{
  add_new_values_globally?: boolean; // default: true
  group_updates?: FilterReviewGroupUpdate[];
  new_groups?: FilterReviewNewGroup[];
  values?: FilterReviewValueUpdate[];
}
```

### PublishJobRequest

```ts
{
  current_job_product_file?: string | null;
  model: string;
}
```

### RenderJobRequest

```ts
{
  model: string;
}
```

### RestoreFilterBackupRequest

```ts
{
  backup_name?: string | null;
}
```

### SettingsPatchRequest

```ts
{
  authoring?: object;
}
```

### UpdateFilterGroupRequest

```ts
{
  expected_revision?: string | null;
  name?: string | null;
  required?: boolean | null;
  status?: "active" | "inactive" | "deprecated" | null;
}
```

### UpdateFilterValueRequest

```ts
{
  expected_revision?: string | null;
  status?: "active" | "inactive" | "deprecated" | null;
  value?: string | null;
}
```
<!-- product-factory-api:generated:end -->

### Product Factory UI Notes

These notes are human-written because they describe frontend behavior rather than
the exact backend request shape.

Job responses should include a stable job identifier, status, timestamps where available,
and the backend request/result/error payloads when available. `POST /api/jobs/{job_id}/stop`
accepts an optional `reason` and should return the updated job.

The UI treats queued and running-like statuses as active. Terminal statuses stop polling.
`cancelled` is terminal and separate from failed states. `killed` is terminal and failure-like.

Authoring status should report intro-text and SEO metadata task state, output/trace paths,
warnings, `ready_for_render`, and render block reasons.

Filter review should report model, category identity, approval state, render blocking state,
missing required groups, review groups, warnings, and optional artifact paths.

Filters Manager writes include `expected_revision` when the backend has provided a revision.
The revision is the concurrency token for group and value changes.

Filter groups and values support the statuses `active`, `inactive`, and `deprecated`. The UI
does not expose delete actions for filter groups or values.

## Commerce API

Current browser-facing endpoints:

```text
GET    /commerce-api/health

GET    /commerce-api/catalog/summary
GET    /commerce-api/catalog/products
GET    /commerce-api/catalog/categories
GET    /commerce-api/catalog/category-hierarchy
GET    /commerce-api/catalog/brands

GET    /commerce-api/catalog/products/{catalog_product_id}/source-urls
POST   /commerce-api/catalog/products/{catalog_product_id}/source-urls
PATCH  /commerce-api/catalog/source-urls/{source_url_id}
POST   /commerce-api/catalog/source-urls/{source_url_id}/validate
GET    /commerce-api/catalog/source-urls/summary
POST   /commerce-api/catalog/source-urls/import/preview
POST   /commerce-api/catalog/source-urls/import/apply

GET    /commerce-api/vendor-sources/source-urls/summary
GET    /commerce-api/vendor-sources/sources
GET    /commerce-api/source-url-agent/sources
GET    /commerce-api/source-url-agent/runs
POST   /commerce-api/source-url-agent/runs
POST   /commerce-api/source-url-agent/runs/sync
GET    /commerce-api/source-url-agent/runs/{run_id}
GET    /commerce-api/source-url-agent/runs/{run_id}/artifacts
GET    /commerce-api/source-url-agent/candidates
GET    /commerce-api/source-url-agent/candidates/{candidate_id}
PATCH  /commerce-api/source-url-agent/candidates/{candidate_id}/review
POST   /commerce-api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network
GET    /commerce-api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network/latest

GET    /commerce-api/paths/roots
GET    /commerce-api/artifacts/roots
GET    /commerce-api/artifacts/price-monitoring/runs/{run_id}
GET    /commerce-api/artifacts/read?path=...
GET    /commerce-api/artifacts/download?path=...

POST   /commerce-api/price-monitoring/selection/preview
POST   /commerce-api/price-monitoring/runs
GET    /commerce-api/price-monitoring/runs
GET    /commerce-api/price-monitoring/runs/{run_id}
POST   /commerce-api/price-monitoring/runs/{run_id}/fetch
GET    /commerce-api/price-monitoring/runs/{run_id}/fetch
GET    /commerce-api/price-monitoring/runs/{run_id}/fetch/logs
GET    /commerce-api/price-monitoring/runs/{run_id}/fetch/executions
GET    /commerce-api/price-monitoring/runs/{run_id}/fetch/{execution_id}
GET    /commerce-api/price-monitoring/runs/{run_id}/fetch/{execution_id}/logs
POST   /commerce-api/price-monitoring/runs/{run_id}/fetch/cancel
POST   /commerce-api/price-monitoring/runs/{run_id}/fetch/{execution_id}/cancel
GET    /commerce-api/price-monitoring/db/status

GET    /commerce-api/price-monitoring/observations
GET    /commerce-api/price-monitoring/runs/{run_id}/observations
GET    /commerce-api/price-monitoring/runs/{run_id}/catalog-snapshot
GET    /commerce-api/price-monitoring/products/{product_id}/price-history
GET    /commerce-api/price-monitoring/products/by-model/{model}/price-history

GET    /commerce-api/price-monitoring/runs/{run_id}/review
POST   /commerce-api/price-monitoring/runs/{run_id}/review/actions
POST   /commerce-api/price-monitoring/runs/{run_id}/export-price-update

GET    /commerce-api/price-monitoring/alerts/rules
POST   /commerce-api/price-monitoring/alerts/rules
GET    /commerce-api/price-monitoring/alerts/rules/{rule_id}
PATCH  /commerce-api/price-monitoring/alerts/rules/{rule_id}
POST   /commerce-api/price-monitoring/alerts/rules/{rule_id}/deactivate
GET    /commerce-api/price-monitoring/alerts/events
POST   /commerce-api/price-monitoring/alerts/events/{event_id}/acknowledge
POST   /commerce-api/price-monitoring/alerts/events/{event_id}/resolve
POST   /commerce-api/price-monitoring/alerts/evaluate/{run_id}

GET    /commerce-api/files/roots
GET    /commerce-api/files/list
POST   /commerce-api/files/read
POST   /commerce-api/files/save
POST   /commerce-api/files/save-copy
```

### Catalog Contracts

Catalog products are returned as paginated items. The UI uses these query fields:

```ts
{
  q?: string | null;
  family?: string | null;
  category_name?: string | null;
  sub_category?: string | null;
  manufacturer?: string | null;
  marketplace?: "all" | "bestprice" | "skroutz" | "both" | "none" | null;
  page?: number;
  page_size?: number;
  atomic_only?: boolean;
  ignored?: "exclude" | "include";
  automation_eligible_only?: boolean;
}
```

Catalog hierarchy filters use `family`, `category_name`, and `sub_category`. The UI label is
`Category`, but request payloads and query params use `category_name`.

Catalog browsing reads from PostgreSQL. The active catalog import is backend-owned runtime
state, not a live CSV read from the browser.

Source URL records require a URL and support statuses such as `active`, `disabled`, `broken`,
`redirected`, and `needs_review`. Source URL import has separate preview and apply calls, and
apply should only be enabled after the operator has reviewed the preview report.

Skroutz browser network diagnostics are explicit operator/admin actions from Vendor Source
Candidate Review when a Skroutz candidate is linked to an active source URL. The workflow opens
the Skroutz product page in Playwright, captures sanitized JSON/XHR/fetch response summaries,
compares them with derived `filter_products.json` and `shops_details.json` URLs, and renders a
compact endpoint table. It does not replace normal direct JSON capture, does not run in scheduled
monitoring, and does not create price observations.

### Price Monitoring Contracts

Selection preview and run creation use:

```ts
{
  source: "skroutz" | "bestprice";
  filters: {
    q: string | null;
    family?: string | null;
    category_name?: string | null;
    sub_category?: string | null;
    manufacturer: string | null;
    marketplace: "bestprice" | "skroutz" | "both" | "none" | null;
    has_mpn: boolean;
    atomic_only: boolean;
    automation_eligible_only: boolean;
  };
  selected_models: string[];
  excluded_models: string[];
  include_ignored: boolean;
  dry_run: boolean;
}
```

Fetch execution uses:

```ts
{
  source: "skroutz" | "bestprice" | null;
  catalog_url: string | null;
}
```

Fetch execution statuses are `queued`, `running`, `succeeded`, `failed`, `killed`, and
`cancelled`. `killed` is terminal and failure-like. `cancelled` is terminal and separate from
failed states.

Price Monitoring requires PostgreSQL and an active imported catalog. The UI reads
`GET /commerce-api/price-monitoring/db/status`; only `ready_for_price_monitoring: true`
enables Price Monitoring preview, run creation, fetch, review, export, execution history, and
alert workflows.

A DB-not-ready response locks Price Monitoring only. It should not imply that commerce health,
file roots, path roots, or artifacts are unavailable.

Review actions use:

```ts
{
  enriched_csv_path: string | null;
  actions: Array<{
    model: string;
    selected_action: "match_price" | "undercut" | "ignore";
    undercut_amount?: number | null;
    reason?: string;
  }>;
}
```

Price update export uses:

```ts
{
  review_csv_path: string | null;
  output_path: string | null;
}
```

The export result is a CSV artifact. The UI does not update OpenCart directly.

### Alert Contracts

Alert rules support the current rule type:

```ts
"competitor_below_own_price"
```

Rule bodies include optional product identity fields, optional amount or percent thresholds,
and an `active` flag. Alert events support `open`, `acknowledged`, and `resolved` statuses.

### Safe CSV File Contracts

CSV file reads and writes preserve values as strings so values such as leading-zero product
models are not changed by the browser.

`POST /commerce-api/files/save-copy` is the normal safe write path. Save in place is available
through `POST /commerce-api/files/save` and should remain guarded by the UI.

### Artifact Contracts

Artifact list endpoints return items with path, name, extension, size, read/download
capabilities, and optional warnings. Previewable artifacts are read through
`/commerce-api/artifacts/read?path=...`; downloads use
`/commerce-api/artifacts/download?path=...`.

CSV artifacts preview as tables with string-preserved values. JSON artifacts preview as
formatted text when valid and raw text otherwise. TXT and LOG artifacts preview as plain text.
