"""Read queries for Source URL Agent candidate history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun
from ecommerce.source_urls import normalize_source_url

SOURCE_URL_CANDIDATE_STATUS_ORDER = {
    "accepted": 0,
    "needs_review": 1,
    "pending": 2,
    "rejected": 3,
    "not_found": 4,
    "error": 5,
}
SOURCE_URL_CANDIDATE_COUNT_STATUSES = (
    "accepted",
    "needs_review",
    "pending",
    "rejected",
    "not_found",
    "error",
)


@dataclass(frozen=True)
class ProductSourceUrlCandidateRunGroup:
    run_id: str
    run: SourceUrlDiscoveryRun | None
    counts: dict[str, int]
    candidates: list[SourceUrlCandidate]
    latest_candidate_created_at: datetime | None


@dataclass(frozen=True)
class ProductSourceUrlCandidateHistory:
    catalog_product_id: int
    product_exists: bool
    items: list[ProductSourceUrlCandidateRunGroup]
    total_candidates: int
    warnings: list[str]


@dataclass(frozen=True)
class SourceUrlCandidateListFilters:
    status: str | None = None
    source_name: str | None = None
    run_id: str | None = None
    model: str | None = None
    catalog_product_id: str | None = None
    min_confidence: str | None = None
    max_confidence: str | None = None


@dataclass(frozen=True)
class SourceUrlCandidateListPage:
    items: list[SourceUrlCandidate]
    total: int
    limit: int
    offset: int


def list_source_url_agent_candidates(
    session: Session,
    filters: SourceUrlCandidateListFilters,
    *,
    limit: int,
    offset: int,
) -> SourceUrlCandidateListPage:
    query_filters = source_url_agent_candidate_filters(filters)
    total = int(session.execute(select(func.count(SourceUrlCandidate.id)).where(*query_filters)).scalar_one())
    statement = (
        select(SourceUrlCandidate)
        .where(*query_filters)
        .order_by(SourceUrlCandidate.created_at.desc(), SourceUrlCandidate.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(session.execute(statement).scalars().all())
    return SourceUrlCandidateListPage(items=items, total=total, limit=limit, offset=offset)


def source_url_agent_candidate_filters(filters: SourceUrlCandidateListFilters) -> list[Any]:
    query_filters: list[Any] = []
    status_text = _optional_text(filters.status)
    if status_text and status_text.casefold() != "all":
        query_filters.append(SourceUrlCandidate.status == status_text)
    source_text = _optional_text(filters.source_name)
    if source_text:
        query_filters.append(SourceUrlCandidate.source_name.ilike(_contains_pattern(source_text), escape="\\"))
    run_id_text = _optional_text(filters.run_id)
    if run_id_text:
        query_filters.append(SourceUrlCandidate.run_id == run_id_text)
    model_text = _optional_text(filters.model)
    if model_text:
        query_filters.append(SourceUrlCandidate.model.ilike(_contains_pattern(model_text), escape="\\"))
    product_id_text = _optional_text(filters.catalog_product_id)
    if product_id_text:
        try:
            query_filters.append(SourceUrlCandidate.catalog_product_id == int(product_id_text))
        except ValueError:
            raise ValueError("catalog_product_id must be an integer.") from None
    min_value = _optional_decimal(filters.min_confidence, "min_confidence")
    if min_value is not None:
        query_filters.append(SourceUrlCandidate.confidence_score >= min_value)
    max_value = _optional_decimal(filters.max_confidence, "max_confidence")
    if max_value is not None:
        query_filters.append(SourceUrlCandidate.confidence_score <= max_value)
    return query_filters


def get_source_url_agent_candidate(session: Session, candidate_id: int) -> SourceUrlCandidate | None:
    return session.get(SourceUrlCandidate, candidate_id)


def matching_source_url_id_for_candidate(session: Session, candidate: SourceUrlCandidate) -> int | None:
    if candidate.catalog_product_id is None or not candidate.candidate_url:
        return None
    try:
        normalized = normalize_source_url(candidate.candidate_url)
    except Exception:
        return None
    value = session.execute(
        select(SourceUrl.id).where(
            SourceUrl.catalog_product_id == candidate.catalog_product_id,
            SourceUrl.url_normalized == normalized,
        )
    ).scalar_one_or_none()
    return int(value) if value is not None else None


def get_product_source_url_candidate_history(
    session: Session,
    catalog_product_id: int,
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
) -> ProductSourceUrlCandidateHistory:
    product_exists = (
        session.execute(
            select(CatalogProductRow.id).where(
                CatalogProductRow.id == catalog_product_id,
                CatalogProductRow.catalog_source == catalog_source,
                CatalogProductRow.active.is_(True),
            )
        ).scalar_one_or_none()
        is not None
    )
    if not product_exists:
        return ProductSourceUrlCandidateHistory(
            catalog_product_id=catalog_product_id,
            product_exists=False,
            items=[],
            total_candidates=0,
            warnings=[],
        )

    candidates = list(
        session.execute(
            select(SourceUrlCandidate)
            .where(SourceUrlCandidate.catalog_product_id == catalog_product_id)
            .order_by(SourceUrlCandidate.created_at.desc(), SourceUrlCandidate.id.desc())
        )
        .scalars()
        .all()
    )
    if not candidates:
        return ProductSourceUrlCandidateHistory(
            catalog_product_id=catalog_product_id,
            product_exists=True,
            items=[],
            total_candidates=0,
            warnings=[],
        )

    run_ids = sorted({candidate.run_id for candidate in candidates if candidate.run_id})
    runs_by_id = {
        row.run_id: row
        for row in session.execute(
            select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id.in_(run_ids))
        )
        .scalars()
        .all()
    }

    grouped: dict[str, list[SourceUrlCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.run_id or "", []).append(candidate)

    items = [
        ProductSourceUrlCandidateRunGroup(
            run_id=run_id,
            run=runs_by_id.get(run_id),
            counts=_candidate_status_counts(group_candidates),
            candidates=sorted(group_candidates, key=_candidate_sort_key),
            latest_candidate_created_at=_latest_candidate_created_at(group_candidates),
        )
        for run_id, group_candidates in grouped.items()
    ]
    items.sort(key=_run_group_sort_key, reverse=True)

    return ProductSourceUrlCandidateHistory(
        catalog_product_id=catalog_product_id,
        product_exists=True,
        items=items,
        total_candidates=len(candidates),
        warnings=[],
    )


def minimal_discovery_run_payload(run_id: str) -> dict[str, Any]:
    return {"run_id": run_id, "status": "unknown"}


def _contains_pattern(value: str) -> str:
    return f"%{_escape_like_value(value)}%"


def _escape_like_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _optional_decimal(value: str | None, field_name: str) -> Decimal | None:
    text = _optional_text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} must be a number.") from None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _candidate_status_counts(candidates: list[SourceUrlCandidate]) -> dict[str, int]:
    counts = {status: 0 for status in SOURCE_URL_CANDIDATE_COUNT_STATUSES}
    for candidate in candidates:
        status = candidate.status or ""
        if status in counts:
            counts[status] += 1
    return counts


def _candidate_sort_key(candidate: SourceUrlCandidate) -> tuple[int, float, int]:
    status_rank = SOURCE_URL_CANDIDATE_STATUS_ORDER.get(candidate.status or "", len(SOURCE_URL_CANDIDATE_STATUS_ORDER))
    return (status_rank, _datetime_sort_value(candidate.created_at), int(candidate.id or 0))


def _latest_candidate_created_at(candidates: list[SourceUrlCandidate]) -> datetime | None:
    values = [candidate.created_at for candidate in candidates if candidate.created_at is not None]
    return max(values) if values else None


def _run_group_sort_key(group: ProductSourceUrlCandidateRunGroup) -> tuple[float, float, str]:
    run_created_at = group.run.created_at if group.run is not None else None
    sort_created_at = run_created_at or group.latest_candidate_created_at
    return (
        _datetime_sort_value(sort_created_at),
        _datetime_sort_value(group.latest_candidate_created_at),
        group.run_id,
    )


def _datetime_sort_value(value: datetime | None) -> float:
    return value.timestamp() if value is not None else 0.0
