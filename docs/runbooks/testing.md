# Testing Runbook

Use the root virtual environment and the checked-in test scripts. Do not use
bare `python`, `py`, a global interpreter, or an app-local virtual environment.

Always run tests with verbose output so you can see whether it is hanging or simply taking longer.

## Default Codex Check

```powershell
.\scripts\test-fast.ps1
```

This is the default Codex and local development check for Product Factory. It
runs from `apps/product-factory-api` and excludes `slow`, `external`, `legacy`,
`e2e`, and `runtime`.

Full `pytest` is not the default Codex command. Do not run full
prepare/render/publish e2e, subprocess, browser, OpenCart, OpenAI, database, or
live network tests unless the prompt explicitly asks for that profile.

## Profiles

```powershell
.\scripts\test-contract.ps1
.\scripts\test-golden.ps1
.\scripts\test-runtime.ps1
```

`contract` covers API, schema, artifact, and request/response contracts.

`golden` covers deterministic frozen input/output fixture regression tests.

`runtime` covers tests that execute or simulate app runtime paths,
subprocesses, workers, process termination, browser/server/database/LLM calls,
or full service orchestration.

Use `.\scripts\test-runtime.ps1` for intentional job runner, worker,
subprocess, process stop/kill, integration, or broad workflow checks.
