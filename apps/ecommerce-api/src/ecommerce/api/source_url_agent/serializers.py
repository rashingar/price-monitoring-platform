"""Payload serializers for Source URL Agent API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ecommerce.artifacts import artifact_link_payload
from ecommerce.db.models.source_urls import SourceUrlCandidate, SourceUrlDiscoveryRun, SourceUrlDiscoveryTask
from ecommerce.db.repositories.common import json_safe_value
from ecommerce.source_url_agent.agent import SourceUrlAgentResult
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


def discovery_run_to_dict(
    row: SourceUrlDiscoveryRun,
    *,
    session: Session | None = None,
    include_tasks: bool = False,
) -> dict[str, Any]:
    task_counts = discovery_task_counts(session, row.run_id) if session is not None else {}
    filters = row.filters_json if isinstance(row.filters_json, dict) else {}
    payload = {
        "id": row.id,
        "run_id": row.run_id,
        "source": row.source_name,
        "source_name": row.source_name,
        "mode": row.mode,
        "status": row.status,
        "input_path": row.input_path,
        "filters_json": json_safe_value(row.filters_json),
        "dry_run": bool(filters.get("dry_run", True)),
        "apply_high_confidence": bool(filters.get("apply_high_confidence", False)),
        "limit": filters.get("limit"),
        "rate_limit_seconds": filters.get("rate_limit_seconds"),
        "selected_count": row.selected_count,
        "candidate_count": row.candidate_count,
        "matched_count": row.matched_count,
        "needs_review_count": row.needs_review_count,
        "not_found_count": row.not_found_count,
        "error_count": row.error_count,
        "started_at": json_safe_value(row.started_at),
        "completed_at": json_safe_value(row.completed_at),
        "created_at": json_safe_value(row.created_at),
        "updated_at": json_safe_value(row.updated_at),
        "task_counts": task_counts,
        "task_total_count": sum(task_counts.values()) if task_counts else 0,
        "task_finished_count": sum(int(task_counts.get(status, 0)) for status in ("completed", "failed", "skipped")),
    }
    payload["summary"] = {
        "selected_count": row.selected_count,
        "candidate_count": row.candidate_count,
        "matched_count": row.matched_count,
        "needs_review_count": row.needs_review_count,
        "not_found_count": row.not_found_count,
        "error_count": row.error_count,
        "task_counts": task_counts,
        "task_total_count": payload["task_total_count"],
        "task_finished_count": payload["task_finished_count"],
    }
    if include_tasks and session is not None:
        payload["tasks"] = discovery_task_items(session, row.run_id)
    return payload


def discovery_task_counts(session: Session, run_id: str) -> dict[str, int]:
    rows = session.execute(
        select(SourceUrlDiscoveryTask.status, func.count(SourceUrlDiscoveryTask.id))
        .where(SourceUrlDiscoveryTask.run_id == run_id)
        .group_by(SourceUrlDiscoveryTask.status)
    ).all()
    return {str(status): int(count) for status, count in rows}


def discovery_task_items(session: Session, run_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        select(SourceUrlDiscoveryTask)
        .where(SourceUrlDiscoveryTask.run_id == run_id)
        .order_by(SourceUrlDiscoveryTask.id.asc())
    ).scalars().all()
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "catalog_product_id": row.catalog_product_id,
            "model": row.model,
            "source_name": row.source_name,
            "status": row.status,
            "match_status": row.match_status,
            "candidate_count": row.candidate_count,
            "error_message": row.error_message,
            "started_at": json_safe_value(row.started_at),
            "completed_at": json_safe_value(row.completed_at),
            "created_at": json_safe_value(row.created_at),
            "updated_at": json_safe_value(row.updated_at),
        }
        for row in rows
    ]


def candidate_to_dict(row: SourceUrlCandidate) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "catalog_product_id": row.catalog_product_id,
        "model": row.model,
        "mpn": row.mpn,
        "manufacturer": row.manufacturer,
        "product_name": row.product_name,
        "category": row.category,
        "own_price": json_safe_value(row.own_price),
        "source_name": row.source_name,
        "source_domain": row.source_domain,
        "source_type": row.source_type,
        "expected_listing": row.expected_listing,
        "candidate_url": row.candidate_url,
        "canonical_url": row.canonical_url,
        "candidate_title": row.candidate_title,
        "candidate_price": json_safe_value(row.candidate_price),
        "match_status": row.match_status,
        "confidence_score": json_safe_value(row.confidence_score),
        "match_method": row.match_method,
        "evidence_json": json_safe_value(row.evidence_json),
        "competing_candidates_count": row.competing_candidates_count,
        "searched_queries_json": json_safe_value(row.searched_queries_json),
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": json_safe_value(row.reviewed_at),
        "notes": row.notes,
        "created_at": json_safe_value(row.created_at),
        "updated_at": json_safe_value(row.updated_at),
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


def artifact_refs_from_paths(paths: dict[str, str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key, value in paths.items():
        if key == "run_dir" or not value:
            continue
        payload = artifact_link_payload(Path(value))
        payload["artifact_key"] = key
        refs.append(payload)
    return refs
