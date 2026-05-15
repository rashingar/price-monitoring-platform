"""CLI worker for DB-backed Ecommerce durable jobs."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TextIO

from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog_update import CATALOG_UPDATE_JOB_TYPE
from ecommerce.catalog_update import service as catalog_update_service
from ecommerce.db.config import DatabaseNotConfiguredError, sanitize_database_error
from ecommerce.db.session import create_session_factory
from ecommerce.env import load_local_env_if_present
from ecommerce.db.repositories.jobs import fail_stale_running_jobs, lease_queued_jobs_for_worker, list_queued_jobs_for_worker, list_stale_running_jobs
from ecommerce.jobs.durable import DurableJobRegistry, execute_registered_job


@dataclass(frozen=True)
class WorkerIterationResult:
    stale_failed: int = 0
    stale_seen: int = 0
    claimed: int = 0
    cancelled: int = 0
    executed: int = 0
    dry_run: bool = False

    @property
    def did_work(self) -> bool:
        return bool(self.stale_failed or self.claimed or self.cancelled or self.executed)


def build_default_registry() -> DurableJobRegistry:
    registry = DurableJobRegistry()
    registry.register(
        CATALOG_UPDATE_JOB_TYPE,
        lambda job_id, _payload: catalog_update_service.run_catalog_update_durable_job(job_id),
    )
    return registry


def build_parser(registry: DurableJobRegistry | None = None) -> argparse.ArgumentParser:
    selected_registry = registry or build_default_registry()
    parser = argparse.ArgumentParser(description="Run queued DB-backed Ecommerce durable jobs.")
    parser.add_argument("--job-type", choices=selected_registry.job_types(), default=None)
    parser.add_argument("--once", action="store_true", help="Run one polling iteration and exit.")
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--stale-running-after-minutes", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true", help="Inspect matching jobs without mutating or executing them.")
    return parser


def run_worker_iteration(
    *,
    registry: DurableJobRegistry,
    job_type: str | None = None,
    limit: int = 1,
    stale_running_after_minutes: int = 60,
    dry_run: bool = False,
    database_url: str | None = None,
    now: datetime | None = None,
    stdout: TextIO | None = None,
) -> WorkerIterationResult:
    output = stdout or sys.stdout
    job_types = None if job_type else registry.job_types()
    session = create_session_factory(database_url)()
    try:
        if dry_run:
            stale_jobs = list_stale_running_jobs(
                session,
                stale_after_minutes=stale_running_after_minutes,
                job_type=job_type,
                job_types=job_types,
                now=now,
            )
            queued_jobs = list_queued_jobs_for_worker(
                session,
                job_type=job_type,
                job_types=job_types,
                limit=limit,
            )
            _print(
                output,
                "dry-run: "
                f"stale_running={len(stale_jobs)} queued={len(queued_jobs)} "
                f"job_type={job_type or ','.join(job_types)}",
            )
            for job in stale_jobs:
                _print(output, f"dry-run stale running job would be failed: job_id={job.job_id} job_type={job.job_type}")
            for job in queued_jobs:
                _print(output, f"dry-run queued job would be claimed: job_id={job.job_id} job_type={job.job_type}")
            session.rollback()
            return WorkerIterationResult(stale_seen=len(stale_jobs), claimed=len(queued_jobs), dry_run=True)

        stale_jobs = fail_stale_running_jobs(
            session,
            stale_after_minutes=stale_running_after_minutes,
            job_type=job_type,
            job_types=job_types,
            now=now,
        )
        session.commit()
        for job in stale_jobs:
            _print(output, f"marked stale running job failed: job_id={job.job_id} job_type={job.job_type}")

        claimed_jobs = lease_queued_jobs_for_worker(
            session,
            job_type=job_type,
            job_types=job_types,
            limit=limit,
        )
        session.commit()

        cancelled = 0
        executed = 0
        for job in claimed_jobs:
            if job.status == "cancelled":
                cancelled += 1
                _print(output, f"cancelled queued job before start: job_id={job.job_id} job_type={job.job_type}")
                continue

            _print(output, f"running durable job: job_id={job.job_id} job_type={job.job_type}")
            final_job = execute_registered_job(session, job.job_id, registry, reraise=False, claimed=True)
            executed += 1
            _print(output, f"finished durable job: job_id={final_job.job_id} status={final_job.status}")

        if not stale_jobs and not claimed_jobs:
            _print(output, f"no matching durable jobs found: job_type={job_type or ','.join(job_types)}")

        return WorkerIterationResult(
            stale_failed=len(stale_jobs),
            claimed=len(claimed_jobs),
            cancelled=cancelled,
            executed=executed,
        )
    finally:
        session.close()


def main(argv: Sequence[str] | None = None) -> int:
    load_local_env_if_present()
    registry = build_default_registry()
    parser = build_parser(registry)
    args = parser.parse_args(argv)

    poll_seconds = max(0.1, float(args.poll_seconds))
    limit = max(1, int(args.limit))
    stale_after_minutes = max(1, int(args.stale_running_after_minutes))

    _print(sys.stdout, "starting Ecommerce durable job worker")
    _print(
        sys.stdout,
        "worker config: "
        f"job_type={args.job_type or ','.join(registry.job_types())} "
        f"once={bool(args.once)} poll_seconds={poll_seconds:g} limit={limit} "
        f"stale_running_after_minutes={stale_after_minutes} dry_run={bool(args.dry_run)}",
    )

    try:
        while True:
            run_worker_iteration(
                registry=registry,
                job_type=args.job_type,
                limit=limit,
                stale_running_after_minutes=stale_after_minutes,
                dry_run=bool(args.dry_run),
            )
            if args.once:
                return 0
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        _print(sys.stdout, "stopping Ecommerce durable job worker")
        return 0
    except (DatabaseNotConfiguredError, SQLAlchemyError) as exc:
        _print(sys.stderr, f"Ecommerce durable job worker failed: {sanitize_database_error(exc)}")
        return 1


def _print(output: TextIO, message: str) -> None:
    print(message, file=output, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
