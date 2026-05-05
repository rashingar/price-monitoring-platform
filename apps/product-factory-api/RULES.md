# Product-Agent Runtime Input Rules

This file defines runtime input validation rules for the template-triggered workflow.


## Trigger

Accepted input template:

```text
model:
url:
photos:
sections:
skroutz_status:
boxnow:
price:
```

Rules:
- `model` must be a confirmed 6-digit code.
- `url` must be a currently supported product URL recognized by the runtime source-detection layer.
- `photos` defaults to `1`.
- `sections` defaults to `0`.
- `skroutz_status` and `boxnow` boolean rule, defaults to `0`.
- `price` defaults to `0`.

If `model` is missing or not exactly 6 digits, fail with:
`Generation failed, provide 6-digit model`

Supported runtime URL scope is determined by the code-supported source-detection layer, not by a hardcoded single-source assumption in this file.

## Default Flow

All Python commands for this repo must use the checked-in repo virtual environment.

Windows command rules:
- From `apps/product-factory-api/src`, use `..\.venv\Scripts\python.exe -m ...`.
- From repo root, use `.venv\Scripts\python.exe -m ...`.
- Never use bare `python`, `py`, global Python, or any interpreter outside `.venv` for pipeline runs, tests, helper scripts, or dependency checks.
- If `.venv` is missing or broken, stop and repair the repo environment before running the pipeline or tests.

1. Run `..\.venv\Scripts\python.exe -m pipeline.workflow prepare ...` from `apps/product-factory-api/src`.
2. Read:
   - `work/{model}/llm/task_manifest.json`
   - `work/{model}/llm/intro_text.context.json`
   - `work/{model}/llm/intro_text.prompt.txt`
   - `work/{model}/llm/seo_meta.context.json`
   - `work/{model}/llm/seo_meta.prompt.txt`
3. Produce:
   - `work/{model}/llm/intro_text.output.txt`
   - `work/{model}/llm/seo_meta.output.json`
4. Run `..\.venv\Scripts\python.exe -m pipeline.workflow render --model {model}` from `apps/product-factory-api/src`.
5. When render publishes `products/{model}.csv`, the runtime must then start a separate OpenCart publish phase through `tools/run_opencart_pipeline.sh` from repo root with `CURRENT_JOB_PRODUCT_FILE` set to that exact published CSV path.
<!--
6. Inspect:
   - `work/{model}/candidate/{model}.validation.json`
   - `work/{model}/publish.run.json`
   - `work/{model}/upload.opencart.json`
   - `work/{model}/import.opencart.json`
-->
<!--
## Source Of Truth

Use these local files as runtime sources:
- `resources/mappings/catalog_taxonomy.json`
- `resources/schemas/electronet_schema_library.json`
- `resources/mappings/filter_map.json`
- `resources/templates/product_import_template.csv`
- `resources/templates/TEMPLATE_presentation.html`
- `resources/prompts/master_prompt+.txt`
- `resources/schemas/compact_response.schema.json`
-->
## Local Responsibilities

Local code owns:
- category serialization
- image path generation
- CTA URL insertion
- technical specs HTML rendering
- final description wrapper HTML
- final CSV writing
- deterministic brand / mpn / manufacturer / name
- deterministic meta title
- deterministic SEO URL
- validation and baseline comparison

## LLM Responsibilities

The LLM stage writes only:
- `intro_text`
- `product.meta_description`
- `product.meta_keywords`

## Outputs

Prepare stage writes:
- `work/{model}/scrape/{model}.raw.html`
- `work/{model}/scrape/{model}.source.json`
- `work/{model}/scrape/{model}.normalized.json`
- `work/{model}/scrape/{model}.report.json`
- `work/{model}/llm/task_manifest.json`
- `work/{model}/llm/intro_text.context.json`
- `work/{model}/llm/intro_text.prompt.txt`
- `work/{model}/llm/seo_meta.context.json`
- `work/{model}/llm/seo_meta.prompt.txt`

Render stage writes:
- `work/{model}/candidate/{model}.csv`
- `work/{model}/candidate/{model}.normalized.json`
- `work/{model}/candidate/{model}.validation.json`
- `work/{model}/candidate/description.html`
- `work/{model}/candidate/characteristics.html`
- `products/{model}.csv` when validation passes
- `work/{model}/publish.run.json` when the post-render publish phase runs
- `work/{model}/upload.opencart.json` when the publish phase reaches image upload
- `work/{model}/import.opencart.json` when the publish phase reaches CSV import

## Validation

- `work/{model}/candidate/{model}.validation.json` is the final machine-readable health report.
- Render success is owned only by render; the post-render publish phase reports its own status and does not flip render to failed.
- Prefer fixing pipeline behavior instead of patching generated files by hand.


