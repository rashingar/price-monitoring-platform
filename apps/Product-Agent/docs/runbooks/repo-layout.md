# Repo Layout Runbook

## What stays in root

Keep these at repo root:
- control docs such as `AGENTS.md` and `RULES.md`
- `scraper/` for the runnable product pipeline code and tests
- `resources/` for shared support assets
- `products/` for final CSV deliverables
- `work/` for runtime artifacts
- `docs/` for active documentation
- `archive/` for historical references

## What belongs under `resources/`

Use `resources/` for shared support assets that the runtime reads directly:
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

## What belongs under `archive/`

Use `archive/` for historical or no-longer-active reference material:
- archived legacy prompts
- archived legacy rules
- other superseded references that should remain readable but should not be treated as active source of truth

Do not treat `archive/` files as current runtime inputs unless a runbook explicitly says otherwise.

## What belongs under `work/`

`work/` stays at repo root for runtime artifacts only.

Use `work/{model}/` for:
- scrape-stage artifacts
- prompt and LLM handoff files
- candidate outputs
- intermediate diagnostics tied to a specific active run

Do not place long-lived docs, checkpoints, or manual notes under `work/`.

## What belongs under `products/`

`products/` stays at repo root for final deliverable CSVs.

Use it for:
- final product CSV outputs intended for user delivery

Do not treat `products/` as a baseline for cleanup decisions beyond the runtime workflow rules already documented in `AGENTS.md` and `RULES.md`.
