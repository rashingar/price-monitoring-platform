"""Durable Ecommerce job inspection API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.config import DatabaseNotConfiguredError, sanitize_database_error
from ecommerce.db.session import session_scope
from ecommerce.jobs.durable import JOB_STATUSES, JobNotFoundError, JobStatus, get_job_by_id, job_to_dict, list_jobs, request_cancel

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class DurableJobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    payload: Any | None = None
    result: Any | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int
    cancel_requested: bool
    updated_at: datetime


class DurableJobListResponse(BaseModel):
    items: list[DurableJobResponse]


@router.get("", response_model=DurableJobListResponse)
def list_durable_jobs(
    job_type: str | None = None,
    status: JobStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    if status is not None and status not in JOB_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported job status.")
    try:
        with session_scope() as session:
            items = [job_to_dict(job) for job in list_jobs(session, job_type=job_type, status=status, limit=limit)]
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc
    return {"items": items}


@router.get("/{job_id}", response_model=DurableJobResponse)
def get_durable_job(job_id: str) -> dict[str, Any]:
    try:
        with session_scope() as session:
            job = get_job_by_id(session, job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            return job_to_dict(job)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


@router.post("/{job_id}/cancel", response_model=DurableJobResponse)
def cancel_durable_job(job_id: str) -> dict[str, Any]:
    try:
        with session_scope() as session:
            job = request_cancel(session, job_id)
            return job_to_dict(job)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


def _database_unavailable(exc: Exception) -> HTTPException:
    detail = {
        "message": "Ecommerce durable jobs require the Ecommerce database.",
        "code": "ecommerce_jobs_database_required",
        "error": sanitize_database_error(exc),
    }
    return HTTPException(status_code=503, detail=detail)
