"""DB persistence for Source URL Agent Mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import (
    SourceUrl,
    SourceUrlCandidate as SourceUrlCandidateRow,
    SourceUrlDiscoveryRun,
)
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url
from ecommerce.source_urls import SourceUrlValidationError, normalize_source_url
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate


@dataclass(frozen=True)
class SourceUrlWriteResult:
    candidate_index: int
    action: str
    source_url_id: int | None = None
    reason: str = ""


def persist_discovery_run(
    session: Session,
    *,
    summary: dict[str, Any],
    filters_json: dict[str, Any] | None,
    started_at: datetime,
    completed_at: datetime,
) -> SourceUrlDiscoveryRun:
    timestamp = _now()
    run_id = str(summary.get("run_id") or "")
    row = session.execute(
        select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id == run_id)
    ).scalar_one_or_none()
    if row is None:
        row = SourceUrlDiscoveryRun(
            run_id=run_id, created_at=timestamp, updated_at=timestamp
        )
        session.add(row)
    row.source_name = str(summary.get("source") or "")
    row.mode = str(summary.get("mode") or "")
    row.status = "completed"
    row.input_path = str(summary.get("input_path") or "") or None
    row.filters_json = filters_json or {}
    row.selected_count = int(summary.get("selected_count") or 0)
    row.candidate_count = int(summary.get("candidate_count") or 0)
    row.matched_count = int(summary.get("matched_count") or 0)
    row.needs_review_count = int(summary.get("needs_review_count") or 0)
    row.not_found_count = int(summary.get("not_found_count") or 0)
    row.error_count = int(summary.get("error_count") or 0)
    row.started_at = _timestamp(started_at)
    row.completed_at = _timestamp(completed_at)
    row.updated_at = timestamp
    session.flush()
    return row


def persist_candidate_rows(
    session: Session, candidates: list[SourceUrlAgentCandidate]
) -> list[SourceUrlCandidateRow]:
    rows: list[SourceUrlCandidateRow] = []
    timestamp = _now()
    for candidate in candidates:
        payload = candidate.to_db_dict()
        row = SourceUrlCandidateRow(
            **payload, created_at=timestamp, updated_at=timestamp
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def apply_high_confidence_source_urls(
    session: Session,
    candidates: list[SourceUrlAgentCandidate],
    *,
    apply: bool,
) -> list[SourceUrlWriteResult]:
    results: list[SourceUrlWriteResult] = []
    for index, candidate in enumerate(candidates):
        if (
            candidate.match_status != "matched"
            or candidate.match_method != "exact_mpn_and_brand"
            or candidate.confidence_score <= 0.90
        ):
            continue
        disabled_provider = _auto_apply_disabled_provider(candidate)
        if disabled_provider:
            results.append(
                SourceUrlWriteResult(
                    index,
                    "skipped",
                    reason=f"provider_auto_apply_disabled:{disabled_provider}",
                )
            )
            continue
        result = write_candidate_source_url(
            session,
            candidate,
            trust_level="high_confidence",
            apply=apply,
            candidate_index=index,
        )
        results.append(result)
    return results


def write_candidate_source_url(
    session: Session,
    candidate: SourceUrlAgentCandidate,
    *,
    trust_level: str,
    apply: bool,
    candidate_index: int = -1,
) -> SourceUrlWriteResult:
    catalog_product_id = candidate.product.catalog_product_id
    if catalog_product_id is None:
        return SourceUrlWriteResult(
            candidate_index, "skipped", reason="catalog_product_id_missing"
        )
    url = candidate.canonical_url or candidate.candidate_url
    if not url:
        return SourceUrlWriteResult(
            candidate_index, "skipped", reason="candidate_url_missing"
        )
    try:
        normalized = normalize_source_url(url)
    except SourceUrlValidationError as exc:
        return SourceUrlWriteResult(
            candidate_index, "skipped", reason=f"invalid_url:{exc}"
        )
    manual = _manual_source_url_for_source(
        session, catalog_product_id, candidate.source_name
    )
    if (
        manual is not None
        and manual.url_normalized != normalized
        and trust_level != "manual"
    ):
        return SourceUrlWriteResult(
            candidate_index,
            "skipped",
            source_url_id=manual.id,
            reason="manual_source_url_exists",
        )

    try:
        upsert = create_or_update_imported_source_url(
            session,
            catalog_product_id=catalog_product_id,
            url=url,
            source_name=candidate.source_name,
            url_type="discovered",
            trust_level=trust_level,
            status="active",
            last_seen_at=candidate.checked_at,
            last_success_at=candidate.checked_at,
            notes=_notes(candidate, trust_level),
            apply=apply,
        )
    except LookupError as exc:
        return SourceUrlWriteResult(candidate_index, "skipped", reason=str(exc))
    except ValueError as exc:
        return SourceUrlWriteResult(candidate_index, "skipped", reason=str(exc))
    return SourceUrlWriteResult(
        candidate_index, upsert.action, source_url_id=upsert.source_url_id, reason=""
    )


def update_candidate_review_status(
    session: Session,
    *,
    run_id: str,
    catalog_product_id: int | None,
    source_name: str,
    candidate_url: str,
    status: str,
    reviewed_by: str | None,
    reviewed_at: datetime | None,
    notes: str | None,
) -> int:
    statement = select(SourceUrlCandidateRow).where(
        SourceUrlCandidateRow.run_id == run_id,
        SourceUrlCandidateRow.source_name == source_name,
        SourceUrlCandidateRow.candidate_url == candidate_url,
    )
    if catalog_product_id is not None:
        statement = statement.where(
            SourceUrlCandidateRow.catalog_product_id == catalog_product_id
        )
    rows = list(session.execute(statement).scalars().all())
    timestamp = _now()
    for row in rows:
        row.status = status
        row.reviewed_by = reviewed_by
        row.reviewed_at = _timestamp(reviewed_at)
        if notes:
            row.notes = notes
        row.updated_at = timestamp
    session.flush()
    return len(rows)


def _manual_source_url_for_source(
    session: Session, catalog_product_id: int, source_name: str
) -> SourceUrl | None:
    return session.execute(
        select(SourceUrl)
        .where(
            SourceUrl.catalog_product_id == catalog_product_id,
            SourceUrl.source_name == source_name,
            SourceUrl.url_type == "manual",
            SourceUrl.status.in_(("active", "needs_review")),
        )
        .order_by(SourceUrl.updated_at.desc(), SourceUrl.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _notes(candidate: SourceUrlAgentCandidate, trust_level: str) -> str:
    suffix = f"Source URL Agent {candidate.run_id}; {candidate.match_method}; confidence={candidate.confidence_score:.4f}"
    if trust_level == "manual":
        suffix = f"Manual review accepted; {suffix}"
    return suffix


def _auto_apply_disabled_provider(candidate: SourceUrlAgentCandidate) -> str:
    provenance = candidate.evidence_json.get("provider_provenance")
    if not isinstance(provenance, dict):
        return ""
    if provenance.get("allow_high_confidence_auto_apply") is not False:
        return ""
    return str(provenance.get("provider_name") or "unknown").strip() or "unknown"


def _timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
