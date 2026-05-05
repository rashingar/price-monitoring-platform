# Price Monitoring Platform

Price Monitoring Platform is a monorepo for product creation, ecommerce catalog
and price monitoring, and the operator console that coordinates those workflows.

## Apps

Target app names:

- `apps/product-factory-api`: Product Factory backend.
- `apps/ecommerce-api`: Ecommerce catalog and monitoring backend.
- `apps/web`: Operator console frontend.

The app folders may not yet be present under their final names if this
documentation step is run before the mechanical migration. Legacy folders may
still exist until the migration runbook is executed.

## Architecture

- [Target architecture](docs/architecture/target-architecture.md)
- [0001: Monorepo with Separate Apps](docs/decisions/0001-monorepo-with-separate-apps.md)
- [0002: App Naming and Domain Boundaries](docs/decisions/0002-app-naming-and-domain-boundaries.md)
- [0003: Database Ownership](docs/decisions/0003-database-ownership.md)
- [0004: Staged Package Renames](docs/decisions/0004-staged-package-renames.md)
- [0005: Contracts-First Integration](docs/decisions/0005-contracts-first-integration.md)
- [Monorepo migration runbook](docs/runbooks/monorepo-migration.md)

## Migration Status

Architecture documentation is the first step. Mechanical folder migration, root
scripts, contract snapshot mirroring, generated clients, workers, Docker, and
database migration changes are intentionally out of scope for this step.
