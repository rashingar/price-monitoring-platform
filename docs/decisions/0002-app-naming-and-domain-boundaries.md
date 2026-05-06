# 0002: App Naming and Domain Boundaries

## Status

Accepted; implemented.

## Context

The pre-monorepo repositories used names that no longer described the platform
domains clearly. The monorepo needed stable app names before folder migration
so documentation, scripts, contracts, and future prompts could refer to the
same targets.

## Decision

Use `product-factory-api`, `ecommerce-api`, and `web` as the app names.

| Pre-monorepo source | Current monorepo path |
| --- | --- |
| Product Factory backend | `apps/product-factory-api` |
| Ecommerce backend | `apps/ecommerce-api` |
| Web operator console | `apps/web` |

Ownership boundaries:

- `product-factory-api` owns product creation/factory workflows.
- `ecommerce-api` owns ecommerce catalog/monitoring workflows.
- `web` owns operator console workflows.

## Consequences

- The Product Factory backend has a name that reflects product creation,
  product authoring, rendering, CSV generation, and handoff artifacts.
- The Ecommerce backend has a name that reflects catalog, source URL, vendor
  source, monitoring, review, export, alert, and database responsibilities.
- The frontend has a neutral app name that can cover all operator workflows.
- Documentation and root scripts use stable app names now that app folders are
  in their final locations.

Boundary rules:

- `product-factory-api` must not own price monitoring runs or alerts.
- `ecommerce-api` must not own LLM intro writing or product rendering
  internals.
- `web` must not directly mutate local files or run jobs except through backend
  APIs.
