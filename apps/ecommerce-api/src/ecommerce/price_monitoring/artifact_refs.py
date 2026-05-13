"""Response payload helpers for persisted Price Monitoring runs and artifacts."""

from __future__ import annotations

from pathlib import Path

from ecommerce.db.diagnostics import collect_run_persistence_status
from ecommerce.price_monitoring.artifacts import build_run_artifact_evidence
from ecommerce.price_monitoring.fetch_execution import execution_response, load_latest_fetch_execution


def fetch_result_persistence_payload(run_id: str) -> dict[str, object]:
    status = collect_run_persistence_status(run_id)
    persistence_status = str(status.get("persistence_status") or "unknown")
    warnings: list[str] = []
    if persistence_status == "not_configured":
        warnings.append("Database persistence is disabled because ECOMMERCE_DATABASE_URL is not configured.")
    elif persistence_status == "missing":
        warnings.append("Fetch result exists on disk, but matching database rows were not found.")
    elif persistence_status == "unknown":
        warning = str(status.get("warning") or "Database persistence status could not be determined.")
        warnings.append(warning)
    elif persistence_status == "error":
        error = str(status.get("error") or "Database persistence status check failed.")
        warnings.append(f"Database persistence status check failed: {error}")
    return {"persistence_status": persistence_status, "warnings": warnings}


def run_db_payload(run_id: str) -> dict[str, object]:
    status = collect_run_persistence_status(run_id)
    payload: dict[str, object] = {
        "configured": bool(status.get("configured", False)),
        "reachable": bool(status.get("reachable", False)),
        "persistence_status": str(status.get("persistence_status") or "unknown"),
    }
    if not payload["configured"]:
        return payload
    if not payload["reachable"]:
        if status.get("error"):
            payload["error"] = str(status["error"])
        return payload
    payload.update(
        {
            "monitoring_run_exists": bool(status.get("monitoring_run_exists", False)),
            "observation_count": int(status.get("observation_count", 0)),
            "matched_observation_count": int(status.get("matched_observation_count", 0)),
            "unmatched_observation_count": int(status.get("unmatched_observation_count", 0)),
            "alert_event_count": int(status.get("alert_event_count", 0)),
        }
    )
    if status.get("warning"):
        payload["warning"] = str(status["warning"])
    return payload


def db_run_to_route_response(item: dict[str, object]) -> dict[str, object]:
    run_id = str(item.get("run_id") or "")
    evidence = build_run_artifact_evidence(item)
    return {
        "run_id": run_id,
        "status": str(item.get("status") or ""),
        "source": str(item.get("source") or ""),
        "source_name": str(item.get("source") or ""),
        "source_filter": str(item.get("source") or ""),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "started_at": str(item.get("started_at") or ""),
        "completed_at": str(item.get("completed_at") or ""),
        "output_dir": str(item.get("output_dir") or ""),
        "input_csv_path": str(item.get("input_csv_path") or ""),
        "selection_summary_path": str(item.get("selection_summary_path") or ""),
        "fetch_result_path": str(item.get("fetch_result_path") or ""),
        "enriched_csv_path": str(item.get("enriched_csv_path") or ""),
        "fetch_summary_path": str(item.get("fetch_summary_path") or ""),
        "selected_count": item.get("selected_count"),
        "skipped_count": item.get("skipped_count"),
        "skipped_by_reason": {},
        "selected_models": [],
        "skipped_models": [],
        "latest_fetch": latest_fetch_payload(item),
        "artifacts": evidence.artifacts,
        "artifact_warnings": evidence.warnings,
    }


def latest_fetch_payload(item: dict[str, object]) -> dict[str, object] | None:
    output_dir = str(item.get("output_dir") or "").strip()
    if output_dir:
        try:
            execution = load_latest_fetch_execution(Path(output_dir))
        except Exception:
            execution = None
        if execution is not None:
            return execution_response(execution)
    return db_latest_fetch_payload(item)


def db_latest_fetch_payload(item: dict[str, object]) -> dict[str, object] | None:
    has_fetch_state = any(
        str(item.get(field) or "").strip()
        for field in ("fetch_result_path", "enriched_csv_path", "fetch_summary_path", "started_at", "completed_at", "error_message")
    )
    status = str(item.get("status") or "")
    if not has_fetch_state and not status.startswith("fetch_"):
        return None
    return {
        "execution_id": "",
        "execution_type": "fetch",
        "status": normalize_db_fetch_status(status),
        "source": str(item.get("source") or ""),
        "queued_at": "",
        "started_at": str(item.get("started_at") or ""),
        "completed_at": str(item.get("completed_at") or ""),
        "cancelled_at": "",
        "enriched_csv_path": str(item.get("enriched_csv_path") or ""),
        "fetch_summary_path": str(item.get("fetch_summary_path") or ""),
        "fetch_result_path": str(item.get("fetch_result_path") or ""),
        "error": str(item.get("error_message") or ""),
        "fetch_input_mode": "source_urls",
        "source_url_capture_used": True,
        "source_url_capture_status": "not_run",
        "source_url_capture_selected_count": 0,
        "source_url_capture_succeeded_count": 0,
        "source_url_capture_failed_count": 0,
        "source_url_capture_result_path": "",
        "source_url_capture_warnings": [],
        "source_url_capture_run_id": "",
        "observation_batch_id": "",
    }


def normalize_db_fetch_status(status: str) -> str:
    if status == "fetch_completed":
        return "succeeded"
    if status == "fetch_failed":
        return "failed"
    return status
