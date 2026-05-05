# 0004: Staged Package Renames

## Status

Accepted

## Context

The monorepo migration includes app folder renames and one known source-folder
normalization. It also exposes legacy internal Python package names that may not
match the final domain names.

Combining folder migration with Python import/package renames would increase
risk and make behavior changes harder to isolate.

## Decision

Stage internal Python package renames after the mechanical monorepo migration.

Product-Agent's old `scraper/` folder should later be renamed to `src/` as part
of the mechanical migration.

The internal Python package `pipeline` should not be renamed during the first
migration.

`ecommerce-api` should keep `src/pricefetcher` initially. `src/pricefetcher` may
later become `src/ecommerce` in a dedicated refactor.

Do not combine folder migration with Python import/package rename.

## Consequences

- The first migration can focus on filesystem placement and app naming.
- Runtime behavior stays stable before semantic package renames.
- Import path changes can be reviewed and tested in dedicated follow-up work.
- The repository may temporarily contain legacy internal package names under
  new app names.
