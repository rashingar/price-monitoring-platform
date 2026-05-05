"""Candidate result models for Source URL Agent Mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ecommerce.db.repositories import json_safe_value
from ecommerce.utils.decimals import format_decimal_two_places
from ecommerce.source_url_agent.evidence import PageEvidence
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.scoring import CandidateScore
from ecommerce.source_url_agent.sources import SourceDefinition


MIN_CANDIDATE_CONFIDENCE_TO_KEEP = 0.80


@dataclass(frozen=True)
class SourceUrlAgentCandidate:
    run_id: str
    product: AgentProduct
    source: SourceDefinition
    expected_listing: str
    candidate_url: str
    canonical_url: str
    candidate_title: str
    candidate_price: Decimal | None
    match_status: str
    confidence_score: float
    match_method: str
    evidence_json: dict[str, Any]
    competing_candidates_count: int
    searched_queries: list[str]
    status: str
    notes: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0))
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @property
    def source_name(self) -> str:
        return self.source.source_name

    @property
    def source_domain(self) -> str:
        return self.source.source_domain

    @property
    def source_type(self) -> str:
        return self.source.source_type

    def to_artifact_row(self, *, include_review_columns: bool = False) -> dict[str, Any]:
        evidence = self.evidence_json
        row: dict[str, Any] = {
            "model": self.product.model,
            "catalog_product_id": self.product.catalog_product_id or "",
            "catalog_name": self.product.name,
            "mpn": self.product.mpn,
            "manufacturer": self.product.manufacturer,
            "category": self.product.category,
            "own_price": format_decimal_two_places(self.product.price) if self.product.price is not None else "",
            "source_name": self.source_name,
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "expected_listing": self.expected_listing,
            "candidate_url": self.candidate_url,
            "canonical_url": self.canonical_url,
            "candidate_title": self.candidate_title,
            "candidate_price": format_decimal_two_places(self.candidate_price) if self.candidate_price is not None else "",
            "match_status": self.match_status,
            "confidence_score": f"{self.confidence_score:.4f}",
            "match_method": self.match_method,
            "evidence_mpn": _evidence_text(evidence.get("mpn"), "found"),
            "evidence_brand": _evidence_text(evidence.get("brand"), "found"),
            "evidence_model": _evidence_text(evidence.get("model"), "found"),
            "evidence_category": _evidence_text(evidence.get("category"), "compatible"),
            "evidence_price": _price_evidence_text(evidence.get("price")),
            "competing_candidates_count": self.competing_candidates_count,
            "searched_queries": " | ".join(self.searched_queries),
            "notes": self.notes,
            "checked_at": self.checked_at.isoformat(),
        }
        if include_review_columns:
            row.update(
                {
                    "review_decision": "",
                    "reviewed_url": "",
                    "review_notes": "",
                    "reviewed_by": "",
                    "reviewed_at": "",
                }
            )
        return row

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "catalog_product_id": self.product.catalog_product_id,
            "catalog_source": self.product.catalog_source,
            "model": self.product.model,
            "mpn": self.product.mpn,
            "manufacturer": self.product.manufacturer,
            "product_name": self.product.name,
            "category": self.product.category,
            "own_price": self.product.price,
            "source_name": self.source_name,
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "expected_listing": self.expected_listing,
            "candidate_url": self.candidate_url,
            "canonical_url": self.canonical_url,
            "candidate_title": self.candidate_title,
            "candidate_price": self.candidate_price,
            "match_status": self.match_status,
            "confidence_score": Decimal(str(self.confidence_score)),
            "match_method": self.match_method,
            "evidence_json": json_safe_value(self.evidence_json),
            "competing_candidates_count": self.competing_candidates_count,
            "searched_queries_json": list(self.searched_queries),
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "notes": self.notes,
        }


def keep_candidate(candidate: SourceUrlAgentCandidate) -> bool:
    return candidate.confidence_score >= MIN_CANDIDATE_CONFIDENCE_TO_KEEP


def candidate_from_evidence(
    *,
    run_id: str,
    product: AgentProduct,
    source: SourceDefinition,
    evidence: PageEvidence,
    score: CandidateScore,
    expected_listing: str,
    competing_candidates_count: int,
    searched_queries: list[str],
    status: str = "pending",
) -> SourceUrlAgentCandidate:
    evidence_json = evidence.to_json()
    evidence_json["mpn"]["expected"] = product.mpn
    evidence_json["model"]["expected"] = product.model
    evidence_json["brand"]["expected"] = product.manufacturer
    evidence_json["category"]["expected"] = product.category
    notes = score.notes
    if evidence.error_code and not notes:
        notes = evidence.error_message
    return SourceUrlAgentCandidate(
        run_id=run_id,
        product=product,
        source=source,
        expected_listing=expected_listing,
        candidate_url=evidence.requested_url,
        canonical_url=evidence.canonical_url,
        candidate_title=evidence.title,
        candidate_price=evidence.candidate_price,
        match_status=score.match_status,
        confidence_score=score.confidence_score,
        match_method=score.match_method,
        evidence_json=evidence_json,
        competing_candidates_count=competing_candidates_count,
        searched_queries=searched_queries,
        status=status,
        notes=notes,
    )


def synthetic_candidate(
    *,
    run_id: str,
    product: AgentProduct,
    source: SourceDefinition,
    expected_listing: str,
    match_status: str,
    status: str,
    match_method: str,
    searched_queries: list[str],
    notes: str,
    candidate_url: str = "",
    canonical_url: str = "",
) -> SourceUrlAgentCandidate:
    return SourceUrlAgentCandidate(
        run_id=run_id,
        product=product,
        source=source,
        expected_listing=expected_listing,
        candidate_url=candidate_url,
        canonical_url=canonical_url,
        candidate_title="",
        candidate_price=None,
        match_status=match_status,
        confidence_score=0.0,
        match_method=match_method,
        evidence_json={
            "mpn": {"expected": product.mpn, "found": False, "fragment": ""},
            "model": {"expected": product.model, "found": False, "fragment": ""},
            "brand": {"expected": product.manufacturer, "found": False, "fragment": ""},
            "category": {"expected": product.category, "compatible": False, "fragment": ""},
            "price": {"compatible": None},
            "title_similarity": 0.0,
            "title_only": False,
            "error_code": match_method if match_status == "error" else "",
            "error_message": notes if match_status == "error" else "",
        },
        competing_candidates_count=0,
        searched_queries=searched_queries,
        status=status,
        notes=notes,
    )


def _evidence_text(value: object, flag_key: str) -> str:
    if not isinstance(value, dict):
        return "missing"
    flag = value.get(flag_key)
    fragment = str(value.get("fragment") or "").strip()
    if flag:
        return f"found:{fragment}" if fragment else "found"
    return "missing"


def _price_evidence_text(value: object) -> str:
    if not isinstance(value, dict):
        return "unknown"
    compatible = value.get("compatible")
    if compatible is True:
        return "compatible"
    if compatible is False:
        return "different"
    return "unknown"
