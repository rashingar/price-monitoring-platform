# Monorepo Migration

Status: complete.

This runbook is a historical record of the migration from separate legacy
folders into the current Price Monitoring Platform monorepo. Current operator
guidance lives in:

- [Current Architecture](../architecture/current-architecture.md)
- [Operator Startup](operator-startup.md)
- [Codex Workflow](codex-workflow.md)
- [Testing Strategy](testing-strategy.md)

Monorepo migration is complete. New work should start from current
architecture, current contracts, and current operator runbooks.

## Completed Outcomes

- Final app folders are in place:
  - `apps/product-factory-api`
  - `apps/ecommerce-api`
  - `apps/web`
- Product Factory source lives under `apps/product-factory-api/src`.
- Product Factory Python project/install name is `product-factory`.
- Product Factory internal Python package is `product_factory`.
- Ecommerce API internal Python package is `ecommerce`.
- Web browser proxy routes remain stable:
  - `/api`
  - `/commerce-api`
- OpenAPI snapshots are mirrored under `packages/contracts`.
- Generated web API type scaffolding is committed under
  `apps/web/src/api/generated`.
- Root setup, dev, test, contract, and hygiene scripts are available.
- Fast test scripts use verbose output and exclude runtime, Ecommerce
  `db_integration`, PostgreSQL-required, slow, external, e2e, and legacy tests
  by default where applicable.
- Hygiene checks cover unsafe paths, app gitlinks, contract mirrors, generated
  web types when dependencies are installed, and whitespace.

## Historical Phase Summary

1. Architecture documentation and decisions were added.
2. Legacy folders were mechanically placed under the final `apps/*` layout.
3. Root scripts and first-run documentation were added.
4. Product Factory and Ecommerce OpenAPI snapshots were mirrored into
   `packages/contracts`.
5. Generated web API type scaffolding was added from the mirrored contracts.
6. Ecommerce API package naming was finalized as `ecommerce`.
7. Product Factory packaging was added as `product-factory`.
8. Product Factory internal package naming was finalized as `product_factory`.
9. Primary docs were converted from migration-oriented notes to current-state
   operator documentation.

## Historical Notes

Older decisions and archived app docs may mention pre-migration names, staged
rename plans, or transitional constraints. Treat those references as historical
context only. Do not use them for current setup, import paths, package names, or
operator commands.

Current commands and policies are maintained in the root README and the current
runbooks linked above.
