# Testing Deprecation Plan

| App | Old/broad test area | Current risk | Replacement target | Delete after | Status |
| --- | --- | --- | --- | --- | --- |
| Product Factory | Subprocess job runner tests | Slow and process-sensitive; can hang or behave differently across local shells | Smaller command-construction contract tests plus focused runtime profile coverage for process handling | Replacement target is implemented and validated | Reclassified as runtime/integration/slow |
| Product Factory | Full Skroutz prepare/render fixture workflow | Broad service orchestration through frozen fixtures; expensive for default Codex checks; the old `307497` golden expectation was stale | Narrow parser, taxonomy, section extraction, deterministic render-row, and validation snapshots | Replaced by `test_skroutz_golden_snapshots.py`; stale `307497` HTML/CSV fixtures removed | Complete |
| Product Factory | Broad Skroutz taxonomy fixture loops | Large fixture sweep can dominate routine feedback | Representative golden taxonomy cases plus targeted unit coverage for taxonomy rules | Replacement target is implemented and validated | Reclassified as slow/golden |
| Ecommerce API | Price Monitoring fetch execution/run tests | Simulates fetch execution, worker state, subprocess results, cancellation, and run artifacts | Smaller route contracts plus focused runtime fetch execution coverage | Replacement target is implemented and validated | Reclassified as runtime |
| Ecommerce API | Source URL agent tests | Exercises source URL agent run orchestration, artifacts, persistence, and review flows | Narrow evidence/scoring/candidate/registry/search-query snapshots, SQLite `db_contract` persistence tests, and opt-in runtime agent coverage | Replaced by `test_source_url_agent_snapshots.py`, `test_source_url_agent_db_contract.py`, and `test_source_url_agent_runtime.py` | Split into golden/db_contract/runtime |
| Ecommerce API | Source URL agent API run tests | Enqueues or simulates source URL agent runs and persists candidates/artifacts | Route-shape and candidate review contract tests plus focused runtime API run coverage | Runtime run orchestration lives in `test_source_url_agent_runtime.py` | Split into contract/db_contract/runtime |
| Ecommerce API | Source capture parser/scoring/direct endpoint tests | Mixed pure parser, sanitization, direct endpoint, DB, and runtime capture behavior in one runtime-marked module | Narrow parser, scoring, sanitization, and direct Skroutz endpoint golden snapshots plus separate DB contracts | Replaced by `test_source_capture_snapshots.py`, `test_skroutz_direct_capture_snapshots.py`, and `test_source_capture_db_contracts.py` | Complete |
| Ecommerce API | Vendor source capture tests | Simulates capture runs, source URL selection, persistence, and artifact generation | Smaller selection, run-result, and API response golden snapshots plus focused runtime capture coverage | Replaced by `test_vendor_sources_snapshots.py`; runtime run-history/artifact orchestration remains opt-in | Split into db_contract/golden/runtime |
| Ecommerce API | Price Monitoring DB-heavy tests | Broad SQLite-backed database workflows, migrations, observations, and alert behavior can dominate default Codex checks | Smaller route/serialization contracts plus explicit runtime database workflow coverage | Replacement target is implemented and validated | Reclassified as runtime where broad |

## Current Test Profile Policy

Root `scripts/test/fast.ps1` is the Codex-safe aggregate fast verification
command. It first runs snapshot hygiene and fast marker hygiene, then delegates
to app-specific fast scripts, web fast checks, and contract mirrors; the
delegated app scripts exclude runtime, Ecommerce `db_integration`,
`postgres_required`, external, e2e, legacy, and slow checks where applicable.
Fast marker hygiene prevents runtime, `db_integration`, `postgres_required`,
external, e2e, legacy, or slow tests from leaking into root fast. App-specific
scripts are still preferred when a change touches only one app.

Ecommerce DB tests are split into `db_contract`, `db_integration`, and
`postgres_required`. `db_contract` tests are included in fast/root-fast when
local and deterministic. `db_integration` is opt-in and not root fast.
`postgres_required` tests are opt-in and never part of default fast
verification. Runtime tests are opt-in, golden tests are deterministic fixture
regressions, and full suites are manual unless explicitly requested.

Python backend tests have a hard 60 second per-test timeout. Runtime/e2e tests
that legitimately need longer must explicitly override it with
`@pytest.mark.timeout(...)` and must not be part of default fast. Always run
tests with verbose output so you can see whether a check is hanging or simply
taking longer. Web Vitest tests have a hard 10 second per-test timeout.

Golden snapshots are reviewed contract artifacts, not auto-regenerated dumps.
Golden snapshot expected files must not be updated unless the prompt explicitly
says `Approve snapshot updates`. If behavior changes intentionally, Codex
should show the semantic reason in the commit message, commit body, or notes. If
a snapshot failure reveals a real bug, fix production or test code rather than
blindly updating the snapshot. Snapshot rewrites should be isolated from
unrelated production changes when practical.

## Completed Product Factory Skroutz Replacement

The Product Factory full Skroutz prepare/render workflow fixture test has been
replaced by smaller golden parser, taxonomy, section extraction, deterministic
render-row, and validation snapshots in
`apps/product-factory-api/src/product_factory/tests/test_skroutz_golden_snapshots.py`.
Those snapshots load committed HTML/rendered-section fixtures and call parser,
taxonomy, render-row, section extraction, and validator code directly. They do
not call live websites, Playwright browser execution, OpenAI, OpenCart, Docker,
or full prepare/render workflow orchestration.

The stale `307497` broad expectations and fixture sample were removed because
the tabletop-hob taxonomy behavior remains covered by the explicit
`test_explicit_tabletop_hob_category_still_resolves_to_small_appliance_hobs`
unit-style taxonomy test. Future Skroutz golden additions should use narrow
explicit JSON snapshots rather than full workflow CSV baselines.

## Completed Ecommerce Source Capture Split

Ecommerce source capture and Vendor Sources capture now use narrow golden
snapshots for parser, scoring, sanitization, direct Skroutz endpoint capture,
vendor source selection, run-result serialization, and API response shapes.
The snapshots live under
`apps/ecommerce-api/tests/fixtures/golden_snapshots/` and avoid timestamps,
absolute temp paths, secrets, full raw payload dumps, and broad workflow side
effects.

Local SQLite persistence behavior is separated into `db_contract` tests for
source URL mirroring, active-status filtering, source health updates, and
append-only observations. Runtime/vendor orchestration, run history, artifact
writing, scheduled capture, and Price Monitoring fetch handoff remain opt-in
runtime or `db_integration` coverage and are not part of root fast.

## Completed Ecommerce Source URL Agent Split

Ecommerce Source URL Agent coverage is split into fast golden snapshots, safe
SQLite DB contracts, and opt-in runtime execution tests. The snapshots live
under
`apps/ecommerce-api/tests/fixtures/golden_snapshots/source_url_agent/` and cover
evidence extraction, scoring outcomes, candidate result shaping, source
registry URL-shape rules, search query generation, and URL normalization.

Source URL Agent `db_contract` tests use deterministic temporary SQLite only
for repository and persistence behavior such as source URL writes, high
confidence promotion thresholds, review CSV application, candidate row
persistence, and export/import relinking. Full Source URL Agent execution,
multi-file artifact writing, job wrappers, and API run orchestration are
classified as runtime, with `db_integration` when they persist discovery runs
through the broader service path.

Root fast includes only fast/golden/`db_contract`-safe Source URL Agent checks.
Runtime, `db_integration`, `postgres_required`, external, e2e, legacy, and slow
Source URL Agent tests remain opt-in. Source URL Agent golden snapshots must not
include temp paths, live timestamps, secrets, authorization/session/cookie
headers, large raw HTML captures, or full run artifacts; expected files must
not be updated unless the prompt explicitly says `Approve snapshot updates`.
Always run these tests with verbose output so it is clear whether a check is
hanging or simply taking longer.
