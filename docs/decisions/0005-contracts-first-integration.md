# 0005: Contracts-First Integration

## Status

Accepted

## Context

The platform has multiple apps that need to coordinate without importing each
other's internals. The web app calls both backends, and the two backends may
exchange data through handoff artifacts and public APIs.

The monorepo should make contracts visible and testable before introducing
generated clients or deeper integration work.

## Decision

Use contracts-first integration between apps.

`packages/contracts` is the first shared package. It should mirror Product
Factory and Ecommerce OpenAPI snapshots after migration.

Frontend API clients may later be generated from these contracts. The web app
should depend on contracts/API clients rather than hand-maintained assumptions
where possible.

Cross-app integration should prefer:

- APIs.
- Explicit handoff artifacts.
- Contract fixtures.

`product-factory-api` must not import `ecommerce-api` internals directly.
`ecommerce-api` must not import `product-factory-api` internals directly.

## Consequences

- Public API shape becomes visible at the monorepo root.
- Frontend/backend drift can be caught with contract checks.
- Backend-to-backend coupling is constrained to explicit integration surfaces.
- Generated clients can be added later without changing the first migration
  scope.
- Shared packages start with contracts instead of becoming general-purpose
  dumping grounds.
