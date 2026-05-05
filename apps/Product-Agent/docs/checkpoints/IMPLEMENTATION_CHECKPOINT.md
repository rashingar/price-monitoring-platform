# Execution Checklist For Approved Implementation

- Create `docs/checkpoints/IMPLEMENTATION_CHECKPOINT.md` and record the approved implementation checklist there.
- Extend scraper reporting with per-field confidence diagnostics for key parsed fields.
- Capture DOM-selector traces for DOM-backed extraction paths so parse drift is visible in reports.
- Harden parser scoping so title, brand, specs, and key-spec extraction stay inside product content and exclude footer/menu/search noise.
- Fix deterministic brand and MPN extraction so the `233541` case resolves correctly to `LG` and `GSGV80PYLL`.
- Rebuild the final product `name` deterministically from parsed title plus verified naming-schema differentiators.
- Generate `meta_title` deterministically from the final canonical name and business rules.
- Keep `seo_keyword` deterministic from the final canonical name instead of the raw parsed title.
- Reduce the LLM contract to unresolved fields only: structured description content, `meta_description`, and `meta_keywords`.
- Add a repo-scoped orchestrator under `scraper/` that accepts both CLI flags and the filled template input via stdin/file.
- Make the orchestrator run the scraper first for Electronet URLs and emit prompt artifacts under `work/{model}/`.
- Add a post-LLM render step that consumes `work/{model}/llm_output.json` and writes candidate artifacts under `work/{model}/candidate/`.
- Add a validator that checks required CSV fields, header/order, encoding integrity, and mojibake/character corruption.
- Add field-by-field health comparison against `products/{model}.csv` when a baseline exists, starting with `products/233541.csv`.
- Add and update automated tests for diagnostics, deterministic naming/meta-title logic, orchestrator flow, validator behavior, and the `233541` end-to-end regression.
