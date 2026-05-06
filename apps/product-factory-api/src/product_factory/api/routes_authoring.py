from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..services.authoring_service import (
    PreparedAuthoringArtifactsNotFoundError,
    get_authoring_status,
    run_intro_text_authoring,
    run_seo_meta_authoring,
)
from ..services.errors import ServiceError, ServiceErrorCode
from .schemas import AuthoringStatusResponse, ErrorResponse


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


@router.post("/{model}/intro-text", response_model=AuthoringStatusResponse, responses=_ERROR_RESPONSES)
def post_intro_text(model: str) -> AuthoringStatusResponse:
    return _run_authoring(lambda: run_intro_text_authoring(model, retry=False))


@router.post("/{model}/intro-text/retry", response_model=AuthoringStatusResponse, responses=_ERROR_RESPONSES)
def post_intro_text_retry(model: str) -> AuthoringStatusResponse:
    return _run_authoring(lambda: run_intro_text_authoring(model, retry=True))


@router.post("/{model}/seo-meta", response_model=AuthoringStatusResponse, responses=_ERROR_RESPONSES)
def post_seo_meta(model: str) -> AuthoringStatusResponse:
    return _run_authoring(lambda: run_seo_meta_authoring(model, retry=False))


@router.post("/{model}/seo-meta/retry", response_model=AuthoringStatusResponse, responses=_ERROR_RESPONSES)
def post_seo_meta_retry(model: str) -> AuthoringStatusResponse:
    return _run_authoring(lambda: run_seo_meta_authoring(model, retry=True))


def _run_authoring(callback):
    try:
        status_response = callback()
    except PreparedAuthoringArtifactsNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ServiceError as exc:
        if exc.code == ServiceErrorCode.VALIDATION_FAILURE.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": exc.message, **exc.details}) from exc
        raise
    if not status_response.ready_for_render:
        invalid = [
            task
            for task in (status_response.intro_text, status_response.seo_meta)
            if task.status == "invalid"
        ]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Authoring validation failed.",
                    "render_block_reasons": status_response.render_block_reasons,
                },
            )
    return status_response
