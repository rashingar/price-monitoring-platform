# Durable Worker Deployment Readiness

This runbook documents the current path to worker-owned durable execution for
self-hosted and server deployments. It does not change the local default.

## Current Local Default

`ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE=true` remains the local/operator
default. With this setting, API routes create a durable DB job and then schedule
local FastAPI background execution for that same API process.

This preserves workstation behavior for operators who start only the Ecommerce
API during development. The durable worker is still the canonical executor and
should be started for realistic deployment testing.

## Recommended Server Mode

Server deployments should run with:

```powershell
ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE=false
```

In this mode, API routes enqueue durable jobs only. They do not start local
background execution. A separate `ecommerce.jobs.worker` process must be running
to lease queued jobs and execute them.

## Required Worker Process

From the repository root in the local PowerShell environment:

```powershell
.\scripts\dev\ecommerce-worker.ps1 --poll-seconds 5 --limit 1
```

The underlying module is:

```powershell
.\.venv\Scripts\python.exe -m ecommerce.jobs.worker --poll-seconds 5 --limit 1
```

Use `--once` for one polling iteration during checks, and `--dry-run` to inspect
matching queued and stale-running jobs without mutating or executing them.

## Affected Job Types

The default durable worker registry currently owns:

- `catalog_update_from_opencart`: Dashboard catalog update from OpenCart export
  through `/api/catalog/update-db`.
- `source_url_agent_run`: Find Source queued runs through
  `/api/source-url-agent/runs`.

Synchronous endpoints and non-durable workflows are not changed by the inline
policy flag.

## Startup Order

Recommended server order:

1. Start PostgreSQL and confirm the Ecommerce database is reachable.
2. Apply migrations from `apps/ecommerce-api`.
3. Start the Ecommerce API with
   `ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE=false`.
4. Start one or more Ecommerce durable worker processes.
5. Start the web process or reverse proxy.
6. Run the operator smoke check and inspect durable job health.

For local development, starting the worker before or after the API is fine. In
worker-only mode, queued jobs remain queued until a worker starts.

## Operational Expectations

- The API process should be treated as the HTTP adapter and durable-job enqueuer.
- The worker process should be supervised by the deployment environment.
- Workers should share the same `ECOMMERCE_DATABASE_URL` and app configuration
  as the API.
- Multiple workers can run. PostgreSQL leasing uses row locking with
  `SKIP LOCKED` so workers do not intentionally claim the same queued job.
- Worker logs should be captured separately from API logs.
- The API platform health details report whether API inline durable execution is
  currently enabled or disabled.
- The API platform health details also report the durable job backlog:
  queued count, queued count by job type, oldest queued timestamp/age when a
  queue exists, running count, running count by job type, and stale-running
  candidate count by job type.

## Platform Health Backlog Signal

`/api/platform/health` includes the durable execution policy and backlog details
in the existing `ecommerce_api` group. This is a backend-only observability
signal; it does not change job endpoint payloads or frontend behavior.

Interpretation:

- `queued=0` with worker-only mode is healthy from a backlog perspective.
- `queued>0` while `ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE=false` produces a
  warning because worker-only mode requires a running durable worker to make
  progress.
- The oldest queued timestamp and age show how long the backlog has been
  waiting. A growing age usually means no worker is leasing jobs or the worker
  is not covering that job type.
- `running>0` is normal while jobs are active.
- `stale_running_candidates>0` produces a warning. These are running jobs whose
  latest heartbeat, start time, update time, or creation time is older than the
  configured stale-running threshold for that job type.

The platform health signal does not detect whether an OS process named
`ecommerce.jobs.worker` exists. It intentionally infers operational risk only
from durable job table state: queued backlog and stale-running candidates.

## Failure Modes When Worker Is Not Running

With `ECOMMERCE_API_EXECUTE_DURABLE_JOBS_INLINE=false`, missing workers do not
make enqueue endpoints fail. Instead:

- New durable jobs are created with `status=queued`.
- Catalog update and Find Source work does not progress.
- The UI can show queued jobs but no results until a worker executes them.
- `/api/jobs` continues to show queued/running job state.
- `/api/platform/health` warns when queued jobs exist in worker-only mode and
  reports the oldest queued durable job timestamp/age.
- Starting the worker later should pick up queued jobs without changing request
  payloads or endpoint response shapes.

If a worker crashes after claiming a job, the job may remain `running` until the
stale-running threshold is exceeded and a worker iteration marks it failed.

## Verification

Read-only API checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/platform/health
Invoke-RestMethod "http://127.0.0.1:8001/api/jobs?status=queued&limit=20"
Invoke-RestMethod "http://127.0.0.1:8001/api/jobs?status=running&limit=20"
Invoke-RestMethod http://127.0.0.1:8001/api/catalog/update-db/latest
Invoke-RestMethod "http://127.0.0.1:8001/api/source-url-agent/runs?limit=20"
```

Worker dry run:

```powershell
.\scripts\dev\ecommerce-worker.ps1 --once --dry-run --limit 20
```

Operator smoke:

```powershell
.\scripts\check\operator-smoke.ps1
```

The current smoke check verifies the durable jobs API responds. Before flipping
the local default, it should also consume the platform health backlog signal in
the intended deployment mode. Process supervision should still verify that the
worker service exists and is running.

## Stale-Running Thresholds

The worker checks stale `running` jobs at the beginning of each iteration.

Current defaults:

- Generic `--stale-running-after-minutes`: `60`.
- `catalog_update_from_opencart` override:
  `ECOMMERCE_CATALOG_UPDATE_STALE_RUNNING_AFTER_MINUTES`, default `240`.
- `source_url_agent` override:
  `ECOMMERCE_SOURCE_URL_AGENT_STALE_RUNNING_AFTER_MINUTES`, default `180`.

The stale threshold does not cancel queued jobs. It only applies to jobs already
marked `running` whose latest heartbeat, start time, update time, or creation
time is older than the threshold.

Do not lower thresholds for production-like browser/export runs without
reviewing the longest expected OpenCart export and Source URL Agent run times.

## Docker, Proxmox, and Tailscale Readiness

For Docker or Proxmox deployments, model the API and worker as separate
supervised services using the same application image and environment, with
different commands:

- API: serve FastAPI with inline durable execution disabled.
- Worker: run `python -m ecommerce.jobs.worker`.

Tailscale or reverse proxy exposure should route browser/API traffic only to
the API/web entry points. The worker does not need inbound HTTP exposure; it
needs database connectivity, filesystem/artifact access required by the job
types it runs, and the same secret/config environment as the API.

Do not flip the repository default until deployment automation starts the
worker, smoke checks consume queued-backlog/stale-running health, process
supervision detects missing worker services, and enqueue-only mode remains
covered by tests.
