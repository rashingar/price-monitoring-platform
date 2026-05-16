from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import JobRecord, JobStatus, JobType, is_terminal_job_status
from .runner import (
    JobRunResult,
    LogCallback,
    run_authoring_intro_job,
    run_authoring_seo_job,
    run_full_pipeline_job,
    run_prepare_job,
    run_publish_job,
    run_render_job,
)
from .store import DEFAULT_JOBS_DIR, JobStore
from ..services import ServiceError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m product_factory.jobs.run_product_factory_job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--job-root", default=str(DEFAULT_JOBS_DIR))
    parser.add_argument("--api-work-root", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = JobStore(Path(args.job_root))
    try:
        record = store.get_job(args.job_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if record is None:
        print(f"Job not found: {args.job_id}", file=sys.stderr)
        return 2
    if record.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        print(f"Job {record.job_id} is not runnable in status {record.status.value}.", file=sys.stderr)
        return 2
    if record.status == JobStatus.QUEUED:
        record = store.mark_running(record.job_id, message="Job started.")
        if record.status != JobStatus.RUNNING:
            return 2

    def log(line: str) -> None:
        store.append_log(record.job_id, line)

    try:
        result = _run_record(record, log) or JobRunResult()
        if _preserve_cancelled_or_killed(store, record.job_id, log):
            return 2
        if result.artifacts:
            store.update_artifacts(record.job_id, result.artifacts)
        if result.status == JobStatus.FAILED:
            log(f"Failed {record.job_type.value} job: {result.error}")
            if _preserve_cancelled_or_killed(store, record.job_id, log):
                return 2
            store.mark_failed(
                record.job_id,
                result.error or "Job failed.",
                message=result.message or "Job failed.",
                error_code=result.error_code,
            )
            return 1
        log(f"Finished {record.job_type.value} job.")
        if _preserve_cancelled_or_killed(store, record.job_id, log):
            return 2
        store.mark_succeeded(
            record.job_id,
            message=result.message or "Job succeeded.",
            error=result.error,
            error_code=result.error_code,
        )
        return 0
    except ServiceError as exc:
        log(f"Failed {record.job_type.value} job [{exc.code}]: {exc.message}")
        if _preserve_cancelled_or_killed(store, record.job_id, log):
            return 2
        store.mark_failed(record.job_id, exc.message, message="Job failed.", error_code=exc.code)
        return 1
    except Exception as exc:
        log(f"Failed {record.job_type.value} job: {exc}")
        if _preserve_cancelled_or_killed(store, record.job_id, log):
            return 2
        store.mark_failed(record.job_id, str(exc), message="Job failed.")
        return 1


def _run_record(record: JobRecord, log: LogCallback) -> JobRunResult | None:
    log(f"Worker accepted {record.job_type.value} job.")
    if record.job_type == JobType.PREPARE:
        return run_prepare_job(record, log)
    if record.job_type == JobType.AUTHORING_INTRO:
        return run_authoring_intro_job(record, log)
    if record.job_type == JobType.AUTHORING_SEO:
        return run_authoring_seo_job(record, log)
    if record.job_type == JobType.RENDER:
        return run_render_job(record, log)
    if record.job_type == JobType.PUBLISH:
        return run_publish_job(record, log)
    if record.job_type == JobType.FULL_PIPELINE:
        return run_full_pipeline_job(record, log)
    raise ValueError(f"Unsupported job type: {record.job_type.value}")


def _preserve_cancelled_or_killed(store: JobStore, job_id: str, log: LogCallback) -> bool:
    current = store.get_job(job_id)
    if current is None:
        return True
    if current.status in {JobStatus.CANCELLED, JobStatus.KILLED}:
        log(f"Worker will not overwrite terminal {current.status.value} status.")
        return True
    return is_terminal_job_status(current.status) and current.status not in {JobStatus.RUNNING, JobStatus.QUEUED}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
