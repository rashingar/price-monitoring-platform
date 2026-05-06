# Repo Layout Runbook

## App Layout

Product Factory lives under `apps/product-factory-api`. Run commands from the
repository root, but treat these paths as app-owned:

- `apps/product-factory-api/AGENTS.md` and `apps/product-factory-api/RULES.md`
  for active runtime control rules
- `apps/product-factory-api/src/product_factory/` for runtime code and tests
- `apps/product-factory-api/resources/` for runtime support assets
- `apps/product-factory-api/docs/` for active documentation
- `apps/product-factory-api/work/` for generated runtime artifacts
- `apps/product-factory-api/products/` for generated CSV deliverables
- `apps/product-factory-api/tools/` for maintenance and OpenCart helpers

## What belongs under `resources/`

Use `apps/product-factory-api/resources/` for shared support assets that the
runtime reads directly:
- `resources/mappings/` for taxonomy, filter, naming, and manufacturer mapping data
- `resources/schemas/` for schema libraries and response schemas
- `resources/templates/` for CSV and HTML template assets
- `resources/prompts/` for prompt source files

Do not place runtime outputs or one-off notes under `resources/`.

## What belongs under `docs/`

Use `docs/` for active project documentation:
- `docs/audits/` for evidence-based repo and health audits
- `docs/runbooks/` for operator-facing guidance like this layout runbook
- `docs/specs/` for active design and implementation specs
- `docs/checkpoints/` for active planning checkpoints

Do not use `docs/` for generated runtime artifacts.

## What belongs under `work/`

`apps/product-factory-api/work/` is for runtime artifacts only.

Use `work/{model}/` for:
- scrape-stage artifacts
- prompt and LLM handoff files
- candidate outputs
- intermediate diagnostics tied to a specific active run

Do not place long-lived docs, checkpoints, or manual notes under `work/`.

## What belongs under `products/`

`apps/product-factory-api/products/` is for final deliverable CSVs.

Use it for:
- final product CSV outputs intended for user delivery

Do not treat `products/` as a baseline for cleanup decisions beyond the runtime workflow rules already documented in `AGENTS.md` and `RULES.md`.
