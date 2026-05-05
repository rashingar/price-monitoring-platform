# 0004: Staged Package Renames

## Status

Accepted; Ecommerce API package rename completed in a dedicated follow-up.

## Context

The monorepo migration includes app folder renames and one known source-folder
normalization. It also exposes legacy internal Python package names that may not
match the final domain names.

Combining folder migration with Python import/package renames would increase
risk and make behavior changes harder to isolate.

## Decision

Stage internal Python package renames after the mechanical monorepo migration.

The legacy Product-Agent `scraper/` folder is renamed to `src/` as part of the
mechanical migration.

The internal Python package `pipeline` should not be renamed during the first
migration.

`ecommerce-api` now uses `src/ecommerce` after the dedicated follow-up rename.

Do not combine future Product Factory folder migration work with Python
import/package renames.

## Consequences

- The first migration focused on filesystem placement and app naming.
- Ecommerce import path changes were reviewed and tested in a dedicated
  follow-up.
- Product Factory can keep `pipeline` until a separate refactor justifies a
  package rename.
