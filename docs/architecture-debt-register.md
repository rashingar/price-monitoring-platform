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
| Product Factory job runtime ownership | Product Factory API / jobs runtime | Job models, store, and runner live under `product_factory.jobs`; API import paths are compatibility shims. | Low | Migrate remaining tests and scripts to preferred `product_factory.jobs.*` imports over time. | Do not place new job execution internals under `product_factory.api`. |
| Source URL Agent route private wrappers | API routes / compatibility seams | Delegate-only private wrappers in Source URL Agent route modules were removed; tests patch public helper seams. | Low | Patch service/repository/helper seams in future tests. | Do not add route-private wrappers solely for monkeypatching. |
| Frontend Stock Sync request type drift | web client / generated contracts | `StockSyncRunRequest` now aliases the generated OpenAPI schema instead of a handwritten interface. | Low | Keep new request bodies generated-schema-derived as endpoint groups are touched. | Do not add handwritten `*Request` interfaces in `commerceTypes.ts` when a generated schema exists. |

## Remaining Deferred Items

| Item | Boundary | Current state | Risk level | Next action | What not to do |
| --- | --- | --- | --- | --- | --- |
| Source URL Agent candidate history payload uses API serializers | Source URL Agent service / API serializers | `ecommerce.source_url_agent.candidate_history_service` still imports `ecommerce.api.source_url_agent.serializers`. A guard allows only this known dependency. | Medium | Move shared candidate/run payload serialization to a non-API module, then remove the allowlist entry. | Do not add new domain/service imports from `ecommerce.api.*`. |
| Source URL Agent run history route still queries runs directly | API routes / repositories | `api/source_url_agent/runs.py` still owns simple run list/get SQL. | Medium | Extract run history lookup to a repository/service helper when touching run history behavior. | Do not expand route-owned run query mechanics. |
| Source URL Agent `agent` compatibility facade remains in app imports | compatibility facade / application imports | Several app modules still import `ecommerce.source_url_agent.agent`; a guard fixes the known import set. | Medium | Migrate imports to `options` and `runner` modules in a behavior-neutral pass. | Do not add new application imports from `ecommerce.source_url_agent.agent`. |
| Ecommerce DB compatibility wrapper modules remain | compatibility wrappers / repositories | Old modules under `ecommerce.db.*` re-export repository helpers for compatibility. No new app imports should use them. | Medium | Keep wrappers until scripts/operator imports are retired or a deprecation window is explicit. | Do not delete wrappers just because internal app code no longer imports them. |
| Ecommerce DB model/repository package barrels remain | metadata registration / repository imports | `ecommerce.db.models` is the metadata registration path; `ecommerce.db.repositories` is a lazy compatibility barrel. App code should use model/repository submodules. | Medium | Keep import-boundary tests preventing new app imports from the barrels except documented infrastructure. | Do not remove `ecommerce.db.models.__init__`; do not add new app imports from repository barrels. |
| Durable jobs still default to local API inline fallback | durable jobs / local operator behavior | Worker-owned execution is the long-term target, but the local default still preserves API inline execution. | Medium | Decide and document a future default flip only after operator startup and worker expectations are stable. | Do not silently change the default or job status semantics. |
| Frontend handwritten ecommerce types remain | web client / generated contracts | `commerceClient.ts` and `commerceTypes.ts` remain transitional facades with some generated-derived aliases. | Medium | Continue replacing request groups with generated schema aliases in narrow prompts. | Do not rewrite the entire client or manually edit generated files. |
| Product Factory API compatibility shims remain | Product Factory API / jobs runtime | `product_factory.api.job_models`, `job_runner`, and `job_store` are still used by tests and remain public compatibility shims. | Low | Migrate test imports to `product_factory.jobs.*`, then reassess shim removal separately. | Do not remove API shims until compatibility usage is proven gone. |
| Broad unreachable-code analysis is deferred | Python critical packages | A lightweight guard now scans only recently refactored critical packages for statements immediately after `return`, `raise`, `break`, or `continue`. | Low | Expand only when there is a concrete regression class and a low-noise target. | Do not add a broad repository scanner that blocks on style or false positives. |

## Known Compatibility Shims

These modules remain intentionally available for now, but new application code
should prefer the owner modules listed here.

| Shim | Owner path to prefer | Why it remains | Guardrail |
| --- | --- | --- | --- |
| `ecommerce.source_url_agent.agent` | `ecommerce.source_url_agent.options` and `ecommerce.source_url_agent.runner` | Existing CLI/API/test imports still use the facade while Source URL Agent internals settle. | `test_source_url_agent_agent_compat_imports_are_known_only` allowlists the current import set. |
| `ecommerce.db.repositories` barrel | Repository submodules such as `ecommerce.db.repositories.source_urls` | Lazy barrel compatibility for older imports. | `test_application_code_does_not_import_deprecated_db_barrels` blocks new app imports. |
| `ecommerce.db.models` package barrel | Model submodules, except metadata registration through `ecommerce.db.__init__` | The package barrel registers SQLAlchemy metadata and is still needed by DB setup. | `test_application_code_does_not_import_deprecated_db_barrels` allows only documented infrastructure. |
| Old `ecommerce.db.*` repository wrappers | `ecommerce.db.repositories.*` | Operator/scripts compatibility during repository split migration. | `test_application_code_does_not_import_old_db_wrapper_modules` blocks application imports. |
| `product_factory.api.job_runner` and `product_factory.api.job_store` | `product_factory.jobs.runner` and `product_factory.jobs.store` | API-level import compatibility while tests/scripts migrate. | Product Factory architecture tests block non-API runtime imports from these shims. |
| `product_factory.api.job_models` | `product_factory.jobs.models` | Public compatibility for existing tests/scripts. | Documented debt; not removed until compatibility usage is retired. |

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
  compatibility facade beyond the known allowlist;
- new application imports from old `ecommerce.db.*` repository wrapper modules.
- Product Factory non-API runtime modules importing API job compatibility shims;
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
