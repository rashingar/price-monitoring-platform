# Legacy Runtime Notes

This file preserves old README material that is no longer part of the root setup guide. Treat it as historical operator context, not as the preferred onboarding path.

For active setup, use `README.md`. For active API endpoints and contracts, use `docs/api.md`.

## Removed Entrypoints

The old README explicitly called out removed runtime entrypoints:

- `product_factory.cli`
- `scraper/product_factory/full_run.py`
- `scraper/product_factory/services/run_service.py`
- `scraper/product_factory/services/run_execution.py`

If one of these old entrypoints is needed for archaeology, restore it from git history intentionally. Do not infer runnable behavior from this archive file.

## CLI-First Workflow Notes

The root README no longer documents the prepare/render workflow as the main onboarding path. The historical operator flow used `product_factory.workflow` from `scraper/`.

Prepare example:

```powershell
cd scraper
..\.venv\Scripts\python.exe -m product_factory.workflow prepare `
  --model 234385 `
  --url "https://www.electronet.gr/..." `
  --photos 5 `
  --sections 0 `
  --skroutz-status 1 `
  --boxnow 0 `
  --price 798
```

Render example:

```powershell
cd scraper
..\.venv\Scripts\python.exe -m product_factory.workflow render --model 234385
```

Historical template options on `product_factory.workflow` also supported `--template-file` and `--stdin`.

## Manual LLM Handoff Notes

The old README documented manual task files under `work/{model}/llm/`:

- `task_manifest.json`
- `intro_text.context.json`
- `intro_text.prompt.txt`
- `seo_meta.context.json`
- `seo_meta.prompt.txt`
- `intro_text.output.txt`
- `seo_meta.output.json`

The LLM-owned fields were:

- `intro_text`
- `product.meta_description`
- `product.meta_keywords`

The old output rules were:

- `intro_text.output.txt` contains plain Greek text only.
- The intro text is exactly one paragraph, 80-180 words, no HTML, no bullets, and no CTA language.
- `seo_meta.output.json` contains only `product.meta_description` and `product.meta_keywords`.
- `product.meta_keywords` is a JSON array.
- Both output files are UTF-8 without BOM.

## Internal Runtime Detail Removed From README

The old README included internal stage notes:

- `prepare` sequenced initialization, source acquisition, and preparation.
- Source acquisition owned source detection, provider bootstrap, fetch, raw snapshot provenance, provider parsing, normalization, and gallery acquisition.
- Preparation owned taxonomy resolution, manufacturer enrichment, presentation/Besco preparation, schema matching, deterministic prepared-context assembly, and artifact persistence.
- The internal stage name used `source_acquisition`, while artifacts were still written under `work/{model}/scrape/`.

The old README also listed deterministic render ownership:

- wrappers, classes, styles, CTA layout, and image wiring are code-owned
- source section titles are preserved when present
- source wording is preserved after sanitation
- render does not rewrite or summarize deterministic section copy
- section-copy generation is not an LLM task

## Old Artifact Lists

Prepare-stage artifacts previously listed in README:

- `work/{model}/scrape/{model}.raw.html`
- `work/{model}/scrape/{model}.source.json`
- `work/{model}/scrape/{model}.normalized.json`
- `work/{model}/scrape/{model}.report.json`
- `work/{model}/llm/task_manifest.json`
- `work/{model}/llm/intro_text.context.json`
- `work/{model}/llm/intro_text.prompt.txt`
- `work/{model}/llm/seo_meta.context.json`
- `work/{model}/llm/seo_meta.prompt.txt`

Render-stage artifacts previously listed in README:

- `work/{model}/candidate/{model}.csv`
- `work/{model}/candidate/{model}.normalized.json`
- `work/{model}/candidate/{model}.validation.json`
- `work/{model}/candidate/description.html`
- `work/{model}/candidate/characteristics.html`
- `products/{model}.csv`
- `work/{model}/publish.run.json`
- `work/{model}/upload.opencart.json`
- `work/{model}/import.opencart.json`

## Old Publish And OpenCart Notes

The old README described the post-render publish handoff through `tools/run_opencart_pipeline.sh`. It also documented OpenCart config resolution through `tools/opencart_config.py` with these inputs:

- `OPENCART_STORE_BASE`
- `OPENCART_ADMIN_PATH`
- `OPENCART_ADMIN_USER`
- `OPENCART_ADMIN_PASS`
- `OPENCART_IMPORT_PROFILE`

The legacy resolution order was:

1. Explicit CLI arguments
2. Process environment
3. `.secrets/opencart.env`
4. Central defaults in `tools/opencart_config.py`

## API Fallback Commands Removed From README

The root README now documents only the repo-native API start command. The old README also showed direct `uvicorn` usage:

```powershell
cd scraper
..\.venv\Scripts\python.exe -m uvicorn product_factory.api.app:app --host 127.0.0.1 --port 8000 --reload
```

It also named the internal API worker CLI:

```powershell
cd scraper
..\.venv\Scripts\python.exe -m product_factory.jobs.run_product_agent_job --job-id <job_id>
```

That worker is an implementation detail for the API supervisor.

## Old Job Runner Notes

The old README included operational details for the job runner:

- `PRODUCT_AGENT_MAX_JOB_WORKERS` defaulted to `1`.
- `PRODUCT_AGENT_JOB_TERMINATE_TIMEOUT_SECONDS` defaulted to `30`.
- Queued jobs could be cancelled before execution.
- Running jobs received graceful process termination first.
- If the child process did not exit before the timeout, the backend killed the process tree.
- Terminal statuses were `succeeded`, `failed`, `cancelled`, and `killed`.

## Old Section And SEO Policy Notes

The old README listed section policy:

- if presentation source sections were missing entirely and sections were requested, render failed
- if usable section count was `0` and sections were requested, render failed
- if sections were weak or exactly one requested section was missing, render warned and continued with fewer sections

The old README listed SEO policy:

- `meta_description` came from `seo_meta.output.json`
- `meta_keywords` came from `seo_meta.output.json`
- render normalized meta keywords so brand/model were present and duplicate singular/plural variants were collapsed
