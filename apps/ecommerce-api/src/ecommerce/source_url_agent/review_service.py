"""Source URL Agent candidate review domain service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url

ReviewDecision = Literal["accept", "reject", "replace_url"]


class SourceUrlCandidateReviewError(Exception):
    """Base error for Source URL Agent candidate review failures."""


class SourceUrlCandidateNotFoundError(SourceUrlCandidateReviewError):
    """Raised when a requested candidate does not exist."""


class InvalidSourceUrlCandidateReviewError(SourceUrlCandidateReviewError):
    """Raised when a review command is not valid."""


class SourceUrlCandidatePromotionError(SourceUrlCandidateReviewError):
    """Raised when an accepted candidate cannot be promoted."""


@dataclass(frozen=True)
class SourceUrlCandidateReviewCommand:
    decision: ReviewDecision | str
    reviewed_url: str | None = None
    review_notes: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


@dataclass(frozen=True)
class SourceUrlCandidatePromotionResult:
    action: str
    source_url_id: int | None
    changed_fields: list[str]
    row: SourceUrl | None


@dataclass(frozen=True)
class SourceUrlCandidateReviewResult:
    candidate: SourceUrlCandidate
    source_url_promotion: SourceUrlCandidatePromotionResult | None


def review_source_url_agent_candidate(
    session: Session,
    candidate_id: int,
    command: SourceUrlCandidateReviewCommand,
) -> SourceUrlCandidateReviewResult:
    candidate = session.get(SourceUrlCandidate, candidate_id)
    if candidate is None:
        raise SourceUrlCandidateNotFoundError("Source URL candidate not found.")
    return apply_candidate_review(session, candidate, command)


def apply_candidate_review(
    session: Session,
    candidate: SourceUrlCandidate,
    command: SourceUrlCandidateReviewCommand,
) -> SourceUrlCandidateReviewResult:
    decision = command.decision
    reviewed_by = _optional_text(command.reviewed_by) or "operator"
    reviewed_at = command.reviewed_at or _now()
    review_notes = _optional_text(command.review_notes)
    promoted = None

    if decision == "accept":
        candidate.status = "accepted"
        promoted = promote_candidate_url(
            session,
            candidate,
            reviewed_url=_optional_text(command.reviewed_url) or _optional_text(candidate.candidate_url),
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            review_notes=review_notes,
        )
    elif decision == "replace_url":
        reviewed_url = _optional_text(command.reviewed_url)
        if not reviewed_url:
            raise InvalidSourceUrlCandidateReviewError("reviewed_url is required for replace_url.")
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
        raise InvalidSourceUrlCandidateReviewError("Invalid review decision.")

    candidate.reviewed_by = reviewed_by
    candidate.reviewed_at = reviewed_at
    candidate.notes = review_notes_text(candidate.notes, decision=str(decision), reviewed_by=reviewed_by, reviewed_at=reviewed_at, notes=review_notes)
    candidate.updated_at = reviewed_at
    session.flush()
    return SourceUrlCandidateReviewResult(candidate=candidate, source_url_promotion=promoted)


def promote_candidate_url(
    session: Session,
    candidate: SourceUrlCandidate,
    *,
    reviewed_url: str | None,
    reviewed_by: str,
    reviewed_at: datetime,
    review_notes: str | None,
) -> SourceUrlCandidatePromotionResult:
    if candidate.catalog_product_id is None:
        raise SourceUrlCandidatePromotionError("catalog_product_id is required to promote a source URL.")
    if not reviewed_url:
        raise SourceUrlCandidatePromotionError("candidate_url is required to promote a source URL.")
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
    return SourceUrlCandidatePromotionResult(
        action=upsert.action,
        source_url_id=upsert.source_url_id,
        changed_fields=list(upsert.changed_fields),
        row=upsert.row,
    )


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
    existing = _optional_text(current)
    return f"{existing}\n{entry}" if existing else entry


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
