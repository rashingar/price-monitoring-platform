# Product Factory Runtime Instructions

This file governs template-triggered runtime and operator-facing execution behavior for the current Product Factory app. Keep it active.

## Command Policy

- Run canonical operator and Codex commands from the repository root.
- Use the root virtual environment interpreter: `.\.venv\Scripts\python.exe`.
- Product Factory must be installed editable before direct module commands are used:
  `.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps`
- The internal Python package is `product_factory`.
- Do not use app-local virtual environments.
- Do not use bare `python` for repo commands except for creating `.venv` as documented in the root README.
- Do not use `py -3.13` as the canonical venv command.
- Prefer root scripts:
  - `.\scripts\dev\product-factory-api.ps1`
  - `.\scripts\test\product-factory-api.ps1`
  - `.\scripts\test\fast.ps1` for operator broad verification

## Trigger

When the user sends a filled template in this exact shape:

```text
model:
url:
photos:
sections:
skroutz_status:
boxnow:
price:
```

treat it as a request to run the full Product Factory workflow.

## End-To-End Flow

1. Parse the template fields exactly as provided.
2. Confirm `url` is supported by the runtime source-detection layer.
3. From repo root, run prepare:

```powershell
.\.venv\Scripts\python.exe -m product_factory.workflow prepare --model {model} --url "{url}" --photos {photos} --sections {sections} --skroutz-status {skroutz_status} --boxnow {boxnow} --price {price}
```

Execution ordering is strict:
- never start `render` before `prepare` has finished successfully
- never run `prepare` and `render` concurrently for the same model
- after `prepare`, verify the updated scrape artifacts exist before starting `render`

4. Inspect these generated files:
   - `work/{model}/llm/task_manifest.json`
   - `work/{model}/llm/intro_text.context.json`
   - `work/{model}/llm/intro_text.prompt.txt`
   - `work/{model}/llm/seo_meta.context.json`
   - `work/{model}/llm/seo_meta.prompt.txt`
   - `work/{model}/scrape/{model}.source.json`
   - `work/{model}/scrape/{model}.report.json`
5. The assistant is the LLM stage. Write:
   - `work/{model}/llm/intro_text.output.txt`
   - `work/{model}/llm/seo_meta.output.json`
6. Write both LLM outputs as UTF-8 without BOM. Do not write Greek output through shell redirection, PowerShell inline heredocs, or codepage-dependent console paths.
7. From repo root, run render:

```powershell
.\.venv\Scripts\python.exe -m product_factory.workflow render --model {model}
```

8. After render publishes `products/{model}.csv`, run the OpenCart publish phase separately from repo root:

```powershell
$env:CURRENT_JOB_PRODUCT_FILE = "apps/product-factory-api/products/{model}.csv"
bash apps/product-factory-api/tools/run_opencart_pipeline.sh {model}
```

`CURRENT_JOB_PRODUCT_FILE` must point to the `products/{model}.csv` created by the current job.

9. If validation fails, debug the Product Factory workflow until the cause is understood, fix it generically, and rerun.
10. If OpenCart publish warns or fails after render succeeds, keep the successful render outputs, report publish status/stage/message clearly, and debug publish separately.

## Ownership Contract

The LLM stage owns only:
- `intro_text`
- `product.meta_description`
- `product.meta_keywords`

Deterministic code owns:
- brand
- mpn
- manufacturer
- name
- meta_title
- seo_keyword
- taxonomy/category serialization
- image paths
- characteristics HTML
- CTA block text and layout
- presentation section titles and body copy
- description HTML wrappers/classes/styles
- final CSV structure

## LLM Output Rules

- `intro_text.output.txt` must contain Greek text with only optional safe inline `<strong>...</strong>` emphasis.
- Use exactly one paragraph.
- Use 80-180 words.
- Use no HTML except `<strong>` and `</strong>` around important verified facts.
- Use no bullets and no CTA language.
- Existing generated products/artifacts are not migrated; only newly authored or re-authored intro text artifacts use emphasis.
- `seo_meta.output.json` must contain only `product.meta_description` and `product.meta_keywords`.
- `product.meta_keywords` must be a JSON array, not CSV text.

## Path Semantics

Product Factory runtime artifacts are app-owned and generated under:
- `work/{model}/scrape/`
- `work/{model}/llm/`
- `work/{model}/candidate/`
- `products/{model}.csv`

These generated folders/files are ignored by Git and must not be committed.

## Validation Expectations

- Treat `work/{model}/candidate/{model}.validation.json` as the final machine-readable health report.
- Treat `products/{model}.csv` as the final deliverable path, not as a comparison baseline.
- Treat `work/{model}/publish.run.json` as the publish-phase status report.
- Treat `work/{model}/upload.opencart.json` and `work/{model}/import.opencart.json` as OpenCart stage reports.
- Do not invalidate a successful render result because the post-render publish phase warned or failed.
- Prefer fixing Product Factory code over hand-editing generated output files.

## Completion Message

After the workflow completes successfully, reply with this fixed completion template first, then add any extra notes if needed:

- `Warnings`
- `Unresolved Source-Null Fields`
- `Category Filters`
- `Model`
- `Validation`
- `Taxonomy`
- `Product SEO`
  - `name`
  - `meta_title`
  - `meta_description`
  - `seo_keyword`
  - `product_url`

Rules for the completion message:
- `Category Filters` lists only filters defined by `resources/mappings/filter_map.json` for the resolved taxonomy path.
- Do not dump the full characteristics table in place of category filters.
- Resolve each category filter value from scraped source/spec data when possible.
- If a category filter exists but no source value exists, show `-`.
- The fixed completion template must always appear first for template-triggered runs.

## Source Scope

- The runtime accepts product URLs supported by the repository's source-detection layer.
- Current supported scope includes Electronet product URLs, Skroutz product URLs, and supported manufacturer product URLs implemented in the codebase.
- Do not invent unsupported provider behavior.

## Test Guidance

- Run future Product Factory checks from repo root.
- Use `.\scripts\test\product-factory-api.ps1` for Product Factory changes.
- Use `.\scripts\test\fast.ps1` for broad fast coverage when dependencies are installed.
- For Codex maintenance or refactor tasks, do not run broad suites by default.
  Use focused checks that are relevant to changed files and keep automated
  runtime under 2 minutes.
- For template-triggered actual product workflow runs, follow the runtime
  workflow rules above.
- If dependencies are missing, report the setup command from the root README instead of installing automatically unless the user explicitly asks.
