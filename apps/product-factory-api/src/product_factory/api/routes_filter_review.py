from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..services.filter_review_service import (
    PreparedArtifactsNotFoundError,
    approve_filter_review,
    get_filter_review_state,
    save_filter_review,
)
from .schemas import ErrorResponse, FilterReviewResponse, FilterReviewUpdateRequest

router = APIRouter(prefix="/filter-review", tags=["filter-review"])

_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Prepared artifacts not found.",
    },
}


@router.get("/{model}", response_model=FilterReviewResponse, responses=_ERROR_RESPONSES)
def get_filter_review(model: str) -> FilterReviewResponse:
    try:
        return get_filter_review_state(model)
    except PreparedArtifactsNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.put("/{model}", response_model=FilterReviewResponse, responses=_ERROR_RESPONSES)
def put_filter_review(
    model: str, request: FilterReviewUpdateRequest
) -> FilterReviewResponse:
    try:
        return save_filter_review(model, request)
    except PreparedArtifactsNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/{model}/approve", response_model=FilterReviewResponse, responses=_ERROR_RESPONSES
)
def post_filter_review_approve(model: str) -> FilterReviewResponse:
    try:
        return approve_filter_review(model)
    except PreparedArtifactsNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
