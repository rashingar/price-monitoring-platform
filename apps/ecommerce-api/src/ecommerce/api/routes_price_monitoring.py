"""Price Monitoring selection, review, and export API routes."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.artifacts import artifact_link_payload, is_artifact_path_allowed
from ecommerce.catalog import MissingCatalogColumnsError
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.diagnostics import collect_run_persistence_status
from ecommerce.db.policy import (
    collect_price_monitoring_database_readiness,
    require_database_ready_for_price_monitoring,
)
from ecommerce.db.repositories import (
    count_run_observations_by_match_status,
    get_monitoring_run,
    list_catalog_snapshot,
    list_monitoring_runs as list_db_monitoring_runs,
    list_model_price_history,
    list_product_price_history,
    list_price_observations,
    monitoring_run_to_dict,
)
from ecommerce.db.session import session_scope
from ecommerce.file_editor.safe_paths import get_allowed_roots, is_path_allowed
from ecommerce.ignore import MissingIgnoreColumnsError
from ecommerce.price_monitoring.export import export_price_update_csv
from ecommerce.price_monitoring.fetch_execution import (
    ActiveFetchExecutionError,
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
from ecommerce.price_monitoring.fetch_run import (
    load_price_monitoring_fetch_result,
)
from ecommerce.price_monitoring.persistence import (
    persist_run_creation_if_configured,
)
from ecommerce.price_monitoring.review import (
    PriceActionInput,
    PriceReviewError,
    apply_price_actions,
    load_price_review_rows,
    load_review_csv,
    summarize_review_rows,
)
from ecommerce.price_monitoring.runs import (
    PRICE_MONITORING_RUNS_DIR,
    InvalidPriceMonitoringRunIdError,
    create_price_monitoring_run,
    load_price_monitoring_run,
    resolve_price_monitoring_run_dir,
    run_record_to_response,
    selection_preview_to_response,
    validate_price_monitoring_run_id,
)
from ecommerce.price_monitoring.selection import (
    PriceMonitoringFilters,
    PriceMonitoringSelectionRequest,
    PriceMonitoringSelectionResult,
    select_price_monitoring_products,
)
from ecommerce.price_monitoring.source_url_coverage import (
    compute_source_url_coverage,
    require_active_source_url_coverage,
)
router = APIRouter(prefix="/api/price-monitoring", tags=["price-monitoring"])


class PriceMonitoringFiltersRequest(BaseModel):
    q: str | None = None
    category: str | None = None
    family: str | None = None
    category_name: str | None = None
    sub_category: str | None = None
    manufacturer: str | None = None
    marketplace: str | None = None
    has_mpn: bool | None = True
    atomic_only: bool = True
    automation_eligible_only: bool = True


class PriceMonitoringSelectionApiRequest(BaseModel):
    source: str | None = None
    source_name: str | None = None
    vendor_slug: str | None = None
    source_filter: str | None = None
    filters: PriceMonitoringFiltersRequest = Field(default_factory=PriceMonitoringFiltersRequest)
    selected_models: list[str] = Field(default_factory=list)
    excluded_models: list[str] = Field(default_factory=list)
    include_ignored: bool = False
    dry_run: bool = False


class PriceActionApiInput(BaseModel):
    model: str = ""
    selected_action: str = ""
    undercut_amount: Decimal | None = None
    reason: str = ""


class PriceReviewActionsApiRequest(BaseModel):
    enriched_csv_path: str | None = None
    actions: list[PriceActionApiInput] = Field(default_factory=list)


class PriceUpdateExportApiRequest(BaseModel):
    review_csv_path: str | None = None
    output_path: str | None = None


class PriceMonitoringFetchApiRequest(BaseModel):
    source: str | None = None
    catalog_url: str | None = None


class PriceMonitoringFetchCancelApiRequest(BaseModel):
    reason: str | None = None


@router.post("/selection/preview")
def preview_selection(request: PriceMonitoringSelectionApiRequest) -> dict:
    """Preview monitoring selection; products require active Vendor Sources URLs."""

    _require_price_monitoring_database_ready()
    selection_request = _to_selection_request(request, dry_run=True)
    try:
        result = _select_price_monitoring_products_with_source_url_coverage(selection_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MissingCatalogColumnsError, MissingIgnoreColumnsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price monitoring selection failed.") from exc
    return selection_preview_to_response(result)


@router.post("/runs")
def create_run(request: PriceMonitoringSelectionApiRequest) -> dict:
    """Create a monitoring run for products with active source URLs only."""

    _require_price_monitoring_database_ready()
    selection_request = _to_selection_request(request, dry_run=False)
    preview: PriceMonitoringSelectionResult | None = None
    try:
        record = create_price_monitoring_run(selection_request)
    except ValueError as exc:
        if str(exc) == "No eligible products selected.":
            preview = _select_price_monitoring_products_with_source_url_coverage(selection_request)
            raise HTTPException(
                status_code=400,
                detail={
                    "message": str(exc),
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
                },
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MissingCatalogColumnsError, MissingIgnoreColumnsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price monitoring run creation failed.") from exc
    try:
        persist_run_creation_if_configured(record, trigger_type="manual")
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB persistence failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB persistence failed: {_safe_db_error(exc)}") from exc
    return run_record_to_response(record)


@router.get("/runs")
def list_runs() -> dict:
    _require_price_monitoring_database_ready()
    try:
        with session_scope() as session:
            items = [_db_run_to_route_response(item) for item in list_db_monitoring_runs(session)]
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    for item in items:
        item["db"] = _run_db_payload(str(item.get("run_id") or ""))
    return {"items": items}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    try:
        validate_run_id_for_db_route(run_id)
        with session_scope() as session:
            run = get_monitoring_run(session, run_id)
            if run is None:
                raise FileNotFoundError(f"DB-backed price monitoring run not found: {run_id}")
            db_payload = monitoring_run_to_dict(run)
        output_dir = Path(str(db_payload.get("output_dir") or ""))
        if output_dir.exists():
            payload = load_price_monitoring_run(run_id)
        else:
            payload = _db_run_to_route_response(db_payload)
    except InvalidPriceMonitoringRunIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    payload["db"] = _run_db_payload(run_id)
    return payload


@router.post("/runs/{run_id}/fetch", status_code=202)
def post_price_monitoring_fetch(run_id: str, request: PriceMonitoringFetchApiRequest) -> dict:
    """Run Vendor Sources capture for selected active source URLs; no marketplace fallback."""

    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        execution = enqueue_fetch_execution(
            run_dir,
            source=request.source,
            catalog_url=request.catalog_url,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ActiveFetchExecutionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "run_id": exc.execution.run_id,
                "execution_id": exc.execution.execution_id,
                "status": exc.execution.status,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price monitoring fetch enqueue failed.") from exc
    return execution_response(execution)


@router.get("/runs/{run_id}/fetch")
def get_price_monitoring_fetch(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        execution = load_latest_fetch_execution(run_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price monitoring fetch execution loading failed.") from exc
    if execution is not None:
        return execution_response(execution)
    try:
        result = load_price_monitoring_fetch_result(run_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price monitoring fetch result loading failed.") from exc
    payload = source_url_fetch_result_to_execution_payload(result)
    persistence = _fetch_result_persistence_payload(run_id)
    payload["persistence_status"] = str(persistence["persistence_status"])
    payload["persistence_warnings"] = persistence["warnings"]
    return payload


@router.get("/runs/{run_id}/fetch/logs")
def get_latest_price_monitoring_fetch_logs(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        execution = load_latest_fetch_execution(run_dir)
        if execution is None:
            raise FileNotFoundError("No fetch execution exists for this run.")
        lines = read_latest_execution_log_lines(run_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run_id": run_id, "execution_id": execution.execution_id, "lines": lines}


@router.post("/runs/{run_id}/fetch/cancel")
def cancel_latest_price_monitoring_fetch(
    run_id: str,
    request: PriceMonitoringFetchCancelApiRequest | None = None,
) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        execution = cancel_latest_active_fetch_execution(run_dir, reason=(request.reason if request else None))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return execution_response(execution)


@router.get("/runs/{run_id}/fetch/executions")
def list_price_monitoring_fetch_executions(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    executions = [execution_response(execution) for execution in list_fetch_executions(run_dir)]
    return {"run_id": run_id, "items": executions, "count": len(executions)}


@router.get("/runs/{run_id}/fetch/{execution_id}")
def get_price_monitoring_fetch_execution(run_id: str, execution_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        execution = load_fetch_execution(run_dir, execution_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return execution_response(execution)


@router.get("/runs/{run_id}/fetch/{execution_id}/logs")
def get_price_monitoring_fetch_execution_logs(run_id: str, execution_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        lines = read_execution_log_lines(run_dir, execution_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run_id": run_id, "execution_id": execution_id, "lines": lines}


@router.post("/runs/{run_id}/fetch/{execution_id}/cancel")
def cancel_price_monitoring_fetch_execution(
    run_id: str,
    execution_id: str,
    request: PriceMonitoringFetchCancelApiRequest | None = None,
) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        execution = cancel_fetch_execution(run_dir, execution_id, reason=(request.reason if request else None))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return execution_response(execution)


@router.get("/db/status")
def get_price_monitoring_db_status() -> dict:
    return collect_price_monitoring_database_readiness()


@router.get("/observations")
def get_price_monitoring_observations(
    run_id: str | None = None,
    source: str | None = None,
    catalog_source: str | None = None,
    model: str | None = None,
    mpn: str | None = None,
    product_id: int | None = None,
    match_status: str | None = None,
    include_unmatched: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    _require_price_monitoring_database_ready()
    safe_match_status = _optional_match_status(match_status)
    safe_limit = max(1, min(int(limit), 1000))
    safe_offset = max(0, int(offset))
    try:
        with session_scope() as session:
            items, count = list_price_observations(
                session,
                run_id=_optional_query_text(run_id),
                source=_optional_query_text(source),
                catalog_source=_optional_query_text(catalog_source),
                model=_optional_query_text(model),
                mpn=_optional_query_text(mpn),
                product_id=product_id,
                match_status=safe_match_status,
                include_unmatched=include_unmatched,
                limit=safe_limit,
                offset=safe_offset,
            )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    return {"items": items, "limit": safe_limit, "offset": safe_offset, "count": count}


@router.get("/runs/{run_id}/observations")
def get_price_monitoring_run_observations(
    run_id: str,
    include_unmatched: bool = True,
    limit: int = 1000,
    offset: int = 0,
) -> dict:
    _require_price_monitoring_database_ready()
    validate_run_id_for_db_route(run_id)
    safe_limit = max(1, min(int(limit), 5000))
    safe_offset = max(0, int(offset))
    try:
        with session_scope() as session:
            items, count = list_price_observations(
                session,
                run_id=run_id,
                include_unmatched=include_unmatched,
                limit=safe_limit,
                offset=safe_offset,
            )
            matched_count, unmatched_count = count_run_observations_by_match_status(session, run_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    return {
        "run_id": run_id,
        "items": items,
        "count": count,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
    }


@router.get("/runs/{run_id}/catalog-snapshot")
def get_price_monitoring_run_catalog_snapshot(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    validate_run_id_for_db_route(run_id)
    try:
        with session_scope() as session:
            items = list_catalog_snapshot(session, run_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    return {"run_id": run_id, "items": items, "count": len(items)}


@router.get("/products/by-model/{model}/price-history")
def get_price_monitoring_model_price_history(
    model: str,
    catalog_source: str | None = None,
    include_unmatched: bool = True,
) -> dict:
    _require_price_monitoring_database_ready()
    try:
        with session_scope() as session:
            items, count = list_model_price_history(
                session,
                model,
                catalog_source=_optional_query_text(catalog_source),
                include_unmatched=include_unmatched,
            )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    return {"model": model, "catalog_source": _optional_query_text(catalog_source), "items": items, "count": count}


@router.get("/products/{product_id}/price-history")
def get_price_monitoring_product_price_history(product_id: str) -> dict:
    numeric_product_id = _parse_product_id_route_value(product_id)
    _require_price_monitoring_database_ready()
    try:
        with session_scope() as session:
            items, count = list_product_price_history(session, numeric_product_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    return {"product_id": numeric_product_id, "items": items, "count": count}


@router.get("/runs/{run_id}/review")
def get_price_review(run_id: str, enriched_csv_path: str | None = None) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    enriched_path = _optional_read_path(enriched_csv_path)
    try:
        rows = load_price_review_rows(run_dir, enriched_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PriceReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price review loading failed.") from exc

    return {
        "run_id": run_id,
        "items": [row.to_api_dict() for row in rows],
        "summary": summarize_review_rows(rows),
    }


@router.post("/runs/{run_id}/review/actions")
def post_price_review_actions(run_id: str, request: PriceReviewActionsApiRequest) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    enriched_path = _optional_read_path(request.enriched_csv_path)
    try:
        result = apply_price_actions(
            run_dir,
            [_to_action_input(action) for action in request.actions],
            enriched_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PriceReviewError, MissingIgnoreColumnsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price review action application failed.") from exc

    return {
        "run_id": run_id,
        "status": "review_actions_applied",
        "review_csv_path": str(result.review_csv_path),
        "review_actions_path": str(result.review_actions_path),
        "artifacts": [
            artifact_link_payload(result.review_csv_path),
            artifact_link_payload(result.review_actions_path),
        ],
        "summary": result.summary,
    }


@router.post("/runs/{run_id}/export-price-update")
def post_price_update_export(run_id: str, request: PriceUpdateExportApiRequest) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    review_csv_path = _optional_read_path(request.review_csv_path) or run_dir / "review.csv"
    output_path = _optional_write_path(request.output_path)

    try:
        rows = load_review_csv(review_csv_path)
        result = export_price_update_csv(run_dir, rows, output_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PriceReviewError, MissingIgnoreColumnsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price update export failed.") from exc

    return {
        "run_id": run_id,
        "status": "price_update_exported",
        "output_path": str(result.output_path),
        "artifact": artifact_link_payload(result.output_path),
        "rows_exported": result.rows_exported,
        "columns": result.columns,
    }


def _to_selection_request(
    request: PriceMonitoringSelectionApiRequest,
    *,
    dry_run: bool,
) -> PriceMonitoringSelectionRequest:
    return PriceMonitoringSelectionRequest(
        source=request.source or "",
        source_name=request.source_name,
        vendor_slug=request.vendor_slug,
        source_filter=request.source_filter,
        filters=PriceMonitoringFilters(
            q=request.filters.q,
            category=request.filters.category,
            family=request.filters.family,
            category_name=request.filters.category_name,
            sub_category=request.filters.sub_category,
            manufacturer=request.filters.manufacturer,
            marketplace=_marketplace_or_none(request.filters.marketplace),
            has_mpn=request.filters.has_mpn,
            atomic_only=request.filters.atomic_only,
            automation_eligible_only=request.filters.automation_eligible_only,
        ),
        selected_models=request.selected_models,
        excluded_models=request.excluded_models,
        include_ignored=request.include_ignored,
        dry_run=dry_run,
    )


def _select_price_monitoring_products_with_source_url_coverage(
    selection_request: PriceMonitoringSelectionRequest,
) -> PriceMonitoringSelectionResult:
    result = select_price_monitoring_products(selection_request)
    with session_scope() as session:
        coverage = compute_source_url_coverage(session, result.items, result.source)
    return require_active_source_url_coverage(result, coverage)


def _marketplace_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in {"bestprice", "skroutz", "both", "none"}:
        raise HTTPException(status_code=400, detail="marketplace must be one of: bestprice, skroutz, both, none")
    return normalized


def _resolve_run_dir(run_id: str) -> Path:
    try:
        run_dir = resolve_price_monitoring_run_dir(run_id, PRICE_MONITORING_RUNS_DIR)
    except InvalidPriceMonitoringRunIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Price monitoring run folder not found: {run_dir}")
    return run_dir


def _optional_read_path(value: str | None) -> Path | None:
    return _optional_safe_path(value, operation="read", artifact_roots_only=False)


def _optional_write_path(value: str | None) -> Path | None:
    return _optional_safe_path(value, operation="write", artifact_roots_only=True)


def _optional_safe_path(value: str | None, *, operation: str, artifact_roots_only: bool) -> Path | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    requested = Path(text)
    if any(part == ".." for part in requested.parts):
        raise HTTPException(status_code=400, detail="Path traversal is not allowed.")
    resolved = requested.expanduser().resolve(strict=False)
    if artifact_roots_only:
        if not is_artifact_path_allowed(resolved.parent):
            raise HTTPException(status_code=403, detail=f"Path is outside allowed artifact roots: {resolved}")
        return resolved
    if not _is_allowed_browser_read_path(resolved):
        raise HTTPException(status_code=403, detail=f"Path is outside allowed {operation} roots: {resolved}")
    return resolved


def _is_allowed_browser_read_path(path: Path) -> bool:
    if is_artifact_path_allowed(path):
        return True
    return is_path_allowed(path, get_allowed_roots())


def _to_action_input(action: PriceActionApiInput) -> PriceActionInput:
    return PriceActionInput(
        model=action.model,
        selected_action=action.selected_action,
        undercut_amount=action.undercut_amount,
        reason=action.reason,
    )


def _fetch_result_persistence_payload(run_id: str) -> dict[str, object]:
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


def _run_db_payload(run_id: str) -> dict[str, object]:
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


def _db_run_to_route_response(item: dict[str, object]) -> dict[str, object]:
    run_id = str(item.get("run_id") or "")
    output_dir = Path(str(item.get("output_dir") or ""))
    artifacts: list[dict[str, object]] = []
    latest_fetch = None
    selected_models: list[object] = []
    skipped_models: list[object] = []
    skipped_by_reason: dict[str, object] = {}
    if output_dir.exists() and output_dir.is_dir():
        try:
            file_payload = load_price_monitoring_run(run_id)
            artifacts = file_payload.get("artifacts", []) if isinstance(file_payload.get("artifacts"), list) else []
            latest_fetch = file_payload.get("latest_fetch")
            selected_models = file_payload.get("selected_models", []) if isinstance(file_payload.get("selected_models"), list) else []
            skipped_models = file_payload.get("skipped_models", []) if isinstance(file_payload.get("skipped_models"), list) else []
            skipped_by_reason = (
                file_payload.get("skipped_by_reason", {}) if isinstance(file_payload.get("skipped_by_reason"), dict) else {}
            )
        except Exception:
            artifacts = [
                artifact_link_payload(path)
                for path in sorted(output_dir.iterdir(), key=lambda child: child.name.casefold())
                if path.is_file()
            ]
    return {
        "run_id": run_id,
        "status": str(item.get("status") or ""),
        "source": str(item.get("source") or ""),
        "created_at": str(item.get("created_at") or ""),
        "output_dir": str(item.get("output_dir") or ""),
        "input_csv_path": str(item.get("input_csv_path") or ""),
        "selection_summary_path": str(item.get("selection_summary_path") or ""),
        "selected_count": item.get("selected_count"),
        "skipped_count": item.get("skipped_count"),
        "skipped_by_reason": skipped_by_reason,
        "selected_models": selected_models,
        "skipped_models": skipped_models,
        "latest_fetch": latest_fetch,
        "artifacts": artifacts,
    }


def _require_price_monitoring_database_ready() -> None:
    require_database_ready_for_price_monitoring()


def validate_run_id_for_db_route(run_id: str) -> None:
    try:
        validate_price_monitoring_run_id(run_id)
    except InvalidPriceMonitoringRunIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _optional_query_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _optional_match_status(value: str | None) -> str | None:
    text = _optional_query_text(value)
    if text is None:
        return None
    if text not in {"matched", "unmatched"}:
        raise HTTPException(status_code=400, detail="match_status must be one of: matched, unmatched")
    return text


def _parse_product_id_route_value(value: str) -> int:
    text = value.strip()
    by_model_hint = "Use /api/price-monitoring/products/by-model/{model}/price-history for model identifiers."
    if not text.isdigit():
        raise HTTPException(status_code=400, detail=f"product_id must be an integer. {by_model_hint}")
    if len(text) > 1 and text.startswith("0"):
        raise HTTPException(status_code=400, detail=f"product_id must not contain leading zeroes. {by_model_hint}")
    return int(text)


def _safe_db_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return sanitize_database_error(message) or exc.__class__.__name__
