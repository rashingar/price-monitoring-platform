# 0004: Staged Package Renames

## Status

Accepted; completed.

This ADR is historical. The staged package rename policy was followed:
Ecommerce API now uses `ecommerce`, and Product Factory now uses
`product_factory`.

## Context

The monorepo migration included app folder renames and one known source-folder
normalization. It also exposes legacy internal Python package names that may not
match the final domain names.

Combining folder migration with Python import/package renames would increase
risk and make behavior changes harder to isolate.

## Decision

Stage internal Python package renames after the folder migration.

The pre-monorepo Product Factory source folder was renamed to `src/` as part of
the folder migration.

The Product Factory internal Python package was intentionally left unchanged
during the first folder migration and was later renamed in a dedicated
follow-up.

`ecommerce-api` now uses `src/ecommerce` after the dedicated follow-up rename.

Product Factory now uses `src/product_factory` after the dedicated follow-up
rename.

## Consequences

- The folder migration focused on filesystem placement and app naming.
- Ecommerce import path changes were reviewed and tested in a dedicated
  follow-up.
- Product Factory import path changes were reviewed and tested in a dedicated
  follow-up.
