# Testing Strategy

This runbook defines the repository-wide test categories and separates operator
broad verification from the default Codex verification policy. The goal is to
keep routine Codex checks targeted, deterministic, local, and quick while
preserving broader coverage for explicit operator use.

## Codex-Safe Root Fast Verification

Run this from the repository root for Codex-safe aggregate fast verification:

```powershell
.\scripts\check\hygiene.ps1
.\scripts\test\fast.ps1
```

`hygiene.ps1` checks unsafe tracked files, accidental app submodules, contract
mirrors, generated web API types when web dependencies exist, and whitespace.
`fast.ps1` first enforces golden snapshot hygiene and fast marker hygiene, then
runs Product Factory fast tests, Ecommerce API fast tests, web fast tests, and
mirrored OpenAPI contract checks in sequence. It is Codex-safe because delegated
app scripts exclude runtime, Ecommerce `db_integration`, `postgres_required`,
external, e2e, legacy, and slow checks where applicable. Fast marker hygiene
prevents runtime, `db_integration`, `postgres_required`, external, e2e, legacy,
or slow tests from leaking into root fast. Both return nonzero on failed
required checks.

For an aggregate local check, run:

```powershell
.\scripts\check\all.ps1
```

It runs hygiene, contracts, generated web API type checks when
`apps/web/node_modules` exists, and fast tests when backend and web dependencies
exist.

## Codex Default Verification

For normal Codex prompts, run small, targeted checks relevant to changed files
and keep total automated check runtime under 2 minutes when possible. When a
prompt touches only one backend app, prefer that app's Codex entrypoint:

```powershell
.\scripts\test\codex-product-factory.ps1
.\scripts\test\codex-ecommerce.ps1
```

Always run:

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

Root `.\scripts\test\fast.ps1` is now a Codex-safe aggregate fast verification
command with snapshot hygiene and fast marker hygiene before app/web/contract
checks. App-specific scripts are still preferred when the change touches only
one app. Runtime, Ecommerce `db_integration`, PostgreSQL-required, and
full-suite selections remain manual unless explicitly requested.

## App Commands

```powershell
.\scripts\check\hygiene.ps1
.\scripts\check\hygiene.ps1 -Staged
.\scripts\check\all.ps1
.\scripts\test\check-snapshots.ps1
.\scripts\test\check-fast-marker-hygiene.ps1
.\scripts\test\codex-product-factory.ps1
.\scripts\test\codex-ecommerce.ps1
.\scripts\test\product-factory-api.ps1
.\scripts\test\ecommerce-api.ps1
.\scripts\test\product-factory-runtime.ps1
.\scripts\test\product-factory-golden.ps1
.\scripts\test\ecommerce-runtime.ps1
.\scripts\test\ecommerce-golden.ps1
.\scripts\test\ecommerce-db-contract.ps1
.\scripts\test\ecommerce-db-integration.ps1
.\scripts\test\ecommerce-postgres.ps1
.\scripts\test\web.ps1
.\scripts\contracts\check.ps1
.\scripts\contracts\check-web-types.ps1
```

The Python scripts use the root `.venv\Scripts\python.exe`; they do not use
app-local virtual environments and do not install dependencies automatically.
The web script runs from `apps\web` and expects `node_modules` to already exist.
All test scripts use verbose output. `scripts\contracts\check.ps1` also checks
that generated web API types are current with the mirrored OpenAPI contracts.
Python backend pytest suites have a hard 60 second per-test timeout using the
Windows-compatible `thread` timeout method. Runtime/e2e tests that legitimately
need longer must opt in with `@pytest.mark.timeout(...)` and must not be part of
default fast verification. Web Vitest suites have a hard 10 second per-test
timeout configured in `apps/web/vitest.config.ts`; any test that legitimately
needs longer should use a local Vitest timeout override with a short reason.

## Standard Categories

- `fast`: local, deterministic, no network, no live browser, no external
  service, and no database service unless it uses an in-memory or temporary DB.
- `contract`: API, OpenAPI, schema, fixture, or artifact contract checks.
- `smoke`: shallow health, import, route, or page checks.
- `integration`: local multi-module or service-style tests using temp files,
  local fakes, fake browsers, in-process clients, or temporary databases.
- `runtime`: tests that execute or simulate app runtime paths such as
  subprocesses, job workers, fetch execution, source URL agent runs, vendor
  capture runs, process termination, browser/server/database/LLM calls, capture
  runs, or broad service orchestration.
- `golden`: deterministic frozen input/output fixture regression tests.
- `db_contract`: safe local DB schema, repository, migration, or persistence
  contract tests using local fakes, temp SQLite, or isolated temp storage.
  Ecommerce `db_contract` tests are allowed in fast/root-fast when local and
  deterministic.
- `db_integration`: broader local database behavior that is opt-in and not part
  of default/root fast verification.
- `postgres_required`: tests that require a real PostgreSQL service or
  environment-specific PostgreSQL setup. These are opt-in and never part of
  default fast verification.
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
require PostgreSQL or another running service, depend on credentials, run
subprocesses, perform broad DB integration, or perform full browser/operator
workflows. Mark those tests `runtime`, `db_integration`, `postgres_required`,
`external`, `slow`, and/or `e2e` as appropriate. No default fast test should
need more than 60 seconds. Python fast suites block obvious subprocess calls
unless the test is intentionally marked for a non-fast runtime/integration
profile.

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

Runtime tests are opt-in. Use the app runtime scripts for job/process/fetch,
source capture, source URL agent, database-heavy, or workflow orchestration
changes:

```powershell
.\scripts\test\product-factory-runtime.ps1
.\scripts\test\ecommerce-runtime.ps1
```

Golden tests are deterministic fixture regressions and can be selected
explicitly:

```powershell
.\scripts\test\product-factory-golden.ps1
.\scripts\test\ecommerce-golden.ps1
```

Product Factory Skroutz golden coverage is intentionally narrow: parser,
taxonomy, section extraction, deterministic render-row, and validation
snapshots use committed fixtures and do not call live websites, browser
execution, OpenAI, OpenCart, or full workflow orchestration. Runtime/e2e
workflow coverage remains opt-in only.

Golden snapshots are reviewed contract artifacts, not auto-regenerated dumps.
Expected JSON files must remain human-readable UTF-8 with stable key ordering
and focused stable fields. Snapshot expected files must not be updated unless
the prompt explicitly says `Approve snapshot updates`. If behavior changes
intentionally, Codex should show the semantic reason in the commit message,
commit body, or notes. If a snapshot failure reveals a real bug, fix production
or test code rather than blindly updating the snapshot. Snapshot rewrites should
be isolated from unrelated production changes when practical. Codex must not
silently rewrite expected snapshots as part of unrelated fixes.

Ecommerce source capture and Vendor Sources golden coverage follows the same
pattern. Parser, scoring, sanitization, direct Skroutz endpoint, source
selection, run-result serialization, and API response snapshots use small JSON
fixtures. They must not include live timestamps, absolute temp paths, secrets,
large raw payload dumps, or broad workflow side effects. DB source URL/product
source persistence coverage belongs in `db_contract`; vendor capture run
history, artifact writing, scheduled capture, and Price Monitoring capture
handoff remain runtime opt-in.

Ecommerce DB tests are split by profile:

```powershell
.\scripts\test\ecommerce-db-contract.ps1
.\scripts\test\ecommerce-db-integration.ps1
.\scripts\test\ecommerce-postgres.ps1
```

`db_contract` is included in Ecommerce fast/root-fast when local and
deterministic. `db_integration` is opt-in and not part of root fast.
`postgres_required` tests are opt-in and never part of default fast
verification.

Future Codex prompts should follow the targeted policy in
[Codex Default Verification](#codex-default-verification). Run runtime,
Ecommerce `db_integration`, `postgres_required`, `slow`, `external`, `e2e`,
`legacy`, or full suite selections only when the operator explicitly asks or
the change needs that scope. Full suites are manual unless explicitly
requested.

Always run tests with verbose output so you can see whether a check is hanging
or simply taking longer.

Broad Product Factory Skroutz prepare/render e2e golden coverage has been
replaced by narrow parser, taxonomy, section extraction, deterministic
render-row, and validation snapshots. The stale `307497` broad expectation and
fixture sample were removed because tabletop-hob taxonomy is covered by a
focused taxonomy test.

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
