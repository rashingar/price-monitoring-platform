"""Product-scoped Source URL Agent candidate history payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ecommerce.db.repositories.source_url_candidates import (
    ProductSourceUrlCandidateHistory,
    get_product_source_url_candidate_history,
    minimal_discovery_run_payload,
)
from ecommerce.source_url_agent.payloads import candidate_to_dict, discovery_run_to_dict


@dataclass(frozen=True)
class ProductSourceUrlCandidateHistoryPayload:
    catalog_product_id: int
    product_exists: bool
    items: list[dict[str, Any]]
    total_candidates: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_product_id": self.catalog_product_id,
            "items": self.items,
            "total_candidates": self.total_candidates,
            "warnings": self.warnings,
        }


def product_source_url_candidate_history_payload(
    session: Session,
    catalog_product_id: int,
) -> ProductSourceUrlCandidateHistoryPayload:
    history = get_product_source_url_candidate_history(session, catalog_product_id)
    return _history_to_payload(session, history)


def _history_to_payload(
    session: Session,
    history: ProductSourceUrlCandidateHistory,
) -> ProductSourceUrlCandidateHistoryPayload:
    items = [
        {
            "run_id": group.run_id,
            "run": discovery_run_to_dict(group.run, session=session)
            if group.run is not None
            else minimal_discovery_run_payload(group.run_id),
            "counts": group.counts,
            "candidates": [candidate_to_dict(candidate) for candidate in group.candidates],
        }
        for group in history.items
    ]
    return ProductSourceUrlCandidateHistoryPayload(
        catalog_product_id=history.catalog_product_id,
        product_exists=history.product_exists,
        items=items,
        total_candidates=history.total_candidates,
        warnings=history.warnings,
    )
