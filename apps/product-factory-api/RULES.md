# Product Factory Runtime Input Rules

## Product identity contract

The current eTranoulis OpenCart integration uses MPN exclusively. GTIN, EAN,
UPC and barcode fields are outside the Product Factory output and publishing
contract. Their absence must never block validation or publishing.

For Phase 3, the six-digit OpenCart/ERP model is an internal key and is never
treated as the manufacturer MPN. Air-conditioner complete sets retain their
verified set MPN and their indoor/outdoor component models; a component cannot
silently replace a complete-set MPN.

This file defines active input validation and workflow rules for the template-triggered Product Factory runtime.

## Command Policy

- Run canonical operator and Codex commands from the repository root.
- Use the root virtual environment interpreter: `.\.venv\Scripts\python.exe`.
- Product Factory must be installed editable:
  `.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps`
- The internal Python package is `product_factory`.
- Do not use app-local virtual environments.
- Do not use bare `python` for repo commands except for creating `.venv` as documented in the root README.
- Do not use `py -3.13` as the canonical venv command.
- Prefer root scripts:
  - `.\scripts\dev\product-factory-api.ps1`
  - `.\scripts\test\product-factory-api.ps1` for operator-requested Product Factory broad verification
  - `.\scripts\test\fast.ps1` for operator-requested broad verification

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
- `url` must be supported by the runtime source-detection layer.
- `photos` defaults to `1`.
- `sections` defaults to `0`.
- `skroutz_status` defaults to `0`.
- `boxnow` defaults to `0`.
- `price` defaults to `0`.

If `model` is missing or not exactly 6 digits, fail with:
`Generation failed, provide 6-digit model`

## Default Flow

1. From repo root, run prepare:

```powershell
.\.venv\Scripts\python.exe -m product_factory.workflow prepare --model {model} --url "{url}" --photos {photos} --sections {sections} --skroutz-status {skroutz_status} --boxnow {boxnow} --price {price}
```

2. Inspect:
   - `work/{model}/llm/task_manifest.json`
   - `work/{model}/llm/intro_text.context.json`
   - `work/{model}/llm/intro_text.prompt.txt`
   - `work/{model}/llm/seo_meta.context.json`
   - `work/{model}/llm/seo_meta.prompt.txt`
   - `work/{model}/scrape/{model}.source.json`
   - `work/{model}/scrape/{model}.report.json`
3. Produce:
   - `work/{model}/llm/intro_text.output.txt`
   - `work/{model}/llm/seo_meta.output.json`
4. From repo root, run render:

```powershell
.\.venv\Scripts\python.exe -m product_factory.workflow render --model {model}
```

5. When render publishes `products/{model}.csv`, start a separate OpenCart publish phase from repo root:

```powershell
$env:CURRENT_JOB_PRODUCT_FILE = "apps/product-factory-api/products/{model}.csv"
bash apps/product-factory-api/tools/run_opencart_pipeline.sh {model}
```

`CURRENT_JOB_PRODUCT_FILE` must point to the current job's published CSV.

## Ownership

Local deterministic code owns:
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
- final CSV writing
- validation and publish reporting

The LLM stage writes only:
- `intro_text`
- `product.meta_description`
- `product.meta_keywords`

## Outputs

Prepare writes:
- `work/{model}/scrape/{model}.raw.html`
- `work/{model}/scrape/{model}.source.json`
- `work/{model}/scrape/{model}.normalized.json`
- `work/{model}/scrape/{model}.report.json`
- `work/{model}/llm/task_manifest.json`
- `work/{model}/llm/intro_text.context.json`
- `work/{model}/llm/intro_text.prompt.txt`
- `work/{model}/llm/seo_meta.context.json`
- `work/{model}/llm/seo_meta.prompt.txt`

Render writes:
- `work/{model}/candidate/{model}.csv`
- `work/{model}/candidate/{model}.normalized.json`
- `work/{model}/candidate/{model}.validation.json`
- `work/{model}/candidate/description.html`
- `work/{model}/candidate/characteristics.html`
- `products/{model}.csv` when validation passes
- `work/{model}/publish.run.json` when the post-render publish phase runs
- `work/{model}/upload.opencart.json` when OpenCart image upload runs
- `work/{model}/import.opencart.json` when OpenCart CSV import runs

Generated runtime folders are ignored by Git and must not be committed.

## Full-Pipeline Extraction Defaults

- Full-pipeline API/Telegram jobs default to `sections=20` as a cap, not an exact required count.
- A source with fewer than 20 available normal sections succeeds and extracts the available sections.
- Full-pipeline jobs default to whole-gallery extraction with `gallery_mode=all`.
- The numeric full-pipeline `photos` default is intentionally large for compatibility with numeric request/render fields; whole-gallery mode uses the actual downloaded count for final image output.
- Manual prepare defaults remain `photos=1`, `sections=0`, and no whole-gallery mode unless explicitly requested.
- Skroutz source/gallery URLs no longer skip the last gallery image. All extracted Skroutz gallery images remain eligible for normal gallery handling.

## Validation

- `work/{model}/candidate/{model}.validation.json` is the final machine-readable health report.
- Render success is owned by render; OpenCart publish reports its own status and does not flip render to failed.
- Prefer fixing Product Factory behavior instead of patching generated files by hand.

## Test Guidance

- Run `.\scripts\test\product-factory-api.ps1` only for operator-requested Product Factory broad verification.
- Run `.\scripts\test\fast.ps1` only for operator-requested broad fast coverage when dependencies are installed.
- For Codex maintenance or refactor tasks, do not run broad suites by default.
  Use focused checks that are relevant to changed files and keep automated
  runtime under 2 minutes.
- For template-triggered actual product workflow runs, follow the runtime
  workflow rules above.
- If dependencies are missing, report the root README setup command and stop.
