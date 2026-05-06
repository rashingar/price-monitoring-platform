# 0003: Database Ownership

## Status

Accepted; implemented.

## Context

The platform needs a clear owner for persistent ecommerce data and database
migrations before app folders were migrated into the monorepo. The Product
Factory backend currently has artifact/file-backed behavior, while the
Ecommerce backend owns catalog and monitoring persistence.

## Decision

`ecommerce-api` owns the platform database and migrations.

PostgreSQL is the `ecommerce-api` source of truth.

`ecommerce-api` owns migrations for:

- Catalog data.
- Source URLs.
- Observations.
- Monitoring runs.
- Alerts.
- Review and export data.
- Vendor source capture.
- Related ecommerce data.

`product-factory-api` remains artifact/file-backed initially.
`product-factory-api` may later add DB-backed job state.

Cross-app integration should happen through APIs, handoff artifacts, or explicit
shared contracts.

## Consequences

- Database migration ownership is unambiguous.
- Catalog and monitoring persistence evolve in one backend.
- Product Factory can preserve artifact-backed behavior instead of being forced
  into the ecommerce schema.
- Cross-app direct database coupling should not be introduced casually.
- Direct database reads or writes across app boundaries require a separate
  architecture decision.

## Future Options

If `product-factory-api` later needs durable database tables, decide later
whether to use:

- A separate schema in the same PostgreSQL instance.
- A separate database.

That decision should be based on operational ownership, backup/restore needs,
data coupling, migration ownership, and deployment constraints.
