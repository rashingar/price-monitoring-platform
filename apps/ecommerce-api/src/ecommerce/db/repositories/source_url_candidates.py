"""Read queries for Source URL Agent candidate history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrlCandidate, SourceUrlDiscoveryRun

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
