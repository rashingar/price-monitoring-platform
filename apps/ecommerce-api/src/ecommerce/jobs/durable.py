"""Durable job execution and handler registry for Ecommerce workflows."""

from __future__ import annotations

from typing import Any
from collections.abc import Callable

from sqlalchemy.orm import Session

from ecommerce.db.models.jobs import EcommerceJob
from ecommerce.db.repositories.jobs import (
    JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    JobNotFoundError,
    JobStatus,
    create_queued_job,
    fail_stale_running_jobs,
    get_job_by_id,
    heartbeat,
    job_to_dict,
    lease_queued_jobs_for_worker,
    list_jobs,
    list_queued_jobs_for_worker,
    list_stale_running_jobs,
    mark_cancelled,
    mark_failed,
    mark_running,
    mark_succeeded,
    request_cancel,
    _require_job,
)

JobHandler = Callable[[Any], Any]
RegisteredJobHandler = Callable[[str, Any], Any]


class DurableJobRegistry:
    """In-process handler registry for synchronous durable job execution."""

    def __init__(self) -> None:
        self._handlers: dict[str, RegisteredJobHandler] = {}

    def register(self, job_type: str, handler: RegisteredJobHandler) -> None:
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> RegisteredJobHandler:
        try:
            return self._handlers[job_type]
        except KeyError as exc:
            raise KeyError(f"No durable job handler registered for job_type={job_type!r}.") from exc

    def job_types(self) -> tuple[str, ...]:
        return tuple(self._handlers)


def execute_job(
    session: Session,
    job_id: str,
    handler: JobHandler,
    *,
    reraise: bool = True,
    claimed: bool = False,
) -> EcommerceJob:
    job = _require_job(session, job_id)
    if job.status in TERMINAL_JOB_STATUSES:
        return job

    if job.cancel_requested:
        mark_cancelled(session, job_id, error_message="Cancellation requested before start.")
        session.commit()
        return _require_job(session, job_id)

    if job.status == "queued":
        mark_running(session, job_id)
        session.commit()
    elif job.status == "running":
        if not claimed:
            return job
        session.commit()
    else:
        raise ValueError(f"Cannot execute job {job_id!r} with status {job.status!r}.")

    try:
        result = handler(job.payload_json)
    except Exception as exc:
        session.rollback()
        mark_failed(session, job_id, error_message=str(exc) or exc.__class__.__name__)
        session.commit()
        if reraise:
            raise
        return _require_job(session, job_id)

    mark_succeeded(session, job_id, result=result)
    session.commit()
    return _require_job(session, job_id)


def execute_registered_job(
    session: Session,
    job_id: str,
    registry: DurableJobRegistry,
    *,
    reraise: bool = True,
    claimed: bool = False,
) -> EcommerceJob:
    job = _require_job(session, job_id)
    registered_handler = registry.get(job.job_type)
    return execute_job(session, job_id, lambda payload: registered_handler(job_id, payload), reraise=reraise, claimed=claimed)
