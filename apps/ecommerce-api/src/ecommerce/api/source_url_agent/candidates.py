"""Candidate routes for the Source URL Agent API."""

from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate
from ecommerce.db.session import session_scope
from ecommerce.source_urls import normalize_source_url
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
from .validation import like_value, optional_decimal, optional_text
from .validation import require_catalog_database_ready as _real_require_catalog_database_ready

router = APIRouter()
_FACADE_MODULE = "ecommerce.api.routes_source_url_agent"


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
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            filters = _candidate_filters(
                status=status,
                source_name=source_name,
                run_id=run_id,
                model=model,
                catalog_product_id=catalog_product_id,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
            )
            total = int(session.execute(select(func.count(SourceUrlCandidate.id)).where(*filters)).scalar_one())
            statement = (
                select(SourceUrlCandidate)
                .where(*filters)
                .order_by(SourceUrlCandidate.created_at.desc(), SourceUrlCandidate.id.desc())
                .limit(limit)
                .offset(offset)
            )
            items = [candidate_to_dict(row) for row in session.execute(statement).scalars().all()]
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate query failed: {_safe_db_error(exc)}") from exc
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/candidates/{candidate_id}")
def get_source_url_agent_candidate(candidate_id: int) -> dict[str, Any]:
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            candidate = session.get(SourceUrlCandidate, candidate_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail="Source URL candidate not found.")
            payload = candidate_to_dict(candidate)
            payload["source_url_id"] = _matching_source_url_id(session, candidate)
            payload["review_panel"] = candidate_review_panel_payload(candidate)
            return payload
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate query failed: {_safe_db_error(exc)}") from exc


def _matching_source_url_id(session: Session, candidate: SourceUrlCandidate) -> int | None:
    if candidate.catalog_product_id is None or not candidate.candidate_url:
        return None
    try:
        normalized = normalize_source_url(candidate.candidate_url)
    except Exception:
        return None
    statement = select(SourceUrl.id).where(
        SourceUrl.catalog_product_id == candidate.catalog_product_id,
        SourceUrl.url_normalized == normalized,
    )
    value = session.execute(statement).scalar_one_or_none()
    return int(value) if value is not None else None


@router.patch("/candidates/{candidate_id}/review")
def review_source_url_agent_candidate(candidate_id: int, request: SourceUrlCandidateReviewRequest) -> dict[str, Any]:
    _require_catalog_database_ready()
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
        raise HTTPException(status_code=500, detail=f"Source URL candidate review failed: {_safe_db_error(exc)}") from exc


def _candidate_filters(
    *,
    status: str | None,
    source_name: str | None,
    run_id: str | None,
    model: str | None,
    catalog_product_id: str | None,
    min_confidence: str | None,
    max_confidence: str | None,
) -> list[Any]:
    filters: list[Any] = []
    status_text = optional_text(status)
    if status_text and status_text.casefold() != "all":
        filters.append(SourceUrlCandidate.status == status_text)
    source_text = optional_text(source_name)
    if source_text:
        filters.append(SourceUrlCandidate.source_name.ilike(f"%{like_value(source_text)}%"))
    run_id_text = optional_text(run_id)
    if run_id_text:
        filters.append(SourceUrlCandidate.run_id == run_id_text)
    model_text = optional_text(model)
    if model_text:
        filters.append(SourceUrlCandidate.model.ilike(f"%{like_value(model_text)}%"))
    product_id_text = optional_text(catalog_product_id)
    if product_id_text:
        try:
            filters.append(SourceUrlCandidate.catalog_product_id == int(product_id_text))
        except ValueError:
            raise HTTPException(status_code=400, detail="catalog_product_id must be an integer.") from None
    min_value = optional_decimal(min_confidence, "min_confidence")
    if min_value is not None:
        filters.append(SourceUrlCandidate.confidence_score >= min_value)
    max_value = optional_decimal(max_confidence, "max_confidence")
    if max_value is not None:
        filters.append(SourceUrlCandidate.confidence_score <= max_value)
    return filters


def _require_catalog_database_ready() -> None:
    hook = _facade_attr("_require_catalog_database_ready")
    if hook is not None and hook is not _require_catalog_database_ready:
        return hook()
    return _real_require_catalog_database_ready()


def _safe_db_error(exc: Exception) -> str:
    return safe_db_error(exc)


def _facade_attr(name: str) -> Any:
    facade = sys.modules.get(_FACADE_MODULE)
    if facade is None:
        return None
    return getattr(facade, name, None)
