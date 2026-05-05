# Legacy Notes

This file preserves setup commands, compatibility behavior, and fallback notes that used to live
in the main README. These notes are archival. New setup and API work should use `README.md` and
`docs/api.md`.

## Legacy Windows Wrappers

The repo still contains Windows wrapper commands:

```powershell
.\setup-windows.cmd
.\dev-windows.cmd
.\build-windows.cmd
.\diagnose-windows.cmd
```

They call the PowerShell scripts under `scripts/`. The old setup wrapper uses installed
`node` and `npm` when they exist. If they are not on `PATH`, it downloads portable Node.js into
`.tools` inside this repo. It installs dependencies from `package-lock.json` with `npm ci` and
falls back to `npm install` only if the lockfile is missing.

The current README intentionally documents direct npm commands instead.

## Legacy Local Platform Startup

The repo-local multi-window startup scripts are preserved here for reference:

```cmd
scripts\windows\start-all.cmd
scripts\windows\start-commerce-api.cmd
scripts\windows\start-product-agent-api.cmd
scripts\windows\start-ui.cmd
scripts\windows\diagnose.cmd
```

Older parent-level platform scripts referenced by the previous README:

```cmd
..\scripts\local\start-platform-windows.cmd
..\scripts\local\start-platform-foreground.cmd
..\scripts\local\diagnose-platform.cmd
```

Legacy startup environment variables:

```text
PRICE_FETCHER_DIR
PRODUCT_AGENT_DIR
PRODUCT_AGENT_API_CMD
VITE_API_PROXY_TARGET
VITE_COMMERCE_API_PROXY_TARGET
```

The old manual startup sequence was:

```powershell
python -m pip install -e .
pricefetcher-api
npm run dev
```

Old diagnostic checks:

```powershell
.\diagnose-windows.cmd
scripts\windows\diagnose.cmd
```

## Legacy Local File Assumptions

Older docs called out these local files:

```text
C:\Users\user\Downloads\sourceCata.csv
C:\Exports\CheckWHouseBalance.csv
```

Catalog browsing no longer treats `sourceCata.csv` as browser runtime data. The backend imports
catalog data into PostgreSQL, and the UI reads the active catalog through commerce API endpoints.

## Compatibility Behaviors

These compatibility behaviors are not part of the current public contract, but they still exist
in parts of the client or test fixtures and should be removed deliberately when the backend
contract is tightened:

- Product-Agent job creation can normalize wrapped responses such as `job`, `data`, or `result`.
- Job lists, logs, and artifacts can normalize common wrapper keys such as `items`, `data`, or
  `results`.
- Commerce artifact URLs can be converted from older `/api/artifacts/...` paths to
  `/commerce-api/artifacts/...`.
- Price Monitoring execution views can derive artifact links from individual artifact path fields
  when the backend does not send a full artifact list.
- Price Monitoring DB status tests include conservative inference for old backend payloads that
  do not expose explicit readiness fields.
- Some UI summaries can display `Raw category` for old run data that only contains
  `filters.category`.
- Source URL import can include legacy run folders through `include_legacy_runs` and
  `legacy_runs_dir`.

## Historical Workflow Notes

Older README notes included these behavior details:

- Product-Agent job polling ran every 2.5 seconds while queued or running-like statuses were
  present, then stopped after terminal status.
- Stop support marked Product-Agent jobs as `cancelled`; backend force-kill could report `killed`.
- Catalog Source URL Import was collapsed by default and required a successful dry-run preview
  before apply.
- Price Monitoring fetch was asynchronous from the UI perspective: start fetch, poll fetch state,
  read logs, and cancel active fetches.
- Failed and killed Price Monitoring artifacts were shown as diagnostic artifacts by default when
  the backend marked them that way.
- Large server-backed results such as catalog rows, observation tables, review tables, CSV
  contents, and API responses were reloaded rather than permanently stored in browser state.
