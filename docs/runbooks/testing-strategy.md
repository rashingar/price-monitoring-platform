# Testing Strategy

This runbook defines the repository-wide test categories and separates operator
broad verification from the default Codex verification policy. The goal is to
keep routine Codex checks targeted, deterministic, local, and quick while
preserving broader coverage for explicit operator use.

## Operator Broad Verification

Run this from the repository root for human/operator broad fast verification:

```powershell
.\scripts\check\hygiene.ps1
.\scripts\test\fast.ps1
```

`hygiene.ps1` checks unsafe tracked files, accidental app submodules, contract
mirrors, generated web API types when web dependencies exist, and whitespace.
`fast.ps1` runs Product Factory fast tests, Ecommerce API fast tests, web fast
tests, and mirrored OpenAPI contract checks in sequence. Both return nonzero on
failed required checks.

For an aggregate local check, run:

```powershell
.\scripts\check\all.ps1
```

It runs hygiene, contracts, generated web API type checks when
`apps/web/node_modules` exists, and fast tests when backend and web dependencies
exist.

## Codex Default Verification

For normal Codex prompts, run only small, targeted checks relevant to changed
files and keep total automated check runtime under 2 minutes. Always run:

```powershell
git diff --check
git status --short
```

Also run focused grep/search checks for changed naming, routing, and doc areas.
Use focused tests only when the changed files clearly map to them:

- Run `.\scripts\contracts\check.ps1` only when API contracts, routes, or
  schemas changed.
- Run `.\scripts\contracts\check-web-types.ps1` only when contracts or
  generated web API types changed and `apps\web\node_modules` is available.
- Run one relevant pytest file or test node for clearly mapped Python changes.
- Run one relevant Vitest file for clearly mapped web changes.

Do not run `.\scripts\test\fast.ps1`,
`.\scripts\test\product-factory-api.ps1`, `.\scripts\test\ecommerce-api.ps1`,
or `.\scripts\test\web.ps1` by default in Codex prompts. If broader
verification is useful, list the exact command under `Manual verification
needed` instead of running it automatically.

## App Commands

```powershell
.\scripts\check\hygiene.ps1
.\scripts\check\hygiene.ps1 -Staged
.\scripts\check\all.ps1
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

Fast tests belong in the operator broad verification command when they are
deterministic and local.
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
definitions and `apps/product-factory-api/src/product_factory/tests/conftest.py` for
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

## Non-Default Tests

Do not delete tests casually. If a test is too slow, external, e2e-only, or
diagnostic-only for the default fast path, mark it with the appropriate marker
and keep the reason close to the test or owning app runbook.

Future Codex prompts should follow the targeted policy in
[Codex Default Verification](#codex-default-verification). Run
`.\scripts\test\fast.ps1`, `slow`, `external`, `e2e`, or `legacy` selections
only when the operator explicitly asks or the change needs that scope.

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
