from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from product_factory.jobs.models import JobType, is_terminal_job_status
from product_factory.jobs.retry import (
    build_retry_from_artifacts_payload,
    build_start_from_scratch_payload,
)
from product_factory.jobs.runner import SequentialJobRunner
from product_factory.jobs.store import JobStore

from .artifact_resolver import resolve_job_artifacts
from .schemas import (
    ErrorResponse,
    AuthoringIntroJobRequest,
    AuthoringSeoJobRequest,
    FullPipelineJobRequest,
    JobArtifactsResponse,
    JobListResponse,
    JobLogsResponse,
    JobResponse,
    PrepareJobRequest,
    PublishJobRequest,
    RenderJobRequest,
    StopJobRequest,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])

_NOT_FOUND_RESPONSE = {
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Job not found.",
    }
}


def _request_payload(schema: Any) -> dict[str, Any]:
    if hasattr(schema, "model_dump"):
        return schema.model_dump()
    return schema.dict()


def _job_store(api_request: Request) -> JobStore:
    return api_request.app.state.job_store


def _job_runner(api_request: Request) -> SequentialJobRunner:
    return api_request.app.state.job_runner


def _enqueue_job(api_request: Request, job_type: JobType, payload: dict[str, Any]) -> JobResponse:
    record = _job_store(api_request).enqueue(job_type, payload)
    _job_runner(api_request).enqueue(record.job_id)
    return JobResponse.from_record(record)


def _get_job_response(api_request: Request, job_id: str) -> JobResponse:
    try:
        record = _job_store(api_request).get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.") from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobResponse.from_record(record)


@router.post(
    "/prepare",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def prepare_job(request: PrepareJobRequest, api_request: Request) -> JobResponse:
    return _enqueue_job(api_request, JobType.PREPARE, _request_payload(request))


@router.post(
    "/render",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def render_job(request: RenderJobRequest, api_request: Request) -> JobResponse:
    return _enqueue_job(api_request, JobType.RENDER, _request_payload(request))


@router.post(
    "/publish",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def publish_job(request: PublishJobRequest, api_request: Request) -> JobResponse:
    return _enqueue_job(api_request, JobType.PUBLISH, _request_payload(request))


@router.post(
    "/authoring/intro-text",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def authoring_intro_job(request: AuthoringIntroJobRequest, api_request: Request) -> JobResponse:
    return _enqueue_job(api_request, JobType.AUTHORING_INTRO, _request_payload(request))


@router.post(
    "/authoring/seo-meta",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def authoring_seo_job(request: AuthoringSeoJobRequest, api_request: Request) -> JobResponse:
    return _enqueue_job(api_request, JobType.AUTHORING_SEO, _request_payload(request))


@router.post(
    "/full-pipeline",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def full_pipeline_job(request: FullPipelineJobRequest, api_request: Request) -> JobResponse:
    return _enqueue_job(api_request, JobType.FULL_PIPELINE, _request_payload(request))


@router.post("/{job_id}/stop", response_model=JobResponse, responses=_NOT_FOUND_RESPONSE)
def stop_job(job_id: str, api_request: Request, request: StopJobRequest | None = None) -> JobResponse:
    try:
        record = _job_runner(api_request).stop_job(
            job_id,
            reason=request.reason if request is not None else None,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.") from exc
    return JobResponse.from_record(record)


@router.post("/{job_id}/retry", response_model=JobResponse, responses=_NOT_FOUND_RESPONSE)
def retry_job(job_id: str, api_request: Request) -> JobResponse:
    try:
        record = _job_store(api_request).get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.") from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if not is_terminal_job_status(record.status):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only terminal jobs can be retried.")
    if record.job_type == JobType.FULL_PIPELINE:
        try:
            return _enqueue_job(
                api_request,
                JobType.FULL_PIPELINE,
                build_retry_from_artifacts_payload(record),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _enqueue_job(api_request, record.job_type, record.payload)


@router.post("/{job_id}/start", response_model=JobResponse, responses=_NOT_FOUND_RESPONSE)
def start_job(job_id: str, api_request: Request) -> JobResponse:
    try:
        record = _job_store(api_request).get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.") from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if not is_terminal_job_status(record.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only terminal jobs can be started again.",
        )
    if record.job_type != JobType.FULL_PIPELINE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start from scratch is supported only for full_pipeline jobs.",
        )
    try:
        return _enqueue_job(
            api_request,
            JobType.FULL_PIPELINE,
            build_start_from_scratch_payload(record),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=JobListResponse)
def list_jobs(api_request: Request) -> JobListResponse:
    return JobListResponse(
        jobs=[JobResponse.from_record(record) for record in _job_store(api_request).list_jobs()]
    )


@router.get("/by-model/{model}", response_model=JobListResponse)
def list_jobs_by_model(model: str, api_request: Request) -> JobListResponse:
    return JobListResponse(
        jobs=[
            JobResponse.from_record(record)
            for record in reversed(_job_store(api_request).list_jobs_for_model(model))
        ]
    )


@router.get("/{job_id}", response_model=JobResponse, responses=_NOT_FOUND_RESPONSE)
def get_job(job_id: str, api_request: Request) -> JobResponse:
    return _get_job_response(api_request, job_id)


@router.get("/{job_id}/logs", response_model=JobLogsResponse, responses=_NOT_FOUND_RESPONSE)
def get_job_logs(job_id: str, api_request: Request) -> JobLogsResponse:
    _get_job_response(api_request, job_id)
    return JobLogsResponse(job_id=job_id, lines=_job_store(api_request).read_logs(job_id))


@router.get("/{job_id}/artifacts", response_model=JobArtifactsResponse, responses=_NOT_FOUND_RESPONSE)
def get_job_artifacts(job_id: str, api_request: Request) -> JobArtifactsResponse:
    try:
        record = _job_store(api_request).get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.") from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobArtifactsResponse.from_artifacts(job_id, resolve_job_artifacts(record))
