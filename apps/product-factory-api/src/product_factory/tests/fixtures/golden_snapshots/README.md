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

## Update Policy

Snapshots must be human-readable UTF-8 JSON with stable key ordering. Snapshot
tests should compare exact expected stable fields unless the test intentionally
documents partial matching.

Snapshot updates require an explicit operator request. Codex must not silently
rewrite expected snapshots as part of unrelated fixes. Golden snapshot expected
files must not be updated unless the prompt explicitly says
`Approve snapshot updates`.
