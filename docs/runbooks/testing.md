# Testing Runbook

Use the root virtual environment and the checked-in test scripts. Do not use
bare `python`, `py`, a global interpreter, or an app-local virtual environment.

Always run tests with verbose output so you can see whether it is hanging or simply taking longer.

## Default Codex Check

```powershell
.\scripts\test\codex-product-factory.ps1
.\scripts\test\codex-ecommerce.ps1
```

Use the app-specific Codex script when a prompt touches only that backend app.
Both scripts exclude `slow`, `external`, `legacy`, `e2e`, and `runtime`.
`.\scripts\test\fast.ps1` is broad monorepo operator verification, not the
default Codex command.

Full `pytest` is not the default Codex command. Do not run full
prepare/render/publish e2e, subprocess, browser, OpenCart, OpenAI, database, or
live network tests unless the prompt explicitly asks for that profile.

## Profiles

```powershell
.\scripts\test\product-factory-golden.ps1
.\scripts\test\product-factory-runtime.ps1
.\scripts\test\ecommerce-golden.ps1
.\scripts\test\ecommerce-runtime.ps1
```

`contract` covers API, schema, artifact, and request/response contracts.

`golden` covers deterministic frozen input/output fixture regression tests.

`runtime` covers tests that execute or simulate app runtime paths,
subprocesses, workers, process termination, browser/server/database/LLM calls,
or full service orchestration.

Use the app runtime scripts for intentional job runner, worker, subprocess,
process stop/kill, fetch execution, source capture, source URL agent, database
workflow, or broad orchestration checks. Full suites are manual unless
explicitly requested.
