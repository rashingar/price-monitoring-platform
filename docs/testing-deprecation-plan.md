# Testing Deprecation Plan

| App | Old/broad test area | Current risk | Replacement target | Delete after | Status |
| --- | --- | --- | --- | --- | --- |
| Product Factory | Subprocess job runner tests | Slow and process-sensitive; can hang or behave differently across local shells | Smaller command-construction contract tests plus focused runtime profile coverage for process handling | Replacement target is implemented and validated | Reclassified as runtime/integration/slow |
| Product Factory | Full Skroutz prepare/render fixture workflow | Broad service orchestration through frozen fixtures; expensive for default Codex checks; current `307497` golden expectation is stale | Stage-level prepare/render golden tests with narrower fixture assertions | Replacement target is implemented and validated | Reclassified as runtime/e2e/golden and strict-xfailed pending replacement |
| Product Factory | Broad Skroutz taxonomy fixture loops | Large fixture sweep can dominate routine feedback | Representative golden taxonomy cases plus targeted unit coverage for taxonomy rules | Replacement target is implemented and validated | Reclassified as slow/golden |
| Ecommerce API | Price Monitoring fetch execution/run tests | Simulates fetch execution, worker state, subprocess results, cancellation, and run artifacts | Smaller route contracts plus focused runtime fetch execution coverage | Replacement target is implemented and validated | Reclassified as runtime |
| Ecommerce API | Source URL agent tests | Exercises source URL agent run orchestration, artifacts, persistence, and review flows | Smaller pure scoring/matching contracts plus focused runtime agent coverage | Replacement target is implemented and validated | Reclassified as runtime |
| Ecommerce API | Source URL agent API run tests | Enqueues or simulates source URL agent runs and persists candidates/artifacts | Route-shape contract tests plus focused runtime API run coverage | Replacement target is implemented and validated | Selected tests reclassified as runtime |
| Ecommerce API | Vendor source capture tests | Simulates capture runs, source URL selection, persistence, and artifact generation | Smaller capture result contract tests plus focused runtime capture coverage | Replacement target is implemented and validated | Reclassified as runtime |
| Ecommerce API | Price Monitoring DB-heavy tests | Broad SQLite-backed database workflows, migrations, observations, and alert behavior can dominate default Codex checks | Smaller route/serialization contracts plus explicit runtime database workflow coverage | Replacement target is implemented and validated | Reclassified as runtime where broad |

## Current Test Profile Policy

Root `scripts/test/fast.ps1` is the Codex-safe aggregate fast verification
command. It delegates to app-specific fast scripts, web fast checks, and
contract mirrors; the delegated app scripts exclude runtime, external, e2e,
legacy, and PostgreSQL-required checks. App-specific scripts are still preferred
when a change touches only one app.

Ecommerce DB tests are split into `db_contract`, `db_integration`, and
`postgres_required`. `postgres_required` tests are never part of default fast
verification. Runtime tests are opt-in, golden tests are deterministic fixture
regressions, and full suites are manual unless explicitly requested. Always run
tests with verbose output so you can see whether a check is hanging or simply
taking longer.

## Next Replacement Target

Replace the Product Factory full Skroutz prepare/render workflow fixture test
with smaller golden parser, taxonomy, section extraction, deterministic
render-row, and validation snapshots. Replace stale `307497` broad expectations
with narrow explicit expected outputs or remove the stale sample after
replacement coverage exists.
