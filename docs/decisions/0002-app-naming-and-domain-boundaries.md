# 0002: App Naming and Domain Boundaries

## Status

Accepted

## Context

The legacy repositories use names that no longer describe the long-term
platform domains clearly. The monorepo needs stable app names before mechanical
folder migration so documentation, scripts, contracts, and future prompts can
refer to the same targets.

## Decision

Use `product-factory-api`, `ecommerce-api`, and `web` as the app names.

| Old name | New monorepo path |
| --- | --- |
| Product-Agent | `apps/product-factory-api` |
| price-fetcher | `apps/ecommerce-api` |
| product-agent-ui | `apps/web` |

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
- Documentation and root scripts can use stable app names before the app folders
  are mechanically migrated.

Boundary rules:

- `product-factory-api` must not own price monitoring runs or alerts.
- `ecommerce-api` must not own LLM intro writing or product rendering
  internals.
- `web` must not directly mutate local files or run jobs except through backend
  APIs.
