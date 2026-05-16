"""Candidate routes for the Source URL Agent API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.db.repositories.source_url_candidates import (
    SourceUrlCandidateListFilters,
    get_source_url_agent_candidate as get_candidate,
    list_source_url_agent_candidates as list_candidates,
    matching_source_url_id_for_candidate,
)
from ecommerce.db.session import session_scope
from ecommerce.source_url_agent.review_service import (
    InvalidSourceUrlCandidateReviewError,
    SourceUrlCandidateNotFoundError,
    SourceUrlCandidatePromotionError,
    SourceUrlCandidateReviewCommand,
    review_source_url_agent_candidate as review_candidate,
)

from .errors import safe_db_error
from .schemas import SourceUrlCandidateReviewRequest
from .serializers import candidate_review_panel_payload, candidate_to_dict, source_url_promotion_to_dict
from .validation import require_catalog_database_ready

router = APIRouter()


@router.get("/candidates")
def list_source_url_agent_candidates(
    status: str | None = None,
    source_name: str | None = None,
    run_id: str | None = None,
    model: str | None = None,
    catalog_product_id: str | None = None,
    min_confidence: str | None = None,
    max_confidence: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    require_catalog_database_ready()
    try:
        with session_scope() as session:
            page = list_candidates(
                session,
                SourceUrlCandidateListFilters(
                    status=status,
                    source_name=source_name,
                    run_id=run_id,
                    model=model,
                    catalog_product_id=catalog_product_id,
                    min_confidence=min_confidence,
                    max_confidence=max_confidence,
                ),
                limit=limit,
                offset=offset,
            )
            items = [candidate_to_dict(row) for row in page.items]
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate query failed: {safe_db_error(exc)}") from exc
    return {"items": items, "total": page.total, "limit": page.limit, "offset": page.offset}


@router.get("/candidates/{candidate_id}")
def get_source_url_agent_candidate(candidate_id: int) -> dict[str, Any]:
    require_catalog_database_ready()
    try:
        with session_scope() as session:
            candidate = get_candidate(session, candidate_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail="Source URL candidate not found.")
            payload = candidate_to_dict(candidate)
            payload["source_url_id"] = matching_source_url_id_for_candidate(session, candidate)
            payload["review_panel"] = candidate_review_panel_payload(candidate)
            return payload
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate query failed: {safe_db_error(exc)}") from exc


@router.patch("/candidates/{candidate_id}/review")
def review_source_url_agent_candidate(candidate_id: int, request: SourceUrlCandidateReviewRequest) -> dict[str, Any]:
    require_catalog_database_ready()
    try:
        with session_scope() as session:
            result = review_candidate(
                session,
                candidate_id,
                SourceUrlCandidateReviewCommand(
                    decision=request.decision,
                    reviewed_url=request.reviewed_url,
                    review_notes=request.review_notes,
                    reviewed_by=request.reviewed_by,
                ),
            )
            payload = candidate_to_dict(result.candidate)
            payload["source_url"] = source_url_promotion_to_dict(result.source_url_promotion)
            return payload
    except HTTPException:
        raise
    except SourceUrlCandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidSourceUrlCandidateReviewError, SourceUrlCandidatePromotionError, LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate review failed: {safe_db_error(exc)}") from exc
