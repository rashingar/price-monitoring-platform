"""Service layer for Price Monitoring route workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ecommerce.db.repositories.price_monitoring import monitoring_run_to_dict
from ecommerce.price_monitoring.artifact_refs import (
    db_run_to_route_response,
    fetch_result_persistence_payload,
    run_db_payload,
)
from ecommerce.price_monitoring.fetch_execution import (
    cancel_fetch_execution,
    cancel_latest_active_fetch_execution,
    enqueue_fetch_execution,
    execution_response,
    list_fetch_executions,
    load_fetch_execution,
    load_latest_fetch_execution,
    read_execution_log_lines,
    read_latest_execution_log_lines,
    source_url_fetch_result_to_execution_payload,
)
from ecommerce.price_monitoring.fetch_run import load_price_monitoring_fetch_result
from ecommerce.price_monitoring.persistence import persist_run_creation_if_configured
from ecommerce.price_monitoring.runs import run_record_to_response, selection_preview_to_response
from ecommerce.price_monitoring.selection import PriceMonitoringSelectionRequest, PriceMonitoringSelectionResult, select_price_monitoring_products
from ecommerce.price_monitoring.source_url_coverage import compute_source_url_coverage, require_active_source_url_coverage


def preview_selection_response(selection_request: PriceMonitoringSelectionRequest, *, session_scope_fn: Callable) -> dict:
    result = select_price_monitoring_products_with_source_url_coverage(selection_request, session_scope_fn=session_scope_fn)
    return selection_preview_to_response(result)


def create_run_response(
    selection_request: PriceMonitoringSelectionRequest,
    *,
    session_scope_fn: Callable,
    create_price_monitoring_run_fn: Callable,
    persist_run_creation_fn: Callable = persist_run_creation_if_configured,
) -> dict:
    try:
        record = create_price_monitoring_run_fn(selection_request)
    except ValueError as exc:
        if str(exc) != "No eligible products selected.":
            raise
        preview = select_price_monitoring_products_with_source_url_coverage(selection_request, session_scope_fn=session_scope_fn)
        raise NoEligibleProductsSelectedError(str(exc), preview=preview, selection_request=selection_request) from exc
    persist_run_creation_fn(record, trigger_type="manual")
    return run_record_to_response(record)


def no_eligible_products_detail(
    message: str,
    *,
    preview: PriceMonitoringSelectionResult | None,
    selection_request: PriceMonitoringSelectionRequest,
) -> dict[str, object]:
    return {
        "message": message,
        "selected_count": preview.selected_count if preview is not None else 0,
        "skipped_count": preview.skipped_count if preview is not None else 0,
        "skipped_by_reason": preview.skipped_by_reason if preview is not None else {},
        "source_url_required": True,
        "source": preview.source if preview is not None else selection_request.source,
        "source_name": preview.source if preview is not None else selection_request.source,
        "source_filter": preview.source_filter if preview is not None else selection_request.source_filter,
        "source_url_coverage": (
            preview.source_url_coverage.to_dict()
            if preview is not None and preview.source_url_coverage is not None
            else None
        ),
        "operator_message": "Add active source URLs in Vendor Sources before creating a Price Monitoring run.",
    }


class NoEligibleProductsSelectedError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        preview: PriceMonitoringSelectionResult | None,
        selection_request: PriceMonitoringSelectionRequest,
    ) -> None:
        super().__init__(message)
        self.preview = preview
        self.selection_request = selection_request

    def detail(self) -> dict[str, object]:
        return no_eligible_products_detail(str(self), preview=self.preview, selection_request=self.selection_request)


def select_price_monitoring_products_with_source_url_coverage(
    selection_request: PriceMonitoringSelectionRequest,
    *,
    session_scope_fn: Callable,
) -> PriceMonitoringSelectionResult:
    result = select_price_monitoring_products(selection_request)
    with session_scope_fn() as session:
        coverage = compute_source_url_coverage(session, result.items, result.source)
    return require_active_source_url_coverage(result, coverage)


def list_runs_response(
    *,
    session_scope_fn: Callable,
    list_monitoring_runs_fn: Callable,
) -> dict:
    with session_scope_fn() as session:
        items = [db_run_to_route_response(item) for item in list_monitoring_runs_fn(session)]
    for item in items:
        item["db"] = run_db_payload(str(item.get("run_id") or ""))
    return {"items": items}


def get_run_response(
    run_id: str,
    *,
    session_scope_fn: Callable,
    get_monitoring_run_fn: Callable,
) -> dict:
    with session_scope_fn() as session:
        run = get_monitoring_run_fn(session, run_id)
        if run is None:
            raise FileNotFoundError(f"DB-backed price monitoring run not found: {run_id}")
        db_payload = monitoring_run_to_dict(run)
    payload = db_run_to_route_response(db_payload)
    payload["db"] = run_db_payload(run_id)
    return payload


def enqueue_fetch_response(
    run_dir: Path,
    *,
    source: str | None,
    catalog_url: str | None,
    enqueue_fetch_execution_fn: Callable = enqueue_fetch_execution,
) -> dict:
    execution = enqueue_fetch_execution_fn(run_dir, source=source, catalog_url=catalog_url)
    return execution_response(execution)


def latest_fetch_response(run_id: str, run_dir: Path) -> dict:
    execution = load_latest_fetch_execution(run_dir)
    if execution is not None:
        return execution_response(execution)
    result = load_price_monitoring_fetch_result(run_dir)
    payload = source_url_fetch_result_to_execution_payload(result)
    persistence = fetch_result_persistence_payload(run_id)
    payload["persistence_status"] = str(persistence["persistence_status"])
    payload["persistence_warnings"] = persistence["warnings"]
    return payload


def latest_fetch_logs_response(run_id: str, run_dir: Path) -> dict:
    execution = load_latest_fetch_execution(run_dir)
    if execution is None:
        raise FileNotFoundError("No fetch execution exists for this run.")
    lines = read_latest_execution_log_lines(run_dir)
    return {"run_id": run_id, "execution_id": execution.execution_id, "lines": lines}


def cancel_latest_fetch_response(run_dir: Path, *, reason: str | None) -> dict:
    return execution_response(cancel_latest_active_fetch_execution(run_dir, reason=reason))


def list_fetch_executions_response(run_id: str, run_dir: Path) -> dict:
    executions = [execution_response(execution) for execution in list_fetch_executions(run_dir)]
    return {"run_id": run_id, "items": executions, "count": len(executions)}


def fetch_execution_response(run_dir: Path, execution_id: str) -> dict:
    return execution_response(load_fetch_execution(run_dir, execution_id))


def fetch_execution_logs_response(run_id: str, run_dir: Path, execution_id: str) -> dict:
    lines = read_execution_log_lines(run_dir, execution_id)
    return {"run_id": run_id, "execution_id": execution_id, "lines": lines}


def cancel_fetch_execution_response(run_dir: Path, execution_id: str, *, reason: str | None) -> dict:
    return execution_response(cancel_fetch_execution(run_dir, execution_id, reason=reason))
