"""Durable Ecommerce job repository helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ecommerce.db.models.jobs import EcommerceJob

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
JOB_STATUSES: tuple[JobStatus, ...] = ("queued", "running", "succeeded", "failed", "cancelled")
TERMINAL_JOB_STATUSES: tuple[JobStatus, ...] = ("succeeded", "failed", "cancelled")


class JobNotFoundError(KeyError):
    """Raised when a durable job id does not exist."""


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


def list_queued_jobs_for_worker(
    session: Session,
    *,
    job_type: str | None = None,
    job_types: Sequence[str] | None = None,
    limit: int = 1,
) -> list[EcommerceJob]:
    statement: Select[tuple[EcommerceJob]] = select(EcommerceJob).where(EcommerceJob.status == "queued")
    statement = _filter_job_type(statement, job_type=job_type, job_types=job_types)
    statement = statement.order_by(EcommerceJob.created_at.asc(), EcommerceJob.id.asc()).limit(_bounded_worker_limit(limit))
    return list(session.execute(statement).scalars())


def lease_queued_jobs_for_worker(
    session: Session,
    *,
    job_type: str | None = None,
    job_types: Sequence[str] | None = None,
    limit: int = 1,
    leased_at: datetime | None = None,
) -> list[EcommerceJob]:
    """Claim oldest queued jobs for this worker process.

    PostgreSQL uses row locks with SKIP LOCKED so concurrent local workers do
    not select the same queued rows. SQLite test databases ignore this locking
    behavior, but the status update still keeps the helper deterministic.
    """

    timestamp = leased_at or _now()
    statement: Select[tuple[EcommerceJob]] = select(EcommerceJob).where(EcommerceJob.status == "queued")
    statement = _filter_job_type(statement, job_type=job_type, job_types=job_types)
    statement = statement.order_by(EcommerceJob.created_at.asc(), EcommerceJob.id.asc()).limit(_bounded_worker_limit(limit))
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)

    jobs = list(session.execute(statement).scalars())
    for job in jobs:
        if job.cancel_requested:
            mark_cancelled(
                session,
                job.job_id,
                error_message="Cancellation requested before worker start.",
                completed_at=timestamp,
            )
        else:
            mark_running(session, job.job_id, started_at=timestamp)
    session.flush()
    return jobs


def list_stale_running_jobs(
    session: Session,
    *,
    stale_after_minutes: int,
    job_type: str | None = None,
    job_types: Sequence[str] | None = None,
    now: datetime | None = None,
) -> list[EcommerceJob]:
    cutoff = (now or _now()) - timedelta(minutes=max(1, int(stale_after_minutes)))
    last_activity = func.coalesce(EcommerceJob.heartbeat_at, EcommerceJob.started_at, EcommerceJob.updated_at, EcommerceJob.created_at)
    statement: Select[tuple[EcommerceJob]] = select(EcommerceJob).where(
        EcommerceJob.status == "running",
        last_activity <= cutoff,
    )
    statement = _filter_job_type(statement, job_type=job_type, job_types=job_types)
    statement = statement.order_by(EcommerceJob.created_at.asc(), EcommerceJob.id.asc())
    return list(session.execute(statement).scalars())


def fail_stale_running_jobs(
    session: Session,
    *,
    stale_after_minutes: int,
    job_type: str | None = None,
    job_types: Sequence[str] | None = None,
    now: datetime | None = None,
) -> list[EcommerceJob]:
    timestamp = now or _now()
    cutoff = timestamp - timedelta(minutes=max(1, int(stale_after_minutes)))
    jobs = list_stale_running_jobs(
        session,
        stale_after_minutes=stale_after_minutes,
        job_type=job_type,
        job_types=job_types,
        now=timestamp,
    )
    for job in jobs:
        mark_failed(
            session,
            job.job_id,
            error_message=(
                "Marked failed by Ecommerce durable job worker because the job "
                f"was still running with no heartbeat after {cutoff.isoformat()}."
            ),
            completed_at=timestamp,
        )
    session.flush()
    return jobs


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


def record_progress(
    session: Session,
    job_id: str,
    *,
    step: str,
    progress_at: datetime | None = None,
) -> EcommerceJob:
    job = _require_job(session, job_id)
    if job.status != "running":
        return job
    timestamp = progress_at or _now()
    existing_result = job.result_json if isinstance(job.result_json, dict) else {}
    job.result_json = {
        **existing_result,
        "progress": {
            "current_step": str(step),
            "updated_at": timestamp.isoformat(),
        },
    }
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


def _bounded_worker_limit(limit: int) -> int:
    return max(1, min(int(limit), 50))


def _filter_job_type(
    statement: Select[tuple[EcommerceJob]],
    *,
    job_type: str | None,
    job_types: Sequence[str] | None,
) -> Select[tuple[EcommerceJob]]:
    if job_type:
        return statement.where(EcommerceJob.job_type == job_type)
    if job_types is not None:
        values = tuple(dict.fromkeys(job_types))
        if not values:
            return statement.where(False)
        return statement.where(EcommerceJob.job_type.in_(values))
    return statement
