# Testing Strategy

This runbook defines the repository-wide test categories and the default
Codex-safe command for local verification. The goal is to keep routine checks
deterministic, local, and quick while preserving slower and live coverage for
explicit use.

## Default Command

Run this from the repository root for normal Codex prompts and local pre-commit
checks:

```powershell
.\scripts\test\fast.ps1
```

`fast.ps1` runs Product Factory fast tests, Ecommerce API fast tests, web fast
tests, and mirrored OpenAPI contract checks in sequence. It returns nonzero on
the first failed required check.

## App Commands

```powershell
.\scripts\test\product-factory-api.ps1
.\scripts\test\ecommerce-api.ps1
.\scripts\test\web.ps1
.\scripts\contracts\check.ps1
.\scripts\contracts\check-web-types.ps1
```

The Python scripts use the root `.venv\Scripts\python.exe`; they do not use
app-local virtual environments and do not install dependencies automatically.
The web script runs from `apps\web` and expects `node_modules` to already exist.
All test scripts use verbose output. `scripts\contracts\check.ps1` also checks
that generated web API types are current with the mirrored OpenAPI contracts.

## Standard Categories

- `fast`: local, deterministic, no network, no live browser, no external
  service, and no database service unless it uses an in-memory or temporary DB.
- `contract`: API, OpenAPI, schema, fixture, or artifact contract checks.
- `smoke`: shallow health, import, route, or page checks.
- `integration`: local multi-module or service-style tests using temp files,
  local fakes, fake browsers, in-process clients, or temporary databases.
- `slow`: intentionally slower tests.
- `external`: tests requiring live websites, network, marketplace pages,
  external APIs, real browser downloads, credentials, or real services.
- `e2e`: full workflow, browser, or operator-flow tests.
- `legacy`: tests preserved but not trusted as part of fast default because they
  are obsolete, flaky, unclear, or coupled to old behavior.

Do not invent extra broad categories for routine test selection. Use the
categories above consistently and keep app-specific tags secondary.

## Fast Tests

Fast tests belong in the default command when they are deterministic and local.
Good fast tests include pure unit checks, API route smoke checks using TestClient
and temporary files, OpenAPI/schema snapshot checks, jsdom component smoke
checks with mocked backend responses, local fixture contract checks, and local
SQLite/temp-file integration tests that complete quickly.

Fast tests must not call live marketplace pages, scrape external websites,
download real browsers, call OpenAI or other external APIs, require OpenCart,
require PostgreSQL or another running service, depend on credentials, or perform
full browser/operator workflows. Mark those tests `external`, `slow`, and/or
`e2e` as appropriate.

## Marking Guidance

For pytest suites, prefer file-level or collection-time markers when a whole
module has the same character. Use test-level markers for selected slow,
external, e2e, or legacy cases inside an otherwise fast file.

Product Factory uses `apps/product-factory-api/src/pytest.ini` for marker
definitions and `apps/product-factory-api/src/pipeline/tests/conftest.py` for
suite classification.

Ecommerce API uses `apps/ecommerce-api/pyproject.toml` for marker definitions
and `apps/ecommerce-api/tests/conftest.py` for suite classification.

Web uses package scripts under `apps/web/package.json`:

```powershell
npm run test:fast
npm run test:contracts
npm run test:smoke
npm run check:api-types
```

The web fast suite is limited to mocked contract and smoke tests under
`apps/web/src/test/contracts` and `apps/web/src/test/smoke`.
Generated web API types are refreshed with
`.\scripts\contracts\generate-web-types.ps1` and checked with
`.\scripts\contracts\check-web-types.ps1`. The generated files under
`apps/web/src/api/generated` are committed and should not be edited by hand.

## Legacy Tests

Do not delete tests casually. If a test is obsolete, flaky, unclear, or coupled
to old behavior, mark it `legacy` first and document it in
`docs/runbooks/legacy-test-cleanup-candidates.md`. Delete later only when the
team has confirmed that it is generated, duplicate, impossible after the
monorepo/rename changes, or no longer useful.

Future Codex prompts should run `.\scripts\test\fast.ps1` unless the task
explicitly requires broader coverage. Run `slow`, `external`, `e2e`, or
`legacy` selections only when the change needs that scope.

## Troubleshooting

If the root Python environment is missing, create it and install only the app
dependencies you need. Python 3.11 or newer is required; the `python` command
must resolve to Python 3.11+. If `python` is not found or is too old, install a
supported Python version and reopen PowerShell.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r apps\product-factory-api\requirements.txt
.\.venv\Scripts\python.exe -m pip install -e apps\product-factory-api --no-deps
.\.venv\Scripts\python.exe -m pip install -r apps\ecommerce-api\requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e apps\ecommerce-api --no-deps
```

If you intentionally manage multiple Python versions with the Windows `py`
launcher, you may use a supported version explicitly, for example
`py -3.12 -m venv .venv`. The default operator command remains
`python -m venv .venv`.

If web dependencies are missing:

```powershell
Push-Location apps\web
npm ci
Pop-Location
```

Do not commit generated artifacts, raw provider HTML captures, database files,
database dumps or backups, `.env` files, `.venv`, `node_modules`, `work/`,
`output/`, `products/`, or secrets.
