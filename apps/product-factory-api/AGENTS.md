# Product-Agent Runtime Instructions

This file governs runtime and operator-facing execution behavior for the current product product_factory.

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

treat it as a request to run the full product_factory.

## End-To-End Flow

0. Use the repo virtual environment for every pipeline and test command.
   - On this Windows repo, the interpreter is `..\.venv\Scripts\python.exe` when running from `apps/product-factory-api/src`.
   - From repo root, use `.venv\Scripts\python.exe`.
   - Do not run pipeline commands, pytest, helper scripts, or dependency checks with bare `python`, global Python, `py`, or any interpreter outside `.venv`.
   - If `.venv` is missing or broken, stop and repair the repo environment before running the pipeline or tests.
1. Parse the template fields exactly as provided.
2. If `url` is a currently supported product URL recognized by the runtime source-detection layer, run:
   `..\.venv\Scripts\python.exe -m product_factory.workflow prepare --model {model} --url "{url}" --photos {photos} --sections {sections} --skroutz-status {skroutz_status} --boxnow {boxnow} --price {price}`
   Run from `apps/product-factory-api/src`.
   Execution ordering is strict:
   - never start `render` before `prepare` has finished successfully
   - never run `prepare` and `render` concurrently for the same model
   - after `prepare`, verify the updated scrape artifacts exist on disk before starting `render`
3. Read:
   - `work/{model}/llm/task_manifest.json`
   - `work/{model}/llm/intro_text.context.json`
   - `work/{model}/llm/intro_text.prompt.txt`
   - `work/{model}/llm/seo_meta.context.json`
   - `work/{model}/llm/seo_meta.prompt.txt`
   - `work/{model}/scrape/{model}.source.json`
   - `work/{model}/scrape/{model}.report.json`
4. The assistant is the LLM stage in this workflow.
5. Author these task outputs:
   - `work/{model}/llm/intro_text.output.txt`
   - `work/{model}/llm/seo_meta.output.json`
   Encoding rule:
   - both files must be UTF-8 text without BOM
   - do not write Greek LLM output through shell redirection, PowerShell inline heredocs, or any codepage-dependent console path
   - when editing manually in this runtime, use repo-native UTF-8 file writes or `apply_patch`
6. The assistant must write only the LLM-owned fields:
   - `product.meta_description`
   - `product.meta_keywords`
   - `intro_text`
7. Do not invent deterministic fields already owned by local code:
   - brand
   - mpn
   - manufacturer
   - name
   - meta_title
   - seo_keyword
   - category serialization
   - image paths
   - characteristics HTML
   - CTA block text/layout
   - presentation section titles
   - presentation section body copy
   - description HTML wrappers/classes/styles
   - final CSV structure
8. Output rules:
   - `intro_text.output.txt` must contain Greek text with only optional safe inline `<strong>...</strong>` emphasis
   - exactly one paragraph
   - 80-180 words
   - no HTML except `<strong>` and `</strong>` around important verified facts
   - no bullets
   - no CTA language
   - existing generated products/artifacts are not migrated; only newly authored or re-authored intro_text artifacts use emphasis
   - `seo_meta.output.json` must contain only:
     - `product.meta_description`
     - `product.meta_keywords`
   - `product.meta_keywords` must be a JSON array, not CSV text
9. Deterministic render ownership:
   - presentation sections are rendered from cleaned deterministic source sections
   - source wording is preserved after sanitation
   - source titles are kept when present
   - no section-copy generation belongs to the LLM
10. After both task outputs are written, run:
   `..\.venv\Scripts\python.exe -m product_factory.workflow render --model {model}`
   Run from `apps/product-factory-api/src`.
   Execution ordering is strict:
   - never start `render` before `prepare` has finished successfully
   - never run `prepare` and `render` concurrently for the same model
   - after `prepare`, verify the updated scrape artifacts exist on disk before starting `render`
11. After a successful render publish to `products/{model}.csv`, the runtime must start the repo-native OpenCart publish phase by invoking:
   `tools/run_opencart_pipeline.sh`
   Run from repo root with `CURRENT_JOB_PRODUCT_FILE` set to the exact `products/{model}.csv` path created in the current job.
12. If validation fails, debug the pipeline until the failure cause is understood then fixed and rerun until the output is complete.
   - if render fails with an LLM encoding error, treat it as a corrupted handoff artifact and rewrite the LLM output files as clean UTF-8 before rerunning
13. If the OpenCart publish phase warns or fails after render succeeds, keep the successful render outputs, report the publish status/stage/message clearly, and debug the publish phase separately.

## Validation Expectations

- Treat `work/{model}/candidate/{model}.validation.json` as the final machine-readable health report.
- Treat `products/{model}.csv` as the final deliverable path for the user, not as a baseline for comparison.
- Treat `work/{model}/publish.run.json` as the publish-phase status report.
- Treat `work/{model}/upload.opencart.json` and `work/{model}/import.opencart.json` as the stage reports when the post-render publish phase runs.
- Do not invalidate a successful render result because the post-render publish phase warned or failed.
- Prefer fixing pipeline issues over hand-editing generated output files.

## Completion Message

After the pipeline completes successfully, reply in chat with this fixed completion template first, then add any extra notes if needed:

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

- The `Category Filters` section must list only the category filters defined by `resources/mappings/filter_map.json` for the resolved taxonomy path.
- Do not dump the full characteristics table in place of category filters.
- Resolve each category filter value from the scraped source/spec data when possible.
- If a category filter exists in `resources/mappings/filter_map.json` but no source value exists, show it as `-`.
- The fixed completion template must always appear first in the final chat response for template-triggered pipeline runs.

## Source Scope

- The current runtime accepts product URLs supported by the repository's source-detection layer.
- At the time of this control-doc refresh, that includes:
  - Electronet product URLs
  - Skroutz product URLs
  - supported manufacturer product URLs already implemented in the codebase
- Do not invent unsupported provider behavior.

## Working Rules

- All commands that execute Python code must use the repo `.venv` interpreter. From `apps/product-factory-api/src`, use `..\.venv\Scripts\python.exe -m ...`; from repo root, use `.venv\Scripts\python.exe -m ...`.
- Tests must be run with the repo venv, for example from `apps/product-factory-api/src`: `..\.venv\Scripts\python.exe -m pytest -q`.
- Never use bare `python -m pytest`, `python -m product_factory.workflow`, `py -m ...`, or global interpreters for this repo.
- Keep all runtime artifacts in `work/{model}/`.
- Keep source scraper artifacts in `work/{model}/scrape/`.
- Keep task-specific LLM artifacts in `work/{model}/llm/`.
- Keep rendered outputs in `work/{model}/candidate/`.
- When the user asks for testing or debugging on a sample model, rerun the actual workflow instead of reasoning from stale files.
- If a bug appears on one product, fix it generically in the pipeline and verify against the committed regression samples under `src/product_factory/tests/fixtures/...`.
