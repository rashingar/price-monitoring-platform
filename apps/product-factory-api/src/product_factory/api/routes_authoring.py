from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from product_factory.jobs.models import JobType

from ..services.authoring_service import (
    PreparedAuthoringArtifactsNotFoundError,
    get_authoring_status,
)
from .schemas import AuthoringStatusResponse, ErrorResponse, JobResponse


router = APIRouter(prefix="/authoring", tags=["authoring"])

_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Prepared artifacts not found."},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Authoring validation failed."},
}


@router.get("/{model}", response_model=AuthoringStatusResponse, responses=_ERROR_RESPONSES)
def get_authoring(model: str) -> AuthoringStatusResponse:
    try:
        return get_authoring_status(model)
    except PreparedAuthoringArtifactsNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{model}/intro-text",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_intro_text(model: str, api_request: Request) -> JobResponse:
    return _enqueue_authoring_job(api_request, JobType.AUTHORING_INTRO, model, retry=False)


@router.post(
    "/{model}/intro-text/retry",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_intro_text_retry(model: str, api_request: Request) -> JobResponse:
    return _enqueue_authoring_job(api_request, JobType.AUTHORING_INTRO, model, retry=True)


@router.post(
    "/{model}/seo-meta",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_seo_meta(model: str, api_request: Request) -> JobResponse:
    return _enqueue_authoring_job(api_request, JobType.AUTHORING_SEO, model, retry=False)


@router.post(
    "/{model}/seo-meta/retry",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_seo_meta_retry(model: str, api_request: Request) -> JobResponse:
    return _enqueue_authoring_job(api_request, JobType.AUTHORING_SEO, model, retry=True)


def _enqueue_authoring_job(api_request: Request, job_type: JobType, model: str, *, retry: bool) -> JobResponse:
    normalized_model = str(model or "").strip()
    if not normalized_model:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="model must not be empty")
    record = api_request.app.state.job_store.enqueue(job_type, {"model": normalized_model, "retry": retry})
    api_request.app.state.job_runner.enqueue(record.job_id)
    return JobResponse.from_record(record)
