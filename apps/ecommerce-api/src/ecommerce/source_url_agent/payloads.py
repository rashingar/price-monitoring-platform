"""Shared Source URL Agent payload helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import SourceUrlCandidate, SourceUrlDiscoveryRun
from ecommerce.db.repositories.common import json_safe_value
from ecommerce.db.repositories.source_urls import (
    list_source_url_discovery_tasks,
    source_url_discovery_task_counts,
)


def discovery_run_to_dict(
    row: SourceUrlDiscoveryRun,
    *,
    session: Session | None = None,
    include_tasks: bool = False,
) -> dict[str, Any]:
    task_counts = source_url_discovery_task_counts(session, row.run_id) if session is not None else {}
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
        payload["tasks"] = [
            {
                "id": task.id,
                "run_id": task.run_id,
                "catalog_product_id": task.catalog_product_id,
                "model": task.model,
                "source_name": task.source_name,
                "status": task.status,
                "match_status": task.match_status,
                "candidate_count": task.candidate_count,
                "error_message": task.error_message,
                "started_at": json_safe_value(task.started_at),
                "completed_at": json_safe_value(task.completed_at),
                "created_at": json_safe_value(task.created_at),
                "updated_at": json_safe_value(task.updated_at),
            }
            for task in list_source_url_discovery_tasks(session, row.run_id)
        ]
    return payload


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
