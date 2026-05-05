# 0001: Monorepo with Separate Apps

## Status

Accepted

## Context

The Price Monitoring Platform is being reorganized from separate legacy
projects into one repository. The platform includes a Product Factory backend,
an Ecommerce backend, and a web operator console.

The repository needs better coordination for contracts, documentation, root
scripts, migration sequencing, and Codex visibility. At the same time, the
backend domains have different responsibilities and should not be collapsed
into one runtime.

## Decision

Adopt a monorepo with separate apps and separate runtimes.

The platform will use a monorepo to improve coordination, contracts, scripts,
and Codex visibility, while preserving clean runtime boundaries.

The target app layout is:

- `apps/product-factory-api`
- `apps/ecommerce-api`
- `apps/web`

`product-factory-api` and `ecommerce-api` remain separate backend runtimes.
`web` remains a frontend application and must interact with backend work through
backend APIs.

## Consequences

- The repository can centralize architecture decisions, runbooks, shared
  contracts, and root orchestration scripts.
- Each app remains independently startable, testable, configurable, and
  deployable.
- Cross-app integration must happen through APIs, explicit handoff artifacts,
  or shared contracts.
- Direct imports across app internals are not an acceptable shortcut.
- The monorepo can add shared packages only when their boundaries are clear.

## Alternatives Considered

### Keep three independent repos

This would preserve isolation, but it would keep contract drift, documentation
spread, migration coordination, and cross-repo visibility problems.

### Merge everything into one backend

This would reduce the number of runtimes, but it would blur domain ownership,
increase coupling, and make the migration riskier than necessary.

### Adopt monorepo with separate apps

This preserves runtime boundaries while improving coordination. This is the
accepted approach.
