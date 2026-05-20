"""Human review CSV import/apply for Source URL Agent Mode."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ecommerce.source_urls import SourceUrlValidationError, normalize_source_url
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.persistence import (
    update_candidate_review_status,
    write_candidate_source_url,
)
from ecommerce.source_url_agent.sources import SourceDefinition, load_source_registry

VALID_REVIEW_DECISIONS = {"accept", "reject", "replace_url"}


@dataclass
class ReviewApplyResult:
    apply: bool
    review_file: str
    counters: Counter[str] = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply": self.apply,
            "review_file": self.review_file,
            "counters": {
                key: int(value) for key, value in sorted(self.counters.items())
            },
            "warnings": list(self.warnings),
            "items": list(self.items),
        }


def apply_review_csv(
    session: Session | None,
    *,
    review_file: Path,
    apply: bool = False,
) -> ReviewApplyResult:
    if not review_file.exists() or not review_file.is_file():
        raise FileNotFoundError(f"Review CSV not found: {review_file}")
    result = ReviewApplyResult(apply=apply, review_file=str(review_file))
    registry = load_source_registry()
    rows = _read_rows(review_file)
    run_id = review_file.parent.name
    for row in rows:
        decision = str(row.get("review_decision") or "").strip().lower()
        if not decision:
            result.counters["pending_count"] += 1
            continue
        if decision not in VALID_REVIEW_DECISIONS:
            result.counters["invalid_count"] += 1
            result.warnings.append(
                f"Invalid review_decision for model {row.get('model')}: {decision}"
            )
            continue
        if decision == "reject":
            _record_non_write_decision(
                session, row, decision, result, run_id=run_id, apply=apply
            )
            continue
        _apply_accept_or_replace(
            session, row, decision, registry, result, run_id=run_id, apply=apply
        )
    return result


def _apply_accept_or_replace(
    session: Session | None,
    row: dict[str, str],
    decision: str,
    registry,
    result: ReviewApplyResult,
    *,
    run_id: str,
    apply: bool,
) -> None:
    candidate_url = str(row.get("candidate_url") or "").strip()
    reviewed_url = str(row.get("reviewed_url") or "").strip()
    url = reviewed_url if decision == "replace_url" else (reviewed_url or candidate_url)
    if not url:
        result.counters["invalid_count"] += 1
        result.warnings.append(
            f"Missing URL for review decision {decision} on model {row.get('model')}."
        )
        return
    try:
        normalized = normalize_source_url(url)
    except SourceUrlValidationError as exc:
        result.counters["invalid_url_count"] += 1
        result.warnings.append(
            f"Invalid reviewed URL for model {row.get('model')}: {exc}"
        )
        return
    if session is None and apply:
        result.counters["skipped_count"] += 1
        result.warnings.append(
            "Database is not configured; review apply is artifact-only."
        )
        return

    source_name = str(row.get("source_name") or "").strip().lower()
    try:
        source = registry.get(source_name)
    except ValueError:
        result.counters["invalid_count"] += 1
        result.warnings.append(f"Unknown source in review file: {source_name}")
        return
    candidate = _row_to_candidate(row, source, reviewed_url=url, run_id=run_id)
    write_result = None
    if session is not None:
        write_result = write_candidate_source_url(
            session, candidate, trust_level="manual", apply=apply
        )
        _update_review_candidate(
            session, row, "accepted", result, run_id=run_id, apply=apply
        )
    result.counters["accepted_count" if decision == "accept" else "replaced_count"] += 1
    result.items.append(
        {
            "model": row.get("model"),
            "source_name": source_name,
            "decision": decision,
            "url": normalized,
            "action": (
                write_result.action
                if write_result is not None
                else ("would_write" if apply else "dry_run")
            ),
            "reason": write_result.reason if write_result is not None else "",
        }
    )


def _record_non_write_decision(
    session: Session | None,
    row: dict[str, str],
    decision: str,
    result: ReviewApplyResult,
    *,
    run_id: str,
    apply: bool,
) -> None:
    status = {
        "reject": "rejected",
    }[decision]
    if session is not None:
        _update_review_candidate(
            session, row, status, result, run_id=run_id, apply=apply
        )
    result.counters[f"{status}_count"] += 1
    result.items.append(
        {
            "model": row.get("model"),
            "source_name": row.get("source_name"),
            "decision": decision,
            "action": (
                "updated_candidate" if apply and session is not None else "dry_run"
            ),
        }
    )


def _update_review_candidate(
    session: Session,
    row: dict[str, str],
    status: str,
    result: ReviewApplyResult,
    *,
    run_id: str,
    apply: bool,
) -> None:
    if not apply:
        return
    reviewed_at = _reviewed_at(row.get("reviewed_at"))
    count = update_candidate_review_status(
        session,
        run_id=run_id,
        catalog_product_id=_int_or_none(row.get("catalog_product_id")),
        source_name=str(row.get("source_name") or "").strip(),
        candidate_url=str(row.get("candidate_url") or "").strip(),
        status=status,
        reviewed_by=str(row.get("reviewed_by") or "").strip() or None,
        reviewed_at=reviewed_at,
        notes=str(row.get("review_notes") or "").strip() or None,
    )
    if count == 0:
        result.warnings.append(
            f"No stored candidate row matched review item model={row.get('model')} source={row.get('source_name')}."
        )


def _row_to_candidate(
    row: dict[str, str], source: SourceDefinition, *, reviewed_url: str, run_id: str
) -> SourceUrlAgentCandidate:
    product = AgentProduct(
        catalog_product_id=_int_or_none(row.get("catalog_product_id")),
        catalog_source="sourceCata",
        model=str(row.get("model") or "").strip(),
        mpn=str(row.get("mpn") or "").strip(),
        name=str(row.get("catalog_name") or "").strip(),
        category=str(row.get("category") or "").strip(),
        manufacturer=str(row.get("manufacturer") or "").strip(),
        price=None,
        quantity=None,
        status=1,
        bestprice_status=None,
        skroutz_status=None,
    )
    return SourceUrlAgentCandidate(
        run_id=run_id,
        product=product,
        source=source,
        expected_listing=str(row.get("expected_listing") or "").strip(),
        candidate_url=reviewed_url,
        canonical_url=reviewed_url,
        candidate_title=str(row.get("candidate_title") or "").strip(),
        candidate_price=None,
        match_status="matched",
        confidence_score=1.0,
        match_method="manual_review",
        evidence_json={},
        competing_candidates_count=_int_or_none(row.get("competing_candidates_count"))
        or 0,
        searched_queries=[],
        status="accepted",
        notes=str(row.get("review_notes") or "").strip(),
        reviewed_by=str(row.get("reviewed_by") or "").strip() or None,
        reviewed_at=_reviewed_at(row.get("reviewed_at")),
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _reviewed_at(value: object) -> datetime:
    text = str(value or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return (
                parsed
                if parsed.tzinfo is not None
                else parsed.replace(tzinfo=timezone.utc)
            )
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(microsecond=0)


def _int_or_none(value: object) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except ValueError:
        return None
