# Golden Snapshot Governance

Golden snapshots are reviewed contract artifacts. Keep them narrow, stable, and
human-readable so a diff shows the intended behavior change.

## Allowed In Snapshots

- Stable normalized fields.
- Parser outputs reduced to important contract fields.
- Taxonomy and result classifications.
- Deterministic render-row fields.
- Stable API and result response shapes.
- Normalized status and count fields.
- Normalized error codes and quality flags.
- Source URL Agent evidence, scoring, candidate shape, source registry,
  search-query, and URL-normalization contracts.

## Forbidden In Snapshots

- Absolute temp paths.
- Current timestamps unless normalized.
- Random run IDs unless normalized.
- Database row IDs unless intentionally normalized.
- Secrets.
- Authorization, session, or cookie headers.
- Full raw HTML captures unless tiny and purpose-built.
- Large JSON payload dumps.
- Generated CSVs or full workflow artifacts when a smaller row or result
  snapshot is enough.
- Live network, browser, OpenAI, OpenCart, or PostgreSQL-dependent output.

## Source URL Agent Snapshots

Source URL Agent snapshots live under `source_url_agent/` and are split into
`evidence/`, `scoring/`, `candidates/`, `registry/`, and `search_queries/`.
They cover pure discovery contracts only. Full Source URL Agent execution,
multi-file run artifacts, job wrappers, and API run orchestration are runtime
opt-in tests, not golden snapshots.

DB contract coverage for Source URL Agent uses deterministic temporary SQLite
and should not require PostgreSQL, live network, browsers, Docker, marketplace
pages, OpenAI, OpenCart, or external services.

## Update Policy

Snapshots must be human-readable UTF-8 JSON with stable key ordering. Snapshot
tests should compare exact expected stable fields unless the test intentionally
documents partial matching.

Snapshot updates require an explicit operator request. Codex must not silently
rewrite expected snapshots as part of unrelated fixes. Golden snapshot expected
files must not be updated unless the prompt explicitly says
`Approve snapshot updates`.

Always run snapshot tests with verbose output so it is clear whether a check is
hanging or simply taking longer.
