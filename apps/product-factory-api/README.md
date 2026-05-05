# product-factory-api

`product-factory-api` is the Product Factory backend runtime. It contains the
old Product-Agent Python pipeline under `src/pipeline` and produces
OpenCart-ready product CSVs from supported product pages. It captures source
product data, normalizes taxonomy, specifications, images, and category
filters, prepares the small LLM-owned copy fields, renders deterministic
product HTML, validates the candidate output, and can hand the final CSV/images
to the repo OpenCart publishing tools.

The Python project/install name is `product-factory`. The internal Python
package remains `pipeline` during this staged migration.

The project is intentionally repo-local. Runtime code, shared product data, generated workspaces, and final deliverables are kept in separate directories so generated output does not become source material.

## Repository Layout

- `src/` contains the Python pipeline package, FastAPI backend, job runner, providers, and tests.
- `resources/` contains shared runtime assets: taxonomy mappings, filter maps, schema libraries, prompt templates, CSV templates, and HTML templates.
- `work/{model}/` contains generated runtime artifacts for a product run.
- `products/` contains final CSV deliverables.
- `docs/` contains active operator, API, contract, runbook, audit, and design documentation.
- `archive/` contains historical material that should not be treated as active runtime guidance.
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

- Copy `.env.example` to `.env` and set `OPENAI_API_KEY` when using OpenAI-backed authoring.
- Copy `opencart.env.example` to `.secrets/opencart.env` when using OpenCart publishing.
- Keep real secrets out of version control.

## Local API

The local backend is a FastAPI app under `src/pipeline/api`. Start it through
the root script after the editable install:

```powershell
.\scripts\dev\product-factory-api.ps1
```

The installed console script points to `pipeline.dev.start:main`, so the direct
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

Run tests through the root script with the repo virtual environment:

```powershell
.\scripts\test\product-factory-api.ps1
```

For faster targeted checks, see `docs/runbooks/testing.md`.

## Runtime Outputs

Generated artifacts belong under `work/{model}/`. Final deliverable CSVs belong under `products/`.

The final machine-readable validation report for a product run is `work/{model}/candidate/{model}.validation.json`. The final user-facing CSV deliverable is `products/{model}.csv`.

Prefer fixing pipeline behavior over hand-editing generated files.

## More Documentation

- `docs/api.md` describes the active local API and contract workflow.
- `docs/contracts/openapi.product-agent.json` is the canonical OpenAPI snapshot.
- `AGENTS.md` and `RULES.md` define runtime operator behavior for template-triggered pipeline work.
- `archive/legacy/runtime_legacy.md` preserves old README workflow detail and CLI notes removed from the root README.
