"""Small DB-backed durable job primitives for Ecommerce workflows."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ecommerce.db.models import EcommerceJob

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
JobHandler = Callable[[Any], Any]

JOB_STATUSES: tuple[JobStatus, ...] = ("queued", "running", "succeeded", "failed", "cancelled")
TERMINAL_JOB_STATUSES: tuple[JobStatus, ...] = ("succeeded", "failed", "cancelled")


class JobNotFoundError(KeyError):
    """Raised when a durable job id does not exist."""


class DurableJobRegistry:
    """In-process handler registry for synchronous execution.

    TODO: Reuse this registry from a future worker command that leases queued
    rows and executes them outside request handling.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler:
        try:
            return self._handlers[job_type]
        except KeyError as exc:
            raise KeyError(f"No durable job handler registered for job_type={job_type!r}.") from exc


def create_queued_job(
    session: Session,
    *,
    job_type: str,
    payload: Any | None = None,
    job_id: str | None = None,
    created_at: datetime | None = None,
) -> EcommerceJob:
    timestamp = created_at or _now()
    job = EcommerceJob(
        job_id=job_id or _new_job_id(),
        job_type=job_type,
        status="queued",
        payload_json=payload,
        result_json=None,
        error_message=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(job)
    session.flush()
    return job


def get_job_by_id(session: Session, job_id: str) -> EcommerceJob | None:
    return session.execute(select(EcommerceJob).where(EcommerceJob.job_id == job_id).limit(1)).scalar_one_or_none()


def list_jobs(
    session: Session,
    *,
    job_type: str | None = None,
    status: JobStatus | None = None,
    limit: int = 100,
) -> list[EcommerceJob]:
    statement: Select[tuple[EcommerceJob]] = select(EcommerceJob)
    if job_type:
        statement = statement.where(EcommerceJob.job_type == job_type)
    if status:
        statement = statement.where(EcommerceJob.status == status)
    bounded_limit = max(1, min(int(limit), 500))
    statement = statement.order_by(EcommerceJob.created_at.desc(), EcommerceJob.id.desc()).limit(bounded_limit)
    return list(session.execute(statement).scalars())


def mark_running(session: Session, job_id: str, *, started_at: datetime | None = None) -> EcommerceJob:
    job = _require_job(session, job_id)
    if job.status in TERMINAL_JOB_STATUSES:
        raise ValueError(f"Cannot mark terminal job {job_id!r} as running.")
    timestamp = started_at or _now()
    job.status = "running"
    job.started_at = timestamp
    job.heartbeat_at = timestamp
    job.completed_at = None
    job.error_message = None
    job.attempt_count = int(job.attempt_count or 0) + 1
    job.updated_at = timestamp
    session.flush()
    return job


def heartbeat(session: Session, job_id: str, *, heartbeat_at: datetime | None = None) -> EcommerceJob:
    job = _require_job(session, job_id)
    timestamp = heartbeat_at or _now()
    job.heartbeat_at = timestamp
    job.updated_at = timestamp
    session.flush()
    return job


def mark_succeeded(
    session: Session,
    job_id: str,
    *,
    result: Any | None = None,
    completed_at: datetime | None = None,
) -> EcommerceJob:
    job = _require_job(session, job_id)
    timestamp = completed_at or _now()
    job.status = "succeeded"
    job.result_json = result
    job.error_message = None
    job.completed_at = timestamp
    job.updated_at = timestamp
    session.flush()
    return job


def mark_failed(
    session: Session,
    job_id: str,
    *,
    error_message: str,
    completed_at: datetime | None = None,
) -> EcommerceJob:
    job = _require_job(session, job_id)
    timestamp = completed_at or _now()
    job.status = "failed"
    job.error_message = _safe_error_message(error_message)
    job.completed_at = timestamp
    job.updated_at = timestamp
    session.flush()
    return job


def request_cancel(session: Session, job_id: str, *, requested_at: datetime | None = None) -> EcommerceJob:
    job = _require_job(session, job_id)
    timestamp = requested_at or _now()
    job.cancel_requested = True
    job.updated_at = timestamp
    session.flush()
    return job


def mark_cancelled(
    session: Session,
    job_id: str,
    *,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> EcommerceJob:
    job = _require_job(session, job_id)
    timestamp = completed_at or _now()
    job.status = "cancelled"
    job.error_message = _safe_error_message(error_message) if error_message else None
    job.completed_at = timestamp
    job.updated_at = timestamp
    session.flush()
    return job


def execute_job(session: Session, job_id: str, handler: JobHandler, *, reraise: bool = True) -> EcommerceJob:
    job = _require_job(session, job_id)
    if job.cancel_requested:
        mark_cancelled(session, job_id, error_message="Cancellation requested before start.")
        session.commit()
        return _require_job(session, job_id)

    mark_running(session, job_id)
    session.commit()

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


def execute_registered_job(session: Session, job_id: str, registry: DurableJobRegistry, *, reraise: bool = True) -> EcommerceJob:
    job = _require_job(session, job_id)
    return execute_job(session, job_id, registry.get(job.job_type), reraise=reraise)


def job_to_dict(job: EcommerceJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "payload": job.payload_json,
        "result": job.result_json,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "heartbeat_at": job.heartbeat_at,
        "completed_at": job.completed_at,
        "attempt_count": job.attempt_count,
        "cancel_requested": job.cancel_requested,
        "updated_at": job.updated_at,
    }


def _require_job(session: Session, job_id: str) -> EcommerceJob:
    job = get_job_by_id(session, job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    return job


def _new_job_id() -> str:
    return f"job_{uuid4().hex}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_error_message(message: str) -> str:
    return str(message or "").strip()[:1000]
