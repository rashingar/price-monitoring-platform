"""Payload serializers for Source URL Agent API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ecommerce.artifacts import artifact_link_payload
from ecommerce.db.models.source_urls import SourceUrlCandidate
from ecommerce.db.repositories.common import json_safe_value
from ecommerce.db.repositories.source_urls import source_url_to_dict
from ecommerce.source_url_agent.options import SourceUrlAgentResult
from ecommerce.source_url_agent.payloads import candidate_to_dict, discovery_run_to_dict
from ecommerce.source_url_agent.review_service import SourceUrlCandidatePromotionResult
from ecommerce.source_url_agent.sources import SourceDefinition


def source_definition_to_dict(source: SourceDefinition) -> dict[str, Any]:
    return {
        "source_name": source.source_name,
        "source_domain": source.source_domain,
        "source_type": source.source_type,
        "enabled": source.enabled,
        "discovery_enabled": source.enabled,
        "expected_listing_field": source.expected_listing_field,
        "rate_limit_seconds": source.rate_limit_seconds,
        "max_candidates_per_product": source.max_candidates_per_product,
        "max_searches_per_product": source.max_searches_per_product,
        "notes": source.notes,
    }


def source_url_agent_result_payload(result: SourceUrlAgentResult) -> dict[str, Any]:
    summary = json_safe_value(result.summary)
    return {
        "run_id": result.run_id,
        "mode": summary.get("mode"),
        "source": summary.get("source"),
        "dry_run": bool(summary.get("dry_run", True)),
        "apply_high_confidence": bool(summary.get("apply_high_confidence", False)),
        "summary": summary,
        "warnings": list(result.warnings),
        "artifacts": artifact_refs_from_paths(result.artifacts.to_dict()),
    }


def candidate_review_panel_payload(row: SourceUrlCandidate) -> dict[str, Any]:
    return {
        "mode": "inline_row",
        "open_on": "row_single_click",
        "primary_fields": {
            "id": row.id,
            "status": row.status,
            "model": row.model,
            "mpn": row.mpn,
            "manufacturer": row.manufacturer,
            "product_name": row.product_name,
            "candidate_url": row.candidate_url,
            "canonical_url": row.canonical_url,
            "confidence_score": json_safe_value(row.confidence_score),
        },
        "review_actions": [
            {
                "decision": "accept",
                "label": "Accept",
                "requires_reviewed_url": False,
                "promotes_source_url": True,
            },
            {
                "decision": "replace_url",
                "label": "Replace URL",
                "requires_reviewed_url": True,
                "promotes_source_url": True,
            },
            {
                "decision": "reject",
                "label": "Reject",
                "requires_reviewed_url": False,
                "promotes_source_url": False,
            },
        ],
        "review_endpoint": f"/api/source-url-agent/candidates/{row.id}/review",
    }


def source_url_promotion_to_dict(
    promotion: SourceUrlCandidatePromotionResult | None,
) -> dict[str, Any] | None:
    if promotion is None:
        return None
    return {
        "action": promotion.action,
        "source_url_id": promotion.source_url_id,
        "changed_fields": list(promotion.changed_fields),
        "item": (
            source_url_to_dict(promotion.row) if promotion.row is not None else None
        ),
    }


def artifact_refs_from_paths(paths: dict[str, str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key, value in paths.items():
        if key == "run_dir" or not value:
            continue
        payload = artifact_link_payload(Path(value))
        payload["artifact_key"] = key
        refs.append(payload)
    return refs
