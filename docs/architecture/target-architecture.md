# Target Architecture

## Overview

The Price Monitoring Platform is moving to a monorepo with separate apps, not
one merged application. The repository will coordinate source code, contracts,
scripts, documentation, and future shared packages while preserving runtime and
domain boundaries between the apps.

The target apps are:

- `apps/product-factory-api`
- `apps/ecommerce-api`
- `apps/web`

The legacy Product-Agent backend becomes `product-factory-api`. The old
ecommerce-api backend becomes `ecommerce-api`. The old product-agent-ui
frontend becomes `web`.

`product-factory-api` and `ecommerce-api` remain separate backend runtimes.
They should not be merged into one backend during the monorepo migration.
`web` is UI-only and must not execute backend jobs directly.

## Target Repository Layout

```text
price-monitoring-platform/
  apps/
    product-factory-api/
    ecommerce-api/
    web/

  packages/
    contracts/
    shared-schemas/
    shared-python/

  scripts/
    dev/
    test/
    db/
    contracts/

  infra/
    local/
    docker/
    caddy/

  docs/
    architecture/
    decisions/
    runbooks/
```

Near-term layout variant:

```text
price-monitoring-platform/
  apps/
    product-factory-api/
    ecommerce-api/
    web/

  packages/
    contracts/

  scripts/
    dev/
    test/
    db/
    contracts/

  docs/
    architecture/
    decisions/
    runbooks/
```

In the near term, `packages/shared-schemas`, `packages/shared-python`, and
`infra/*` may exist as placeholders or may be deferred until there is a concrete
need. Placeholder directories should stay intentionally small and documented.

`packages/contracts` is the first shared package. It will hold OpenAPI snapshots
and later generated clients. `shared-python` and `shared-schemas` are future
packages and should not become dumping grounds for convenient cross-app imports.

## Runtime Architecture

The monorepo contains multiple runtimes:

- `product-factory-api`: backend runtime for Product Factory workflows.
- `ecommerce-api`: backend runtime for ecommerce catalog, source, monitoring,
  review, export, alert, and persistence workflows.
- `web`: browser UI runtime for operator workflows.

The backend apps remain independently startable, testable, configurable, and
deployable. Cross-app integration should happen through APIs, explicit handoff
artifacts, and contracts rather than direct imports across app internals.

Long-running execution should eventually move toward a durable worker/job
architecture, but this is not part of the first mechanical migration.

## App Responsibilities

`product-factory-api` owns:

- Product ingestion.
- Product page capture.
- LLM authoring.
- SEO metadata.
- Category and filter review.
- Deterministic product HTML rendering.
- OpenCart-ready product CSV generation.
- Product Factory artifacts.

`ecommerce-api` owns:

- Catalog data.
- Source URLs.
- Vendor sources.
- Source capture snapshots.
- Price observations.
- Monitoring runs.
- Review actions.
- Price update exports.
- Alert rules and events.
- Database migrations.

`web` owns:

- Operator console screens and client-side workflows.
- Browser routing and UI state.
- Calling backend APIs through explicit clients and contracts.

`web` must not directly mutate local files or run backend jobs except through
backend APIs.

## Domain Boundaries

Product Factory workflows create and prepare product content. Ecommerce
workflows manage catalog state, source discovery, price monitoring, review,
exports, and alerts.

`product-factory-api` must not own price monitoring runs or alerts.
`ecommerce-api` must not own LLM intro writing or product rendering internals.
`web` must remain an operator console and should not become a backend
orchestration runtime.

Direct imports between backend app internals are not allowed as an integration
strategy. Shared code must have a deliberate package boundary and a narrow,
documented purpose.

## Database Ownership

PostgreSQL is the `ecommerce-api` source of truth.

`ecommerce-api` owns the platform database and database migrations for catalog,
source URLs, vendor sources, source capture snapshots, price observations,
monitoring runs, review actions, price update exports, alert rules/events, and
related ecommerce data.

`product-factory-api` remains artifact/file-backed initially. It may later get
DB-backed job state, but it should not be forced into the ecommerce schema
during the first migration. If durable Product Factory database tables are
needed later, the platform should make an explicit follow-up decision about
using a separate schema in the same PostgreSQL instance or a separate database.

Cross-app direct database coupling should not be introduced casually.

## API and Contract Strategy

`packages/contracts` is the first shared package. It should mirror Product
Factory and Ecommerce OpenAPI snapshots after migration and later host generated
API clients.

The web app should depend on contracts or generated API clients rather than
hand-maintained assumptions where possible. Contract fixtures should support
integration tests without forcing one backend to import the other backend's
internals.

The Ecommerce API internal package is `ecommerce`. Product Factory still keeps
the internal `pipeline` package until a separate Product Factory refactor is
needed.

## Artifact Strategy

Local artifact storage remains acceptable now. Product Factory artifacts,
handoff files, rendered product outputs, CSV exports, source capture snapshots,
and monitoring exports may remain file-backed during the first migration.

Over time, artifact access should become API-mediated and metadata-backed. The
database should record artifact identity, ownership, state, and provenance where
that improves review, traceability, or durability. The first migration should
not introduce a new artifact service.

## Job and Worker Direction

Long-running execution should eventually move toward durable workers and job
queues with observable state, retry behavior, and clear ownership. That
direction applies to product generation, source capture, price monitoring,
exports, and other long-running tasks.

This worker/job direction is not part of the first mechanical migration. The
first migration should preserve existing runtime behavior and job execution
semantics.

## Frontend Strategy

`web` is the operator console for Product Factory and Ecommerce workflows. It
should call backend APIs and should not execute backend jobs directly.

Browser routes `/api` and `/commerce-api` remain stable during the first
migration. They should not be changed unless a future gateway redesign changes
that intentionally.

The frontend should move toward generated clients from `packages/contracts`
where practical, but generated clients are not introduced by the first
architecture documentation step.

## Environment/Configuration Strategy

Each app keeps its own runtime configuration during the first migration.
Configuration should remain explicit and app-scoped.

Root scripts coordinate development and test commands while preserving app
boundaries. Python root scripts use the monorepo virtual environment at
`.venv/`; on Windows they call `.venv\Scripts\python.exe` and fail clearly when
it is missing. Dependency setup remains app-aware and manual for now. Product
Factory now has minimal setuptools package metadata and editable install
support as Python project `product-factory`, while requirements files remain
the dependency install inputs. Its internal package remains `pipeline`.
Ecommerce API uses the internal package name `ecommerce`. There is still no
unified monorepo Python lockfile.

Secrets and environment files should not be centralized until the operational
model is clear. Generated runtime outputs, generated `products/` folders, raw
scraped HTML captures, local databases, virtual environments, and dependency
directories stay ignored by default.

## Testing Strategy

Each app keeps its own test suite. Root test scripts may later provide
convenient orchestration for all apps, but backend and frontend tests should
remain independently runnable.

Contracts should be tested at the boundaries:

- OpenAPI snapshots should be mirrored into `packages/contracts`.
- Contract fixtures should validate web client assumptions.
- Backend contract tests should verify public API shape.

For mechanical migration changes, run `git diff --check` and the app-local test
scripts when dependencies are already installed.

Root test scripts should use verbose output and skip tests marked for live
external services, live marketplace scraping, browser-live workflows, or other
slow external dependencies during stabilization.

## Phased Migration Roadmap

1. Phase 0: Create architecture docs and decisions.
2. Phase 1: Mechanically move/copy app folders into target app names.
3. Phase 2: Add root scripts and root README guidance.
4. Phase 3: Mirror OpenAPI snapshots into `packages/contracts`.
5. Phase 4: Clean up path references and documentation.
6. Phase 5: Stabilize tests, local development, and app boundaries.
7. Phase 6: Perform intentional refactors, including package renames when
   needed.

Phase 1 through Phase 4 are complete in the current layout:

- `apps/product-factory-api`
- `apps/ecommerce-api`
- `apps/web`
- `apps/product-factory-api/src`

The dedicated Ecommerce API package rename has been completed. Product Factory
still owns its `pipeline` package and now has minimal package metadata for
editable installs.

## Explicit Non-Goals

- Do not refactor business logic as part of the mechanical layout migration.
- Do not introduce Docker in the mechanical layout migration.
- Do not introduce workers in the mechanical layout migration.
- Do not introduce generated clients in the mechanical layout migration.
- Do not introduce database migrations in the mechanical layout migration.
- Do not merge the two backend runtimes.
- Do not change browser routes `/api` and `/commerce-api` during the first
  migration.
