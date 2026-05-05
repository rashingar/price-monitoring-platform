"""Vendor Sources workflow API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from pricefetcher.api import routes_source_url_agent as source_url_agent
from pricefetcher.api.routes_source_url_agent import (
    SourceUrlAgentRunRequest,
    SourceUrlCandidateReviewLayoutRequest,
    SourceUrlCandidateReviewRequest,
)
from pricefetcher.artifacts import artifact_link_payload
from pricefetcher.db.config import sanitize_database_error
from pricefetcher.db.policy import require_database_ready_for_price_monitoring
from pricefetcher.db.session import session_scope
from pricefetcher.vendor_sources.capture import (
    get_vendor_source_capture_run,
    list_vendor_source_capture_runs,
    run_vendor_source_capture,
    vendor_source_capture_run_to_dict,
)
from pricefetcher.vendor_sources.coverage import source_health_items, source_url_summary
from pricefetcher.vendor_sources import list_vendor_source_capabilities

router = APIRouter(prefix="/api/vendor-sources", tags=["vendor-sources"])


class VendorSourceCaptureRunApiRequest(BaseModel):
    source_name: str | None = None
    vendor_slug: str | None = None
    catalog_source: str | None = None
    catalog_product_ids: list[int] = Field(default_factory=list)
    product_source_ids: list[int] = Field(default_factory=list)
    refresh_after_minutes: int = 360
    limit: int = 50
    dry_run: bool = False
    admin_all_sources: bool = False
    # Deprecated request name retained for old callers. Prefer vendor_slug/source_name.
    vendor: str | None = None
    include_not_due: bool = False


@router.get("/sources")
def list_vendor_sources() -> dict[str, Any]:
    return {"items": list_vendor_source_capabilities()}


@router.get("/source-urls/summary")
def get_vendor_source_url_summary(source_name: str | None = None) -> dict[str, Any]:
    _require_vendor_sources_database_ready()
    try:
        with session_scope() as session:
            return source_url_summary(session, source_name=source_name)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Vendor source URL summary failed: {_safe_db_error(exc)}") from exc


@router.get("/source-health")
def get_vendor_source_health(
    vendor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    _require_vendor_sources_database_ready()
    try:
        with session_scope() as session:
            return source_health_items(session, vendor=vendor, limit=limit, offset=offset)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Vendor source health query failed: {_safe_db_error(exc)}") from exc


@router.post("/captures/runs")
def post_vendor_source_capture_runs(request: VendorSourceCaptureRunApiRequest) -> dict[str, Any]:
    _require_vendor_sources_database_ready()
    try:
        with session_scope() as session:
            result = run_vendor_source_capture(
                session,
                source_name=request.source_name,
                vendor_slug=request.vendor_slug or request.vendor,
                catalog_source=request.catalog_source,
                catalog_product_ids=request.catalog_product_ids,
                product_source_ids=request.product_source_ids,
                refresh_after_minutes=request.refresh_after_minutes,
                limit=request.limit,
                include_not_due=request.include_not_due,
                dry_run=request.dry_run,
                admin_all_sources=request.admin_all_sources,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Vendor source capture run failed: {_safe_db_error(exc)}") from exc
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        raise HTTPException(status_code=500, detail=f"Vendor source capture run failed: {message}") from exc
    payload = result.to_dict()
    payload["selected_count"] = result.selected_product_source_count
    return payload


@router.get("/captures/runs")
def get_vendor_source_capture_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    _require_vendor_sources_database_ready()
    try:
        with session_scope() as session:
            return {"items": list_vendor_source_capture_runs(session, limit=limit, offset=offset), "limit": limit, "offset": offset}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Vendor source capture run history failed: {_safe_db_error(exc)}") from exc


@router.get("/captures/runs/{run_id}")
def get_vendor_source_capture_run_detail(run_id: str) -> dict[str, Any]:
    _require_vendor_sources_database_ready()
    try:
        with session_scope() as session:
            row = get_vendor_source_capture_run(session, run_id)
            if row is None:
                raise FileNotFoundError(f"Vendor source capture run not found: {run_id}")
            return vendor_source_capture_run_to_dict(row)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Vendor source capture run lookup failed: {_safe_db_error(exc)}") from exc


@router.get("/captures/runs/{run_id}/artifacts")
def get_vendor_source_capture_run_artifacts(run_id: str) -> dict[str, Any]:
    _require_vendor_sources_database_ready()
    try:
        with session_scope() as session:
            row = get_vendor_source_capture_run(session, run_id)
            if row is None:
                raise FileNotFoundError(f"Vendor source capture run not found: {run_id}")
            artifact_paths = [str(path) for path in row.artifact_refs_json or []]
            if row.result_path and row.result_path not in artifact_paths:
                artifact_paths.insert(0, row.result_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Vendor source capture artifact lookup failed: {_safe_db_error(exc)}") from exc
    return {"run_id": run_id, "items": [artifact_link_payload(Path(path)) for path in artifact_paths]}


@router.post("/captures/run")
def post_vendor_source_capture_run_compatibility(request: VendorSourceCaptureRunApiRequest) -> dict[str, Any]:
    payload = post_vendor_source_capture_runs(request)
    payload["deprecated"] = True
    payload["replacement_endpoint"] = "/api/vendor-sources/captures/runs"
    return payload


@router.post("/agent/runs")
def launch_vendor_source_agent_run(request: SourceUrlAgentRunRequest) -> dict[str, Any]:
    return source_url_agent.launch_source_url_agent_run(request)


@router.get("/agent/runs")
def list_vendor_source_agent_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return source_url_agent.list_source_url_agent_runs(limit=limit, offset=offset)


@router.get("/agent/runs/{run_id}")
def get_vendor_source_agent_run(run_id: str) -> dict[str, Any]:
    return source_url_agent.get_source_url_agent_run(run_id)


@router.get("/agent/runs/{run_id}/artifacts")
def get_vendor_source_agent_run_artifacts(run_id: str) -> dict[str, Any]:
    return source_url_agent.get_source_url_agent_run_artifacts(run_id)


@router.get("/candidates")
def list_vendor_source_candidates(
    status: str | None = None,
    source_name: str | None = None,
    run_id: str | None = None,
    model: str | None = None,
    catalog_product_id: str | None = None,
    min_confidence: str | None = None,
    max_confidence: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return source_url_agent.list_source_url_agent_candidates(
        status=status,
        source_name=source_name,
        run_id=run_id,
        model=model,
        catalog_product_id=catalog_product_id,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        limit=limit,
        offset=offset,
    )


@router.get("/candidates/review-layout")
def get_vendor_source_candidate_review_layout(user_key: str | None = None) -> dict[str, Any]:
    payload = source_url_agent.get_source_url_candidate_review_layout(user_key=user_key)
    return _vendor_review_layout_payload(payload)


@router.put("/candidates/review-layout")
def save_vendor_source_candidate_review_layout(request: SourceUrlCandidateReviewLayoutRequest) -> dict[str, Any]:
    payload = source_url_agent.save_source_url_candidate_review_layout(request)
    return _vendor_review_layout_payload(payload)


@router.post("/candidates/review-layout/reset")
def reset_vendor_source_candidate_review_layout(user_key: str | None = None) -> dict[str, Any]:
    payload = source_url_agent.reset_source_url_candidate_review_layout(user_key=user_key)
    return _vendor_review_layout_payload(payload)


@router.get("/candidates/{candidate_id}")
def get_vendor_source_candidate(candidate_id: int) -> dict[str, Any]:
    payload = source_url_agent.get_source_url_agent_candidate(candidate_id)
    drawer = payload.get("drawer")
    if isinstance(drawer, dict):
        drawer["review_endpoint"] = f"/api/vendor-sources/candidates/{candidate_id}/review"
    return payload


@router.patch("/candidates/{candidate_id}/review")
def review_vendor_source_candidate(candidate_id: int, request: SourceUrlCandidateReviewRequest) -> dict[str, Any]:
    return source_url_agent.review_source_url_agent_candidate(candidate_id, request)


def _vendor_review_layout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    actions = payload.get("actions")
    if isinstance(actions, dict):
        actions["review_endpoint_template"] = "/api/vendor-sources/candidates/{candidate_id}/review"
    return payload


def _require_vendor_sources_database_ready() -> None:
    require_database_ready_for_price_monitoring()


def _safe_db_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return sanitize_database_error(message) or exc.__class__.__name__
