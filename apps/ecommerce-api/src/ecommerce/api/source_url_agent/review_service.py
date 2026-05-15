"""Candidate review application for Source URL Agent API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import SourceUrlCandidate
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url, source_url_to_dict

from .schemas import SourceUrlCandidateReviewRequest
from .validation import optional_text


def apply_candidate_review(
    session: Session,
    candidate: SourceUrlCandidate,
    request: SourceUrlCandidateReviewRequest,
) -> dict[str, Any] | None:
    decision = request.decision
    reviewed_by = optional_text(request.reviewed_by) or "operator"
    reviewed_at = now()
    review_notes = optional_text(request.review_notes)
    promoted = None

    if decision == "accept":
        candidate.status = "accepted"
        promoted = promote_candidate_url(
            session,
            candidate,
            reviewed_url=optional_text(request.reviewed_url) or optional_text(candidate.candidate_url),
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            review_notes=review_notes,
        )
    elif decision == "replace_url":
        reviewed_url = optional_text(request.reviewed_url)
        if not reviewed_url:
            raise HTTPException(status_code=400, detail="reviewed_url is required for replace_url.")
        candidate.status = "accepted"
        promoted = promote_candidate_url(
            session,
            candidate,
            reviewed_url=reviewed_url,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            review_notes=review_notes,
        )
    elif decision == "reject":
        candidate.status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid review decision.")

    candidate.reviewed_by = reviewed_by
    candidate.reviewed_at = reviewed_at
    candidate.notes = review_notes_text(candidate.notes, decision=decision, reviewed_by=reviewed_by, reviewed_at=reviewed_at, notes=review_notes)
    candidate.updated_at = reviewed_at
    session.flush()
    return promoted


def promote_candidate_url(
    session: Session,
    candidate: SourceUrlCandidate,
    *,
    reviewed_url: str | None,
    reviewed_by: str,
    reviewed_at: datetime,
    review_notes: str | None,
) -> dict[str, Any]:
    if candidate.catalog_product_id is None:
        raise ValueError("catalog_product_id is required to promote a source URL.")
    if not reviewed_url:
        raise ValueError("candidate_url is required to promote a source URL.")
    notes = promotion_notes(candidate, reviewed_by=reviewed_by, reviewed_at=reviewed_at, review_notes=review_notes)
    upsert = create_or_update_imported_source_url(
        session,
        catalog_product_id=int(candidate.catalog_product_id),
        url=reviewed_url,
        source_name=candidate.source_name,
        url_type="discovered",
        trust_level="manual",
        status="active",
        last_seen_at=reviewed_at,
        last_success_at=reviewed_at,
        notes=notes,
        apply=True,
    )
    return {
        "action": upsert.action,
        "source_url_id": upsert.source_url_id,
        "changed_fields": list(upsert.changed_fields),
        "item": source_url_to_dict(upsert.row) if upsert.row is not None else None,
    }


def promotion_notes(
    candidate: SourceUrlCandidate,
    *,
    reviewed_by: str,
    reviewed_at: datetime,
    review_notes: str | None,
) -> str:
    parts = [
        f"Source URL candidate review accepted candidate_id={candidate.id}",
        f"run_id={candidate.run_id}",
        f"match_method={candidate.match_method}",
        f"confidence={candidate.confidence_score}",
        f"reviewed_by={reviewed_by}",
        f"reviewed_at={reviewed_at.isoformat()}",
    ]
    if review_notes:
        parts.append(f"notes={review_notes}")
    return "; ".join(parts)


def review_notes_text(
    current: str | None,
    *,
    decision: str,
    reviewed_by: str,
    reviewed_at: datetime,
    notes: str | None,
) -> str:
    entry = f"Review {decision} by {reviewed_by} at {reviewed_at.isoformat()}"
    if notes:
        entry = f"{entry}: {notes}"
    existing = optional_text(current)
    return f"{existing}\n{entry}" if existing else entry


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
