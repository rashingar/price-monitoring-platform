"""Catalog DB update API backed by durable Ecommerce jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog_update import (
    CATALOG_UPDATE_JOB_TYPE,
    run_catalog_update_durable_job,
)
from ecommerce.db.config import DatabaseNotConfiguredError, sanitize_database_error
from ecommerce.db.policy import (
    catalog_database_unavailable_detail,
    collect_catalog_database_readiness,
)
from ecommerce.db.session import create_session_factory, session_scope
from ecommerce.db.repositories.jobs import create_queued_job, job_to_dict, list_jobs
from ecommerce.jobs.durable import execute_job
from ecommerce.jobs.execution_policy import api_execute_durable_jobs_inline_enabled

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class CatalogUpdateJobResponse(BaseModel):
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
    status_url: str | None = None


@router.post("/update-db", response_model=CatalogUpdateJobResponse)
def start_catalog_update(background_tasks: BackgroundTasks) -> dict[str, Any]:
    _require_catalog_update_database_ready()
    try:
        with session_scope() as session:
            job = create_queued_job(
                session,
                job_type=CATALOG_UPDATE_JOB_TYPE,
                payload={"source": "opencart_export"},
            )
            payload = _job_response(job_to_dict(job))
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc

    if api_execute_durable_jobs_inline_enabled():
        background_tasks.add_task(_execute_catalog_update_job, payload["job_id"])
    return payload


@router.get("/update-db/latest", response_model=CatalogUpdateJobResponse | None)
def get_latest_catalog_update() -> dict[str, Any] | None:
    try:
        with session_scope() as session:
            jobs = list_jobs(session, job_type=CATALOG_UPDATE_JOB_TYPE, limit=1)
            if not jobs:
                return None
            return _job_response(job_to_dict(jobs[0]))
    except DatabaseNotConfiguredError as exc:
        raise _database_unavailable(exc) from exc
    except SQLAlchemyError as exc:
        raise _database_unavailable(exc) from exc


def _execute_catalog_update_job(job_id: str) -> None:
    session = create_session_factory()()
    try:
        execute_job(
            session,
            job_id,
            lambda _payload: run_catalog_update_durable_job(job_id),
            reraise=False,
        )
    finally:
        session.close()


def _require_catalog_update_database_ready() -> None:
    readiness = collect_catalog_database_readiness()
    if bool(readiness.get("configured", False)) and bool(
        readiness.get("reachable", False)
    ):
        return
    raise HTTPException(
        status_code=503, detail=catalog_database_unavailable_detail(readiness)
    )


def _job_response(payload: dict[str, Any]) -> dict[str, Any]:
    payload["status_url"] = f"/api/jobs/{payload['job_id']}"
    return payload


def _database_unavailable(exc: Exception) -> HTTPException:
    detail = {
        "message": "Ecommerce catalog update requires the Ecommerce database and durable jobs table.",
        "code": "catalog_update_database_required",
        "error": sanitize_database_error(exc),
    }
    return HTTPException(status_code=503, detail=detail)
