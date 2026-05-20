# product-factory-api

`product-factory-api` is the Product Factory backend runtime. It contains the
Product Factory Python pipeline under `src/product_factory` and produces
OpenCart-ready product CSVs from supported product pages. It captures source
product data, normalizes taxonomy, specifications, images, and category
filters, prepares the small LLM-owned copy fields, renders deterministic
product HTML, validates the candidate output, and can hand the final CSV/images
to the repo OpenCart publishing tools.

The Python project/install name is `product-factory`. The internal Python
package is `product_factory`.

The project is intentionally repo-local. Runtime code, shared product data, generated workspaces, and final deliverables are kept in separate directories so generated output does not become source material.

## Repository Layout

- `src/product_factory/` contains the Python package, FastAPI backend, job runner, providers, and tests.
- `resources/` contains shared runtime assets: taxonomy mappings, filter maps, schema libraries, prompt templates, CSV templates, and HTML templates.
- `work/{model}/` contains generated runtime artifacts for a product run.
- `products/` contains final CSV deliverables.
- `docs/` contains active operator, API, contract, runbook, audit, and design documentation.
- `tools/` contains OpenCart publishing helpers and supporting maintenance scripts.

See `docs/runbooks/repo-layout.md` for the repo layout rules.

## Setup

Use the repo virtual environment for all Python commands after it exists.
Pipeline commands, tests, helper scripts, and dependency checks must run through
the root `.venv`; do not use bare `python`, `py`, a global interpreter, or an
app-local virtual environment for this repo.

From repo root on Windows:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt
.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps
.\.venv\Scripts\python.exe -m playwright install chromium
```

Python 3.11 or newer is required. The `python` command must resolve to Python
3.11+. If `python` is not found or is too old, install a supported Python
version and reopen PowerShell.

`pyproject.toml` provides minimal setuptools package metadata, src-layout
package discovery, and the `product-factory-api` console script. Dependencies
are still installed from `requirements.txt` for now. `requirements-lock.txt` is
the pinned dependency record and should change only when dependencies
intentionally change.

Optional local configuration:

- Copy the repo-root `.env.example` to repo-root `.env`.
- Set `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENCART_*` values there when using
  OpenAI-backed authoring or OpenCart publishing.
- Do not create app-local `.env` files for new setups. Existing app-local
  `.env` and `.secrets/opencart.env` files are deprecated compatibility
  fallback only.
- OS env vars override repo-root `.env`; repo-root `.env` overrides deprecated
  app-local files. Diagnostics print key names only, never secret values.

## Local API

The local backend is a FastAPI app under `src/product_factory/api`. Start it through
the root script after the editable install:

```powershell
.\scripts\dev\product-factory-api.ps1
```

The installed console script points to `product_factory.dev.start:main`, so the direct
equivalent is:

```powershell
.\.venv\Scripts\product-factory-api.exe --host 127.0.0.1 --port 8000 --reload
```

Useful local URLs:

- API health: `http://127.0.0.1:8000/api/health`
- Interactive docs: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

API endpoints, request/response contracts, snapshot rules, and contract test commands live in `docs/api.md`.

## Development Checks

Run Product Factory-only Codex checks through the targeted root script with the
repo virtual environment:

```powershell
.\scripts\test\codex-product-factory.ps1
```

Run broader Product Factory fast verification when explicitly requested:

```powershell
.\scripts\test\product-factory-api.ps1
```

Runtime tests are opt-in via `.\scripts\test\product-factory-runtime.ps1`.
Golden tests are deterministic fixture regressions via
`.\scripts\test\product-factory-golden.ps1`. For targeted checks, see
`docs/runbooks/testing.md`.

## Runtime Outputs

Generated artifacts belong under `work/{model}/`. Final deliverable CSVs belong under `products/`.

The final machine-readable validation report for a product run is `work/{model}/candidate/{model}.validation.json`. The final user-facing CSV deliverable is `products/{model}.csv`.

Prefer fixing pipeline behavior over hand-editing generated files.

## Full-Pipeline Extraction Defaults

Full-pipeline jobs from the API and Telegram default to `sections: 20` as a
safe maximum cap. The cap is not an exact requirement: sources with fewer normal
presentation sections still succeed and use the available sections.

Full-pipeline jobs default to `gallery_mode: "all"` so Product Factory downloads
the whole available gallery. The numeric `photos` default is `100` for
compatibility with existing request and render contracts that require a numeric
photo field; in whole-gallery mode the final image list is based on the number
of images actually downloaded.

Manual prepare defaults remain `photos: 1`, `sections: 0`, and no whole-gallery
mode unless the caller explicitly sets `gallery_mode: "all"`.

For Skroutz source URLs, Product Factory no longer skips the last extracted
gallery image. All extracted Skroutz gallery images remain eligible for the
normal gallery mode/photo cap, deduplication, download success, and energy-label
insertion behavior.

## More Documentation

- `docs/api.md` describes the active local API and contract workflow.
- `docs/contracts/openapi.product-factory.json` is the canonical OpenAPI snapshot.
- `AGENTS.md` and `RULES.md` define runtime operator behavior for template-triggered pipeline work.
