# Architecture Debt Register

This register preserves the architecture decisions clarified during the recent
boundary cleanup work. It is intentionally small and operational: each item
states the affected boundary, current state, risk, next action, and what not to
do while the debt remains.

## Current Boundary Decisions

- API routes are HTTP adapters: validate request inputs, translate errors, and
  call services or repositories.
- Services own workflow orchestration: sequencing, workflow state transitions,
  artifact read/write decisions, progress semantics, and repository
  composition.
- Repositories own DB mechanics: SQLAlchemy filters, counts, ordering,
  pagination, row state transitions, and established row serialization
  contracts.
- Durable workers are the canonical durable job executors. API inline execution
  exists only as the configured local/operator fallback controlled by
  `ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE`.
- Generated OpenAPI-derived frontend types are the frontend API type authority.
- Removed compatibility paths must stay deleted and owner-path imports are the
  default for application code, tests, scripts, and docs.

## Resolved Items

| Item | Boundary | Current state | Risk level | Next action | What not to do |
| --- | --- | --- | --- | --- | --- |
| Durable job inline execution policy | API routes / durable worker | API background execution is explicit and controlled by `ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE`; worker remains canonical. | Low | Keep route tests covering enabled and disabled policy behavior. | Do not add route-owned durable execution paths without consulting the policy helper. |
| Source URL Agent queued-run setup | API routes / Source URL Agent service | Queued run setup moved to `ecommerce.source_url_agent.enqueue_service`; route remains response/error adapter. | Low | Move any new queued-run sequencing into the service. | Do not rebuild run/task/job setup in route modules. |
| Source URL Agent candidate listing filters | API routes / repositories | Candidate list filtering, counts, ordering, pagination, and SQL wildcard escaping live in repository helpers. | Low | Keep literal `%`, `_`, and backslash regression coverage. | Do not put SQLAlchemy candidate filters back in API routes. |
| Platform health readiness dependency | platform health / API | Source URL Agent readiness calculation is shared outside API modules; platform health no longer imports API readiness. | Low | Keep the platform-health import guard. | Do not import `ecommerce.api.*` from platform health collectors. |
| Source URL import summary/count logic | API routes / source URL repository/service | SQL summary/count mechanics moved out of `routes_source_url_import.py`. | Low | Keep route tests focused on response shape and service/repository tests on query mechanics. | Do not reintroduce aggregate SQL in import routes. |
| Catalog category/brand/hierarchy aggregation | API routes / catalog repository | Catalog aggregation and hierarchy query mechanics moved to catalog helpers. | Low | Add helper tests when catalog aggregation expands. | Do not add repeated catalog SQL fragments to routes. |
| Vendor Source request type drift | web client / generated contracts | Vendor Source capture/import request types are generated-schema-derived aliases. | Low | Continue endpoint group by endpoint group. | Do not duplicate generated request shapes in handwritten frontend types. |
| Product Factory job runtime ownership | Product Factory API / jobs runtime | Job models, store, and runner live under `product_factory.jobs`; API job shim files under `product_factory.api` were removed. | Low | Keep guardrails that fail if old API job shim files or imports are reintroduced. | Do not place new job execution internals under `product_factory.api`. |
| Source URL Agent route private wrappers | API routes / compatibility seams | Delegate-only private wrappers in Source URL Agent route modules were removed; tests patch public helper seams. | Low | Patch service/repository/helper seams in future tests. | Do not add route-private wrappers solely for monkeypatching. |
| Frontend Stock Sync request type drift | web client / generated contracts | `StockSyncRunRequest` now aliases the generated OpenAPI schema instead of a handwritten interface. | Low | Keep new request bodies generated-schema-derived as endpoint groups are touched. | Do not add handwritten `*Request` interfaces in `commerceTypes.ts` when a generated schema exists. |
| Source URL Agent `agent` facade | Source URL Agent runtime imports | Historical `ecommerce.source_url_agent.agent` facade was removed; option/result types live in `options` and execution lives in `runner`. | Low | Keep guardrails that fail if the facade file or imports are reintroduced. | Do not recreate a facade for lower-level Source URL Agent imports. |
| Ecommerce DB repository wrappers and barrel | DB repositories | Old `ecommerce.db.*` repository wrappers were removed; `ecommerce.db.repositories` no longer re-exports helpers and is only a package marker. | Low | Keep imports on concrete repository modules. | Do not reintroduce lazy package-level repository exports. |
| Ecommerce DB model barrel behavior | DB models / metadata registration | `ecommerce.db.models` remains only as a metadata-registration package; model-class, `Base`, and `JSON_DOCUMENT` re-exports were removed. | Low | Keep Alembic and metadata tests importing `Base` from `ecommerce.db.models.base` and loading `ecommerce.db.models` for side effects. | Do not reintroduce model-class re-exports from `ecommerce.db.models`. |
| Source URL Agent candidate history payload ownership | Source URL Agent service / payload helpers | Shared candidate and discovery-run payload helpers live in `ecommerce.source_url_agent.payloads`; candidate history no longer imports API serializers. | Low | Keep non-API import guardrails and candidate history response-shape coverage. | Do not add domain/service imports from `ecommerce.api.*`. |
| Source URL Agent run history query ownership | API routes / repositories | Run count, list, get, and discovery-task lookup mechanics live in `ecommerce.db.repositories.source_urls`; API routes validate inputs, translate HTTP errors, attach artifacts, and serialize responses. | Low | Keep route tests on payload shape and repository tests on ordering/count behavior. | Do not put discovery-run SQL back in API routes. |

## Remaining Deferred Items

| Item | Boundary | Current state | Risk level | Next action | What not to do |
| --- | --- | --- | --- | --- | --- |
| Durable jobs still default to local API inline fallback | durable jobs / local operator behavior | Worker-owned execution is the long-term target, but the local default still preserves API inline execution. Server/self-hosting guidance now recommends `ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE=false` with a separate worker process, and platform health now reports durable queued/running/stale backlog risk from the job table. | Medium | Keep the default deferred until the durable worker deployment runbook is operationally proven, worker startup is part of deployment automation, operator smoke/checks consume the backlog health signal, process supervision detects missing worker services, and enqueue-only mode remains covered for catalog update and Source URL Agent jobs. | Do not silently change the default, remove the local fallback, add OS process detection to platform health, or change job status semantics. |
| Frontend handwritten ecommerce types remain | web client / generated contracts | `commerceClient.ts` and `commerceTypes.ts` remain transitional facades with some generated-derived aliases. | Medium | Continue replacing request groups with generated schema aliases in narrow prompts. | Do not rewrite the entire client or manually edit generated files. |
| Broad unreachable-code analysis is deferred | Python critical packages | A lightweight guard now scans only recently refactored critical packages for statements immediately after `return`, `raise`, `break`, or `continue`. | Low | Expand only when there is a concrete regression class and a low-noise target. | Do not add a broad repository scanner that blocks on style or false positives. |

## Removed Compatibility Paths

These paths were removed. Use the owner paths listed here.

| Removed path | Owner path to use | Replacement state | Guardrail |
| --- | --- | --- | --- |
| `ecommerce.source_url_agent.agent` | `ecommerce.source_url_agent.options` and `ecommerce.source_url_agent.runner` | File deleted; compatibility tests removed. | Ecommerce architecture tests fail if the file or imports return. |
| `product_factory.api.job_runner` | `product_factory.jobs.runner` | File deleted; compatibility tests removed. | Product Factory architecture tests fail if the file or imports return. |
| `product_factory.api.job_store` | `product_factory.jobs.store` | File deleted; compatibility tests removed. | Product Factory architecture tests fail if the file or imports return. |
| `product_factory.api.job_models` | `product_factory.jobs.models` | File deleted; compatibility tests removed. | Product Factory architecture tests fail if the file or imports return. |
| Old `ecommerce.db.*` repository wrappers | `ecommerce.db.repositories.*` concrete modules | Wrapper files deleted. | Ecommerce architecture tests fail if files or imports return. |
| `ecommerce.vendor_sources.run_repository` | `ecommerce.db.repositories.vendor_sources` | Wrapper file deleted. | Ecommerce architecture tests fail if the file or imports return. |
| `ecommerce.db.repositories` helper re-exports | Concrete repository submodules | Package remains as a marker only with no helper re-exports. | Repository package tests and architecture checks fail if barrel imports/re-exports return. |
| `ecommerce.db.models` model-class re-exports | Concrete model submodules; `ecommerce.db.models.base` for `Base` | Package remains for metadata registration only. | Model package tests fail if model-class, `Base`, or `JSON_DOCUMENT` re-exports return. |

## Guardrails

The lightweight Python import-boundary guardrails live in
`apps/ecommerce-api/tests/test_architecture_boundaries.py` and
`apps/product-factory-api/src/product_factory/tests/test_architecture_boundaries.py`.

They protect against:

- platform health importing `ecommerce.api.*`;
- new application imports from deprecated `ecommerce.db.models` and
  `ecommerce.db.repositories` barrels;
- new non-API imports from `ecommerce.api.*` beyond the known allowlist;
- domain/service modules importing Ecommerce route modules such as
  `ecommerce.api.routes_*` or `ecommerce.api.source_url_agent.*`;
- source or test imports from removed compatibility paths;
- removed compatibility module files being recreated;
- DB model/repository package-level compatibility re-exports returning;
- Product Factory source or test modules importing removed API job shim paths;
- obvious unreachable blocks in the currently critical Python packages:
  `ecommerce.platform_health`, `ecommerce.source_url_agent`,
  `ecommerce.db.repositories`, and `product_factory.jobs`.

Frontend contract guardrails live in
`apps/web/src/test/contracts/generatedContractDrift.contract.test.ts` and
`apps/web/scripts/check-fixture-contracts.mjs`.

They protect against:

- handwritten `*Request` interfaces or object request types being reintroduced
  in `commerceTypes.ts` when generated schemas should be used;
- high-risk Commerce request aliases drifting away from generated OpenAPI
  schemas;
- fixture request examples using stale fields such as `handoff_path`, `file`,
  or Vendor Source capture `source_filter`.

If a guard fails, either move the code to the correct owner or update this
register with a deliberate, reviewed allowlist entry and a follow-up action.
