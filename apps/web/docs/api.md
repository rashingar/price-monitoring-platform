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

Current browser-facing endpoints:

```text
GET    /api/health

POST   /api/jobs/prepare
POST   /api/jobs/render
POST   /api/jobs/publish
GET    /api/jobs
GET    /api/jobs/{job_id}
POST   /api/jobs/{job_id}/stop
GET    /api/jobs/{job_id}/logs
GET    /api/jobs/{job_id}/artifacts

GET    /api/authoring/{model}
POST   /api/authoring/{model}/intro-text
POST   /api/authoring/{model}/intro-text/retry
POST   /api/authoring/{model}/seo-meta
POST   /api/authoring/{model}/seo-meta/retry

GET    /api/filter-review/{model}
PUT    /api/filter-review/{model}
POST   /api/filter-review/{model}/approve

GET    /api/settings
PATCH  /api/settings

GET    /api/filters/status
GET    /api/filters/categories
GET    /api/filters/categories/{category_id}
PUT    /api/filters/categories/{category_id}/groups
PATCH  /api/filters/categories/{category_id}/groups/{group_id}
PUT    /api/filters/categories/{category_id}/groups/{group_id}/values
PATCH  /api/filters/categories/{category_id}/groups/{group_id}/values/{value_id}
POST   /api/filters/sync
GET    /api/filters/sync-report
```

### Product Factory Contracts

`POST /api/jobs/prepare` accepts:

```ts
{
  model: string;
  url: string;
  photos: number;
  sections: number;
  skroutz_status: number;
  boxnow: number;
  price: number | null;
}
```

`POST /api/jobs/render` and `POST /api/jobs/publish` accept:

```ts
{
  model: string;
}
```

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
GET    /commerce-api/vendor-sources/agent/runs
POST   /commerce-api/vendor-sources/agent/runs
GET    /commerce-api/vendor-sources/candidates
POST   /commerce-api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network
GET    /commerce-api/vendor-sources/source-urls/{source_url_id}/diagnostics/skroutz-network/latest

GET    /commerce-api/paths/roots
GET    /commerce-api/artifacts/roots
GET    /commerce-api/artifacts/bridge/runs/{run_id}
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
POST   /commerce-api/bridge/run
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
CSV Bridge, file roots, path roots, or artifacts are unavailable.

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

### CSV Bridge Contracts

CSV file reads and writes preserve values as strings so values such as leading-zero product
models are not changed by the browser.

`POST /commerce-api/files/save-copy` is the normal safe write path. Save in place is available
through `POST /commerce-api/files/save` and should remain guarded by the UI.

Bridge runs accept:

```ts
{
  opencart_export_path: string;
  stock_csv_path: string | null;
  output_dir: string | null;
}
```

When `stock_csv_path` is omitted, the backend default is used.

### Artifact Contracts

Artifact list endpoints return items with path, name, extension, size, read/download
capabilities, and optional warnings. Previewable artifacts are read through
`/commerce-api/artifacts/read?path=...`; downloads use
`/commerce-api/artifacts/download?path=...`.

CSV artifacts preview as tables with string-preserved values. JSON artifacts preview as
formatted text when valid and raw text otherwise. TXT and LOG artifacts preview as plain text.
