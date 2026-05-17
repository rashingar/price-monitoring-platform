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
- Compatibility facades must be documented, guarded, and avoided for new
  application imports.

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
| Product Factory job runtime ownership | Product Factory API / jobs runtime | Job models, store, and runner live under `product_factory.jobs`; normal tests now import owner paths and API import paths have only explicit compatibility coverage. | Low | Keep the compatibility test until a deprecation window retires the public API shim paths. | Do not place new job execution internals under `product_factory.api`. |
| Source URL Agent route private wrappers | API routes / compatibility seams | Delegate-only private wrappers in Source URL Agent route modules were removed; tests patch public helper seams. | Low | Patch service/repository/helper seams in future tests. | Do not add route-private wrappers solely for monkeypatching. |
| Frontend Stock Sync request type drift | web client / generated contracts | `StockSyncRunRequest` now aliases the generated OpenAPI schema instead of a handwritten interface. | Low | Keep new request bodies generated-schema-derived as endpoint groups are touched. | Do not add handwritten `*Request` interfaces in `commerceTypes.ts` when a generated schema exists. |

## Remaining Deferred Items

| Item | Boundary | Current state | Risk level | Next action | What not to do |
| --- | --- | --- | --- | --- | --- |
| Source URL Agent candidate history payload uses API serializers | Source URL Agent service / API serializers | `ecommerce.source_url_agent.candidate_history_service` still imports `ecommerce.api.source_url_agent.serializers`. A guard allows only this known dependency. | Medium | Move shared candidate/run payload serialization to a non-API module, then remove the allowlist entry. | Do not add new domain/service imports from `ecommerce.api.*`. |
| Source URL Agent run history route still queries runs directly | API routes / repositories | `api/source_url_agent/runs.py` still owns simple run list/get SQL. | Medium | Extract run history lookup to a repository/service helper when touching run history behavior. | Do not expand route-owned run query mechanics. |
| Source URL Agent `agent` compatibility facade remains public | compatibility facade / public imports | Application and normal tests now import `ecommerce.source_url_agent.options` and `ecommerce.source_url_agent.runner`; only an explicit compatibility test and docs reference the historical facade. | Low | Keep the no-application-import guard; remove the facade only after public/operator compatibility is explicitly retired. | Do not add new application imports from `ecommerce.source_url_agent.agent`. |
| Ecommerce DB compatibility wrapper modules remain | compatibility wrappers / repositories | Old modules under `ecommerce.db.*` re-export repository helpers for compatibility. Search shows no application/test/script imports beyond guard/docs, but the public compatibility window is still open. | Medium | Keep wrappers until scripts/operator imports are retired or a deprecation window is explicit. | Do not delete wrappers just because internal app code no longer imports them. |
| Ecommerce DB model/repository package barrels remain | metadata registration / repository imports | `ecommerce.db.models` is the metadata registration path for Alembic/metadata loading; `ecommerce.db.repositories` is a lazy compatibility barrel. Normal tests use owner paths except explicit package/barrel compatibility coverage. | Medium | Keep import-boundary tests preventing new app imports from the barrels except documented infrastructure. | Do not remove `ecommerce.db.models.__init__`; do not add new app imports from repository barrels. |
| Durable jobs still default to local API inline fallback | durable jobs / local operator behavior | Worker-owned execution is the long-term target, but the local default still preserves API inline execution. | Medium | Decide and document a future default flip only after operator startup and worker expectations are stable. | Do not silently change the default or job status semantics. |
| Frontend handwritten ecommerce types remain | web client / generated contracts | `commerceClient.ts` and `commerceTypes.ts` remain transitional facades with some generated-derived aliases. | Medium | Continue replacing request groups with generated schema aliases in narrow prompts. | Do not rewrite the entire client or manually edit generated files. |
| Product Factory API compatibility shims remain | Product Factory API / jobs runtime | `product_factory.api.job_models`, `job_runner`, and `job_store` are no longer used by normal tests; one explicit compatibility test keeps the public shim contract covered. | Low | Remove only after public/script/docs compatibility is intentionally retired and search proves zero usage. | Do not remove API shims until compatibility usage is proven gone and the deprecation window is closed. |
| Broad unreachable-code analysis is deferred | Python critical packages | A lightweight guard now scans only recently refactored critical packages for statements immediately after `return`, `raise`, `break`, or `continue`. | Low | Expand only when there is a concrete regression class and a low-noise target. | Do not add a broad repository scanner that blocks on style or false positives. |

## Known Compatibility Shims

These modules remain intentionally available for now, but new application code
should prefer the owner modules listed here.

| Shim | Status | Owner path to prefer | Current usage | Removal criteria | Guardrail |
| --- | --- | --- | --- | --- | --- |
| `ecommerce.source_url_agent.agent` | deprecated, guarded | `ecommerce.source_url_agent.options` and `ecommerce.source_url_agent.runner` | No application or normal test imports; retained for public/operator compatibility and covered by `test_source_url_agent_agent_facade_reexports_owner_symbols`. | Remove later only after docs/operator compatibility is retired and search proves zero app/test/script/docs usage. | `test_application_code_does_not_import_source_url_agent_agent_facade` blocks application imports. |
| `ecommerce.db.repositories` barrel | active compatibility | Repository submodules such as `ecommerce.db.repositories.source_urls` | No application imports; one explicit compatibility test imports the lazy barrel. | Remove later only after public compatibility is retired and compatibility tests/docs are updated. | `test_application_code_does_not_import_deprecated_db_barrels` blocks new app imports. |
| `ecommerce.db.models` package barrel | keep permanently for metadata/registration | Model submodules, except metadata registration through `ecommerce.db.__init__` and Alembic | Required by Alembic/metadata loading and explicit metadata package tests; normal tests use `ecommerce.db.models.base.Base` and model submodules. | Do not remove while SQLAlchemy metadata registration depends on this package loader. | `test_application_code_does_not_import_deprecated_db_barrels` allows only documented infrastructure. |
| Old `ecommerce.db.*` repository wrappers | remove later | `ecommerce.db.repositories.*` | No application/test/script imports found beyond guard/docs; retained for public/operator compatibility during the repository split migration. | Remove later only after the compatibility window is explicitly closed and search proves zero app/test/script/docs usage. | `test_application_code_does_not_import_old_db_wrapper_modules` blocks application imports. |
| `product_factory.api.job_runner` and `product_factory.api.job_store` | deprecated, guarded | `product_factory.jobs.runner` and `product_factory.jobs.store` | No production or normal test imports; one explicit compatibility test verifies re-export identity. | Remove later only after public/script/docs compatibility is retired and search proves zero app/test/script/docs usage. | Product Factory architecture tests block non-API runtime imports from these shims. |
| `product_factory.api.job_models` | deprecated, guarded | `product_factory.jobs.models` | No production or normal test imports; one explicit compatibility test verifies re-export identity. | Remove later only after public/script/docs compatibility is retired and search proves zero app/test/script/docs usage. | Product Factory architecture tests include this shim and block non-API runtime imports. |
| None in this pass | removed in this pass | n/a | No shim met both zero-usage and explicit-safe-removal criteria. | n/a | n/a |

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
- new application imports from the `ecommerce.source_url_agent.agent`
  compatibility facade;
- new application imports from old `ecommerce.db.*` repository wrapper modules.
- Product Factory non-API runtime modules importing API job compatibility shims,
  including `product_factory.api.job_models`;
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
