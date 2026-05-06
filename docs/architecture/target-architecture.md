# Target Architecture

Status: historical. The target architecture described by this document has
landed and is now represented by
[Current Architecture](current-architecture.md).

Use the current architecture document for active operator and development
guidance. This file remains only as a migration record.

## Completed Target

- Apps live under the final monorepo layout:
  - `apps/product-factory-api`
  - `apps/ecommerce-api`
  - `apps/web`
- Shared OpenAPI snapshots live under `packages/contracts`.
- Root scripts live under `scripts/setup`, `scripts/dev`, `scripts/test`,
  `scripts/contracts`, and `scripts/check`.
- Product Factory uses the Python project/install name `product-factory` and
  internal package `product_factory`.
- Ecommerce API uses internal package `ecommerce`.
- The web app keeps `/api` and `/commerce-api` browser proxy routes stable.
- Ecommerce API owns PostgreSQL migrations and persisted ecommerce data.
- Product Factory remains artifact-backed for local product runs.

## Current Guidance

For active documentation, use:

- [Current Architecture](current-architecture.md)
- [Operator Startup](../runbooks/operator-startup.md)
- [Codex Workflow](../runbooks/codex-workflow.md)
- [Testing Strategy](../runbooks/testing-strategy.md)

For the historical completion record, use
[Monorepo Migration](../runbooks/monorepo-migration.md).
