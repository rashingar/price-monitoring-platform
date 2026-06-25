from __future__ import annotations

import os

from .models import JobStatus
from .runner import SequentialJobRunner
from .store import JobStore

RESTART_INTERRUPTED_ERROR_CODE = "job_interrupted_by_restart"


def reconcile_persisted_jobs(store: JobStore, runner: SequentialJobRunner) -> None:
    for record in store.list_non_terminal_jobs():
        if record.status == JobStatus.QUEUED:
            runner.enqueue(record.job_id)
            continue
        if record.status == JobStatus.RUNNING and not _is_current_runner_job(
            record.job_id, record.parent_process_id, runner
        ):
            interrupted = store.mark_failed(
                record.job_id,
                "Job was interrupted by Product Factory API restart.",
                message="Job interrupted by API restart; retry explicitly if needed.",
                error_code=RESTART_INTERRUPTED_ERROR_CODE,
            )
            store.update_process_metadata(
                interrupted.job_id,
                termination_mode="interrupted_by_restart",
            )
            store.append_log(
                interrupted.job_id,
                "Startup recovery marked stale running job interrupted by API restart.",
            )


def _is_current_runner_job(
    job_id: str,
    parent_process_id: int | None,
    runner: SequentialJobRunner,
) -> bool:
    return runner.owns_running_job(job_id) and parent_process_id in {None, os.getpid()}
