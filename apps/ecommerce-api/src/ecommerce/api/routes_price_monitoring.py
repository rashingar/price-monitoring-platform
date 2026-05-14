"""Price Monitoring selection, review, and export API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.artifacts import artifact_link_payload, is_artifact_path_allowed
from ecommerce.catalog import MissingCatalogColumnsError
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.policy import (
    collect_price_monitoring_database_readiness,
    require_database_ready_for_price_monitoring,
)
from ecommerce.db.repositories.price_monitoring import count_run_observations_by_match_status, get_monitoring_run, list_catalog_snapshot, list_monitoring_runs as list_db_monitoring_runs, list_model_price_history, list_product_price_history, list_price_observations, list_price_observation_listings, monitoring_run_to_dict
from ecommerce.db.session import session_scope
from ecommerce.file_editor.safe_paths import get_allowed_roots, is_path_allowed
from ecommerce.ignore import MissingIgnoreColumnsError
from ecommerce.price_monitoring import review_service
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
    backfill_run_listing_evidence,
    persist_run_creation_if_configured,
)
from ecommerce.price_monitoring.review import (
    PriceActionInput,
    PriceReviewError,
    apply_price_actions_to_rows,
    load_price_review_rows,
    load_price_review_rows_from_observations,
    load_review_csv,
    summarize_review_rows,
)
from ecommerce.price_monitoring.runs import (
    PRICE_MONITORING_RUNS_DIR,
    InvalidPriceMonitoringRunIdError,
    PriceMonitoringRunRecord,
    create_price_monitoring_run,
    resolve_price_monitoring_run_dir,
    run_record_to_response,
    selection_preview_to_response,
    validate_price_monitoring_run_id,
)
from ecommerce.price_monitoring.run_payloads import (
    PriceActionApiInput,
    PriceMonitoringFetchApiRequest,
    PriceMonitoringFetchCancelApiRequest,
    PriceMonitoringSelectionApiRequest,
    PriceReviewActionsApiRequest,
    PriceUpdateExportApiRequest,
    to_action_input,
    to_selection_request,
)
from ecommerce.price_monitoring.service import NoEligibleProductsSelectedError
from ecommerce.price_monitoring import service as monitoring_service
from ecommerce.price_monitoring.selection import (
    PriceMonitoringSelectionRequest,
)
router = APIRouter(prefix="/api/price-monitoring", tags=["price-monitoring"])


@router.post("/selection/preview")
def preview_selection(request: PriceMonitoringSelectionApiRequest) -> dict:
    """Preview monitoring selection; products require active Vendor Sources URLs."""

    _require_price_monitoring_database_ready()
    selection_request = _to_selection_request(request, dry_run=True)
    try:
        return monitoring_service.preview_selection_response(selection_request, session_scope_fn=session_scope)
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


@router.post("/runs")
def create_run(request: PriceMonitoringSelectionApiRequest) -> dict:
    """Create a monitoring run for products with active source URLs only."""

    _require_price_monitoring_database_ready()
    selection_request = _to_selection_request(request, dry_run=False)
    try:
        return monitoring_service.create_run_response(
            selection_request,
            session_scope_fn=session_scope,
            create_price_monitoring_run_fn=create_price_monitoring_run,
            persist_run_creation_fn=_persist_run_creation_for_route,
        )
    except NoEligibleProductsSelectedError as exc:
        raise HTTPException(status_code=400, detail=exc.detail()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MissingCatalogColumnsError, MissingIgnoreColumnsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except _PriceMonitoringRunPersistenceError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Price monitoring DB persistence failed: {_safe_db_error(exc.original)}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price monitoring run creation failed.") from exc


@router.get("/runs")
def list_runs() -> dict:
    _require_price_monitoring_database_ready()
    try:
        return monitoring_service.list_runs_response(
            session_scope_fn=session_scope,
            list_monitoring_runs_fn=list_db_monitoring_runs,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB persistence failed: {_safe_db_error(exc)}") from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    try:
        validate_run_id_for_db_route(run_id)
        return monitoring_service.get_run_response(
            run_id,
            session_scope_fn=session_scope,
            get_monitoring_run_fn=get_monitoring_run,
        )
    except InvalidPriceMonitoringRunIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc


@router.post("/runs/{run_id}/fetch", status_code=202)
def post_price_monitoring_fetch(run_id: str, request: PriceMonitoringFetchApiRequest) -> dict:
    """Run Vendor Sources capture for selected active source URLs; no marketplace fallback."""

    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        return monitoring_service.enqueue_fetch_response(
            run_dir,
            source=request.source,
            catalog_url=request.catalog_url,
            enqueue_fetch_execution_fn=enqueue_fetch_execution,
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


@router.get("/runs/{run_id}/fetch")
def get_price_monitoring_fetch(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        return monitoring_service.latest_fetch_response(run_id, run_dir)
    except Exception as exc:
        if isinstance(exc, FileNotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail="Price monitoring fetch result loading failed.") from exc


@router.get("/runs/{run_id}/fetch/logs")
def get_latest_price_monitoring_fetch_logs(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        return monitoring_service.latest_fetch_logs_response(run_id, run_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/fetch/cancel")
def cancel_latest_price_monitoring_fetch(
    run_id: str,
    request: PriceMonitoringFetchCancelApiRequest | None = None,
) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        return monitoring_service.cancel_latest_fetch_response(run_dir, reason=(request.reason if request else None))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs/{run_id}/fetch/executions")
def list_price_monitoring_fetch_executions(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    return monitoring_service.list_fetch_executions_response(run_id, run_dir)


@router.get("/runs/{run_id}/fetch/{execution_id}")
def get_price_monitoring_fetch_execution(run_id: str, execution_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        return monitoring_service.fetch_execution_response(run_dir, execution_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/fetch/{execution_id}/logs")
def get_price_monitoring_fetch_execution_logs(run_id: str, execution_id: str) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        return monitoring_service.fetch_execution_logs_response(run_id, run_dir, execution_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/fetch/{execution_id}/cancel")
def cancel_price_monitoring_fetch_execution(
    run_id: str,
    execution_id: str,
    request: PriceMonitoringFetchCancelApiRequest | None = None,
) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    try:
        return monitoring_service.cancel_fetch_execution_response(run_dir, execution_id, reason=(request.reason if request else None))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
def get_price_review(run_id: str, enriched_csv_path: str | None = None, include_all_listings: bool = False) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    enriched_path = _optional_read_path(enriched_csv_path)
    try:
        return review_service.get_review_response(
            run_id,
            run_dir,
            enriched_path,
            include_all_listings=include_all_listings,
            session_scope_fn=session_scope,
            list_price_observations_fn=list_price_observations,
            list_price_observation_listings_fn=list_price_observation_listings,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PriceReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price review loading failed.") from exc


@router.post("/runs/{run_id}/backfill-listings")
def post_price_review_listing_backfill(run_id: str) -> dict:
    _require_price_monitoring_database_ready()
    validate_run_id_for_db_route(run_id)
    try:
        return review_service.backfill_listing_response(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB persistence failed: {_safe_db_error(exc)}") from exc


@router.post("/runs/{run_id}/review/actions")
def post_price_review_actions(run_id: str, request: PriceReviewActionsApiRequest) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    enriched_path = _optional_read_path(request.enriched_csv_path)
    try:
        return review_service.apply_review_actions_response(
            run_id,
            run_dir,
            enriched_path,
            [_to_action_input(action) for action in request.actions],
            session_scope_fn=session_scope,
            list_price_observations_fn=list_price_observations,
            list_price_observation_listings_fn=list_price_observation_listings,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PriceReviewError, MissingIgnoreColumnsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Price monitoring DB query failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price review action application failed.") from exc


@router.post("/runs/{run_id}/export-price-update")
def post_price_update_export(run_id: str, request: PriceUpdateExportApiRequest) -> dict:
    _require_price_monitoring_database_ready()
    run_dir = _resolve_run_dir(run_id)
    review_csv_path = _optional_read_path(request.review_csv_path) or run_dir / "review.csv"
    output_path = _optional_write_path(request.output_path)

    try:
        return review_service.export_price_update_response(run_id, run_dir, review_csv_path, output_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PriceReviewError, MissingIgnoreColumnsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Price update export failed.") from exc


def _to_selection_request(
    request: PriceMonitoringSelectionApiRequest,
    *,
    dry_run: bool,
) -> PriceMonitoringSelectionRequest:
    try:
        return to_selection_request(request, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    return to_action_input(action)


def _require_price_monitoring_database_ready() -> None:
    require_database_ready_for_price_monitoring()


class _PriceMonitoringRunPersistenceError(RuntimeError):
    def __init__(self, original: Exception) -> None:
        super().__init__(str(original) or original.__class__.__name__)
        self.original = original


def _persist_run_creation_for_route(
    record: PriceMonitoringRunRecord,
    *,
    trigger_type: str = "manual",
) -> bool:
    try:
        return persist_run_creation_if_configured(record, trigger_type=trigger_type)
    except Exception as exc:
        raise _PriceMonitoringRunPersistenceError(exc) from exc


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
