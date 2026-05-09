"""Source URL Agent candidate review API routes."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ecommerce.artifacts import ArtifactPathError, ArtifactPathForbiddenError, artifact_link_payload, list_run_artifacts
from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.models import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun, SourceUrlDiscoveryTask, UiViewPreference
from ecommerce.db.policy import catalog_database_unavailable_detail, collect_catalog_database_readiness, require_database_ready_for_catalog
from ecommerce.db.repositories import json_safe_value
from ecommerce.db.session import session_scope
from ecommerce.db.source_url_repository import create_or_update_imported_source_url, source_url_to_dict
from ecommerce.source_urls import normalize_source_url
from ecommerce.source_url_agent.agent import Resolver, SourceUrlAgentOptions, SourceUrlAgentResult, run_source_url_agent
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate
from ecommerce.source_url_agent.products import AgentProduct, SourceUrlAgentInputError, read_products_from_catalog, read_products_from_csv
from ecommerce.source_url_agent.sources import SOURCE_CHOICES, SourceDefinition, load_source_registry

ReviewDecision = Literal["accept", "reject", "replace_url"]
SourceUrlAgentRunMode = Literal["catalog", "csv"]
SOURCE_URL_CANDIDATE_REVIEW_VIEW_KEY = "source_url_candidate_review"
DEFAULT_USER_KEY = "default"
MIN_COLUMN_WIDTH_PX = 80
MAX_COLUMN_WIDTH_PX = 800
DEFAULT_API_MAX_PRODUCTS_PER_BATCH = 25
MAX_API_SOURCE_URL_AGENT_LIMIT = 500

# Test hook for exercising the API orchestration with the real service layer
# without launching browser-backed discovery.
SOURCE_URL_AGENT_API_RESOLVER: Resolver | None = None

DEFAULT_REVIEW_COLUMNS: list[dict[str, Any]] = [
    {"key": "status", "label": "Status", "visible": True, "order": 10, "width_px": 120, "min_width_px": 96, "data_type": "status"},
    {"key": "confidence_score", "label": "Confidence", "visible": True, "order": 20, "width_px": 120, "min_width_px": 104, "data_type": "decimal"},
    {"key": "model", "label": "Model", "visible": True, "order": 30, "width_px": 140, "min_width_px": 104, "data_type": "text"},
    {"key": "mpn", "label": "MPN", "visible": True, "order": 40, "width_px": 140, "min_width_px": 104, "data_type": "text"},
    {"key": "manufacturer", "label": "Manufacturer", "visible": True, "order": 50, "width_px": 140, "min_width_px": 112, "data_type": "text"},
    {"key": "source_name", "label": "Source", "visible": True, "order": 60, "width_px": 128, "min_width_px": 104, "data_type": "text"},
    {"key": "candidate_price", "label": "Candidate Price", "visible": True, "order": 70, "width_px": 132, "min_width_px": 112, "data_type": "money"},
    {"key": "own_price", "label": "Own Price", "visible": True, "order": 80, "width_px": 112, "min_width_px": 96, "data_type": "money"},
    {"key": "candidate_title", "label": "Candidate Title", "visible": True, "order": 90, "width_px": 260, "min_width_px": 160, "data_type": "text"},
    {"key": "candidate_url", "label": "Candidate URL", "visible": False, "order": 100, "width_px": 320, "min_width_px": 180, "data_type": "url"},
    {"key": "canonical_url", "label": "Canonical URL", "visible": False, "order": 110, "width_px": 320, "min_width_px": 180, "data_type": "url"},
    {"key": "match_method", "label": "Match Method", "visible": False, "order": 120, "width_px": 180, "min_width_px": 136, "data_type": "text"},
    {"key": "match_status", "label": "Match Status", "visible": False, "order": 130, "width_px": 136, "min_width_px": 112, "data_type": "status"},
    {"key": "competing_candidates_count", "label": "Competing", "visible": False, "order": 140, "width_px": 112, "min_width_px": 96, "data_type": "integer"},
    {"key": "run_id", "label": "Run ID", "visible": False, "order": 150, "width_px": 180, "min_width_px": 120, "data_type": "text"},
    {"key": "catalog_product_id", "label": "Catalog Product ID", "visible": False, "order": 160, "width_px": 136, "min_width_px": 112, "data_type": "integer"},
    {"key": "product_name", "label": "Product Name", "visible": False, "order": 170, "width_px": 260, "min_width_px": 160, "data_type": "text"},
    {"key": "category", "label": "Category", "visible": False, "order": 180, "width_px": 220, "min_width_px": 144, "data_type": "text"},
    {"key": "expected_listing", "label": "Expected Listing", "visible": False, "order": 190, "width_px": 132, "min_width_px": 112, "data_type": "text"},
    {"key": "source_domain", "label": "Source Domain", "visible": False, "order": 200, "width_px": 180, "min_width_px": 136, "data_type": "text"},
    {"key": "source_type", "label": "Source Type", "visible": False, "order": 210, "width_px": 136, "min_width_px": 112, "data_type": "text"},
    {"key": "created_at", "label": "Created", "visible": False, "order": 220, "width_px": 172, "min_width_px": 140, "data_type": "datetime"},
    {"key": "updated_at", "label": "Updated", "visible": False, "order": 230, "width_px": 172, "min_width_px": 140, "data_type": "datetime"},
    {"key": "reviewed_by", "label": "Reviewed By", "visible": False, "order": 240, "width_px": 140, "min_width_px": 112, "data_type": "text"},
    {"key": "reviewed_at", "label": "Reviewed At", "visible": False, "order": 250, "width_px": 172, "min_width_px": 140, "data_type": "datetime"},
]
DEFAULT_REVIEW_COLUMN_KEYS = {column["key"] for column in DEFAULT_REVIEW_COLUMNS}


class SourceUrlCandidateReviewRequest(BaseModel):
    decision: ReviewDecision
    reviewed_url: str | None = None
    review_notes: str | None = None
    reviewed_by: str | None = None


class SourceUrlAgentRunRequest(BaseModel):
    source: str = "all"
    mode: SourceUrlAgentRunMode = "catalog"
    input_path: str | None = None
    limit: int | None = Field(default=None, ge=1, le=MAX_API_SOURCE_URL_AGENT_LIMIT)
    offset: int = Field(default=0, ge=0)
    catalog_product_id: int | None = Field(default=None, ge=1)
    model: str | None = None
    selected_models: list[str] = Field(default_factory=list)
    missing_only: bool = False
    active_only: bool = True
    dry_run: bool = True
    apply_high_confidence: bool = False
    max_products_per_batch: int | None = Field(default=None, ge=1, le=MAX_API_SOURCE_URL_AGENT_LIMIT)
    max_searches_per_product_source: int | None = Field(default=None, ge=1, le=20)
    rate_limit_seconds: float | None = Field(default=None, ge=0)
    headed: bool = False
    no_browser_cache: bool = False


class SourceUrlCandidateReviewColumnPreference(BaseModel):
    key: str
    visible: bool | None = None
    order: int | None = None
    width_px: int | None = None


class SourceUrlCandidateReviewLayoutRequest(BaseModel):
    user_key: str | None = None
    columns: list[SourceUrlCandidateReviewColumnPreference] | None = None
    settings_card_collapsed: bool | None = None
    review_panel_width_px: int | None = None


def launch_source_url_agent_run(request: SourceUrlAgentRunRequest) -> dict[str, Any]:
    _require_source_url_agent_run_database_ready()
    _validate_source_choice(request.source)
    if request.apply_high_confidence and request.dry_run:
        raise HTTPException(status_code=400, detail="apply_high_confidence requires dry_run=false.")

    limit = _api_run_limit(request)
    max_products_per_batch = request.max_products_per_batch or DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    input_path = _source_url_agent_input_path(request)
    options = SourceUrlAgentOptions(
        mode=request.mode,
        source=request.source.strip().lower(),
        input_path=input_path,
        limit=limit,
        offset=request.offset,
        catalog_product_id=request.catalog_product_id,
        model=_optional_text(request.model),
        selected_models=_selected_models(request.selected_models),
        missing_only=bool(request.missing_only),
        active_only=bool(request.active_only),
        dry_run=bool(request.dry_run),
        apply_high_confidence=bool(request.apply_high_confidence),
        max_products_per_batch=max_products_per_batch,
        max_searches_per_product_source=request.max_searches_per_product_source,
        rate_limit_seconds=request.rate_limit_seconds,
        headed=bool(request.headed),
        no_browser_cache=bool(request.no_browser_cache),
    )

    try:
        with session_scope() as session:
            if request.mode == "csv":
                products = read_products_from_csv(
                    input_path or Path(),
                    catalog_source=DEFAULT_CATALOG_SOURCE,
                    active_only=request.active_only,
                    limit=limit,
                    offset=request.offset,
                    model=request.model,
                )
            else:
                products = read_products_from_catalog(
                    session,
                    catalog_source=DEFAULT_CATALOG_SOURCE,
                    active_only=request.active_only,
                    limit=limit,
                    offset=request.offset,
                    catalog_product_id=request.catalog_product_id,
                    model=request.model,
                    selected_models=_selected_models(request.selected_models),
                )
            result = run_source_url_agent(
                products=products,
                options=options,
                session=session,
                resolver=SOURCE_URL_AGENT_API_RESOLVER,
            )
    except HTTPException:
        raise
    except (FileNotFoundError, SourceUrlAgentInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL Agent run failed: {_safe_db_error(exc)}") from exc
    return _source_url_agent_result_payload(result)


def enqueue_source_url_agent_run(request: SourceUrlAgentRunRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    _require_source_url_agent_run_database_ready()
    _validate_source_choice(request.source)
    if request.apply_high_confidence and request.dry_run:
        raise HTTPException(status_code=400, detail="apply_high_confidence requires dry_run=false.")

    run_id = _make_api_run_id()
    limit = _api_run_limit(request)
    input_path = _source_url_agent_input_path(request)
    selected_models = _selected_models(request.selected_models)
    source_name = request.source.strip().lower()
    try:
        sources = load_source_registry().selected(source_name)
        with session_scope() as session:
            products = _products_for_request(
                session,
                request=request,
                limit=limit,
                input_path=input_path,
                selected_models=selected_models,
            )
            row = _create_queued_discovery_run(
                session,
                run_id=run_id,
                request=request,
                source_name=source_name,
                input_path=input_path,
                selected_count=len(products),
                task_count=len(products) * len(sources),
                selected_models=selected_models,
            )
            _create_queued_discovery_tasks(session, run_id=run_id, products=products, sources=sources)
            payload = _discovery_run_to_dict(row, session=session, include_tasks=True)
    except (FileNotFoundError, SourceUrlAgentInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL Agent run enqueue failed: {_safe_db_error(exc)}") from exc

    background_tasks.add_task(_run_enqueued_source_url_agent, run_id, request)
    return payload


def _run_enqueued_source_url_agent(run_id: str, request: SourceUrlAgentRunRequest) -> None:
    _mark_discovery_run_running(run_id)
    limit = _api_run_limit(request)
    max_products_per_batch = request.max_products_per_batch or DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    input_path = _source_url_agent_input_path(request)
    selected_models = _selected_models(request.selected_models)
    options = SourceUrlAgentOptions(
        mode=request.mode,
        run_id=run_id,
        source=request.source.strip().lower(),
        input_path=input_path,
        limit=limit,
        offset=request.offset,
        catalog_product_id=request.catalog_product_id,
        model=_optional_text(request.model),
        selected_models=selected_models,
        missing_only=bool(request.missing_only),
        active_only=bool(request.active_only),
        dry_run=bool(request.dry_run),
        apply_high_confidence=bool(request.apply_high_confidence),
        max_products_per_batch=max_products_per_batch,
        max_searches_per_product_source=request.max_searches_per_product_source,
        rate_limit_seconds=request.rate_limit_seconds,
        headed=bool(request.headed),
        no_browser_cache=bool(request.no_browser_cache),
        progress_callback=lambda event, product, source, candidates, error: _record_discovery_task_progress(
            run_id,
            event=event,
            product=product,
            source=source,
            candidates=candidates,
            error_message=error,
        ),
    )
    try:
        with session_scope() as session:
            products = _products_for_request(
                session,
                request=request,
                limit=limit,
                input_path=input_path,
                selected_models=selected_models,
            )
            run_source_url_agent(
                products=products,
                options=options,
                session=session,
                resolver=SOURCE_URL_AGENT_API_RESOLVER,
            )
    except Exception as exc:
        _mark_discovery_run_failed(run_id, str(exc).strip() or exc.__class__.__name__)


def _products_for_request(
    session: Session,
    *,
    request: SourceUrlAgentRunRequest,
    limit: int,
    input_path: Path | None,
    selected_models: list[str],
) -> list[AgentProduct]:
    if request.mode == "csv":
        return read_products_from_csv(
            input_path or Path(),
            catalog_source=DEFAULT_CATALOG_SOURCE,
            active_only=request.active_only,
            limit=limit,
            offset=request.offset,
            model=request.model,
        )
    return read_products_from_catalog(
        session,
        catalog_source=DEFAULT_CATALOG_SOURCE,
        active_only=request.active_only,
        limit=limit,
        offset=request.offset,
        catalog_product_id=request.catalog_product_id,
        model=request.model,
        selected_models=selected_models,
    )


def _create_queued_discovery_run(
    session: Session,
    *,
    run_id: str,
    request: SourceUrlAgentRunRequest,
    source_name: str,
    input_path: Path | None,
    selected_count: int,
    task_count: int,
    selected_models: list[str],
) -> SourceUrlDiscoveryRun:
    timestamp = _now()
    row = SourceUrlDiscoveryRun(
        run_id=run_id,
        source_name=source_name,
        mode=request.mode,
        status="queued",
        input_path=str(input_path) if input_path else None,
        filters_json={
            "source": source_name,
            "limit": _api_run_limit(request),
            "offset": request.offset,
            "catalog_product_id": request.catalog_product_id,
            "model": request.model,
            "selected_models": selected_models,
            "missing_only": request.missing_only,
            "active_only": request.active_only,
            "dry_run": request.dry_run,
            "apply_high_confidence": request.apply_high_confidence,
            "max_products_per_batch": request.max_products_per_batch,
            "max_searches_per_product_source": request.max_searches_per_product_source,
            "rate_limit_seconds": request.rate_limit_seconds,
            "headed": request.headed,
            "no_browser_cache": request.no_browser_cache,
            "task_count": task_count,
        },
        selected_count=selected_count,
        candidate_count=0,
        matched_count=0,
        needs_review_count=0,
        not_found_count=0,
        error_count=0,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(row)
    session.flush()
    return row


def _create_queued_discovery_tasks(
    session: Session,
    *,
    run_id: str,
    products: list[AgentProduct],
    sources: list[SourceDefinition],
) -> None:
    timestamp = _now()
    for product in products:
        for source in sources:
            session.add(
                SourceUrlDiscoveryTask(
                    run_id=run_id,
                    catalog_product_id=product.catalog_product_id,
                    model=product.model,
                    source_name=source.source_name,
                    status="queued",
                    candidate_count=0,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
    session.flush()


def _mark_discovery_run_running(run_id: str) -> None:
    with session_scope() as session:
        row = session.execute(select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id == run_id)).scalar_one_or_none()
        if row is None:
            return
        timestamp = _now()
        row.status = "running"
        row.started_at = row.started_at or timestamp
        row.updated_at = timestamp


def _mark_discovery_run_failed(run_id: str, message: str) -> None:
    with session_scope() as session:
        timestamp = _now()
        row = session.execute(select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id == run_id)).scalar_one_or_none()
        if row is not None:
            row.status = "failed"
            row.completed_at = timestamp
            row.updated_at = timestamp
        tasks = session.execute(
            select(SourceUrlDiscoveryTask).where(
                SourceUrlDiscoveryTask.run_id == run_id,
                SourceUrlDiscoveryTask.status.in_(("queued", "running")),
            )
        ).scalars().all()
        for task in tasks:
            task.status = "failed"
            task.error_message = message
            task.completed_at = timestamp
            task.updated_at = timestamp


def _record_discovery_task_progress(
    run_id: str,
    *,
    event: str,
    product: AgentProduct,
    source: SourceDefinition,
    candidates: list[SourceUrlAgentCandidate],
    error_message: str | None,
) -> None:
    with session_scope() as session:
        task = _find_discovery_task(session, run_id=run_id, product=product, source=source)
        if task is None:
            return
        timestamp = _now()
        if event == "started":
            task.status = "running"
            task.started_at = task.started_at or timestamp
        else:
            match_status = _task_match_status(candidates)
            task.match_status = match_status
            task.candidate_count = len(candidates)
            task.error_message = error_message or _task_error_message(candidates)
            task.status = "failed" if match_status == "error" else "completed"
            if match_status == "skipped":
                task.status = "skipped"
            task.completed_at = timestamp
        task.updated_at = timestamp
        _refresh_discovery_run_progress(session, run_id)


def _find_discovery_task(
    session: Session,
    *,
    run_id: str,
    product: AgentProduct,
    source: SourceDefinition,
) -> SourceUrlDiscoveryTask | None:
    statement = select(SourceUrlDiscoveryTask).where(
        SourceUrlDiscoveryTask.run_id == run_id,
        SourceUrlDiscoveryTask.source_name == source.source_name,
    )
    if product.catalog_product_id is not None:
        statement = statement.where(SourceUrlDiscoveryTask.catalog_product_id == product.catalog_product_id)
    else:
        statement = statement.where(SourceUrlDiscoveryTask.model == product.model)
    return session.execute(statement.limit(1)).scalar_one_or_none()


def _task_match_status(candidates: list[SourceUrlAgentCandidate]) -> str | None:
    statuses = [candidate.match_status for candidate in candidates]
    for status in ("error", "needs_review", "matched", "not_found", "skipped"):
        if status in statuses:
            return status
    return statuses[0] if statuses else None


def _task_error_message(candidates: list[SourceUrlAgentCandidate]) -> str | None:
    for candidate in candidates:
        if candidate.match_status == "error" and candidate.notes:
            return candidate.notes
    return None


def _refresh_discovery_run_progress(session: Session, run_id: str) -> None:
    row = session.execute(select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id == run_id)).scalar_one_or_none()
    if row is None or row.status == "completed":
        return
    tasks = session.execute(select(SourceUrlDiscoveryTask).where(SourceUrlDiscoveryTask.run_id == run_id)).scalars().all()
    row.candidate_count = sum(int(task.candidate_count or 0) for task in tasks)
    row.matched_count = sum(1 for task in tasks if task.match_status == "matched")
    row.needs_review_count = sum(1 for task in tasks if task.match_status == "needs_review")
    row.not_found_count = sum(1 for task in tasks if task.match_status == "not_found")
    row.error_count = sum(1 for task in tasks if task.match_status == "error" or task.status == "failed")
    row.updated_at = _now()


def list_source_url_agent_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    _require_source_url_agent_run_database_ready()
    try:
        with session_scope() as session:
            total = int(session.execute(select(func.count(SourceUrlDiscoveryRun.id))).scalar_one())
            statement = (
                select(SourceUrlDiscoveryRun)
                .order_by(SourceUrlDiscoveryRun.created_at.desc(), SourceUrlDiscoveryRun.id.desc())
                .limit(limit)
                .offset(offset)
            )
            items = [_discovery_run_to_dict(row, session=session) for row in session.execute(statement).scalars().all()]
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL Agent run history query failed: {_safe_db_error(exc)}") from exc
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_source_url_agent_run(run_id: str) -> dict[str, Any]:
    _require_source_url_agent_run_database_ready()
    try:
        with session_scope() as session:
            row = session.execute(select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id == run_id)).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=404, detail="Source URL Agent run not found.")
            payload = _discovery_run_to_dict(row, session=session, include_tasks=True)
            payload["artifacts"] = _source_url_agent_artifact_items(run_id)
            return payload
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL Agent run query failed: {_safe_db_error(exc)}") from exc


def get_source_url_agent_run_artifacts(run_id: str) -> dict[str, Any]:
    return _source_url_agent_artifact_listing(run_id)


def list_source_url_agent_candidates(
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
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            filters = _candidate_filters(
                status=status,
                source_name=source_name,
                run_id=run_id,
                model=model,
                catalog_product_id=catalog_product_id,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
            )
            total = int(session.execute(select(func.count(SourceUrlCandidate.id)).where(*filters)).scalar_one())
            statement = (
                select(SourceUrlCandidate)
                .where(*filters)
                .order_by(SourceUrlCandidate.created_at.desc(), SourceUrlCandidate.id.desc())
                .limit(limit)
                .offset(offset)
            )
            items = [_candidate_to_dict(row) for row in session.execute(statement).scalars().all()]
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate query failed: {_safe_db_error(exc)}") from exc
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_source_url_candidate_review_layout(user_key: str | None = None) -> dict[str, Any]:
    _require_catalog_database_ready()
    resolved_user_key = _preference_user_key(user_key)
    try:
        with session_scope() as session:
            preference = _get_view_preference(session, resolved_user_key)
            return _review_layout_payload(resolved_user_key, preference.preferences_json if preference is not None else None)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate layout query failed: {_safe_db_error(exc)}") from exc


def save_source_url_candidate_review_layout(request: SourceUrlCandidateReviewLayoutRequest) -> dict[str, Any]:
    _require_catalog_database_ready()
    resolved_user_key = _preference_user_key(request.user_key)
    preferences = _normalize_review_layout_preferences(request)
    try:
        with session_scope() as session:
            now = _now()
            preference = _get_view_preference(session, resolved_user_key)
            if preference is None:
                preference = UiViewPreference(
                    view_key=SOURCE_URL_CANDIDATE_REVIEW_VIEW_KEY,
                    user_key=resolved_user_key,
                    preferences_json=preferences,
                    created_at=now,
                    updated_at=now,
                )
                session.add(preference)
            else:
                preference.preferences_json = preferences
                preference.updated_at = now
            session.flush()
            return _review_layout_payload(resolved_user_key, preference.preferences_json)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate layout save failed: {_safe_db_error(exc)}") from exc


def reset_source_url_candidate_review_layout(user_key: str | None = None) -> dict[str, Any]:
    _require_catalog_database_ready()
    resolved_user_key = _preference_user_key(user_key)
    try:
        with session_scope() as session:
            preference = _get_view_preference(session, resolved_user_key)
            if preference is not None:
                session.delete(preference)
                session.flush()
            return _review_layout_payload(resolved_user_key, None)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate layout reset failed: {_safe_db_error(exc)}") from exc


def get_source_url_agent_candidate(candidate_id: int) -> dict[str, Any]:
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            candidate = session.get(SourceUrlCandidate, candidate_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail="Source URL candidate not found.")
            payload = _candidate_to_dict(candidate)
            payload["source_url_id"] = _matching_source_url_id(session, candidate)
            payload["review_panel"] = _candidate_review_panel_payload(candidate)
            return payload
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate query failed: {_safe_db_error(exc)}") from exc


def _matching_source_url_id(session: Session, candidate: SourceUrlCandidate) -> int | None:
    if candidate.catalog_product_id is None or not candidate.candidate_url:
        return None
    try:
        normalized = normalize_source_url(candidate.candidate_url)
    except Exception:
        return None
    statement = select(SourceUrl.id).where(
        SourceUrl.catalog_product_id == candidate.catalog_product_id,
        SourceUrl.url_normalized == normalized,
    )
    value = session.execute(statement).scalar_one_or_none()
    return int(value) if value is not None else None


def review_source_url_agent_candidate(candidate_id: int, request: SourceUrlCandidateReviewRequest) -> dict[str, Any]:
    _require_catalog_database_ready()
    try:
        with session_scope() as session:
            candidate = session.get(SourceUrlCandidate, candidate_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail="Source URL candidate not found.")
            source_url_payload = _apply_candidate_review(session, candidate, request)
            payload = _candidate_to_dict(candidate)
            payload["source_url"] = source_url_payload
            return payload
    except HTTPException:
        raise
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL candidate review failed: {_safe_db_error(exc)}") from exc


def _apply_candidate_review(
    session: Session,
    candidate: SourceUrlCandidate,
    request: SourceUrlCandidateReviewRequest,
) -> dict[str, Any] | None:
    decision = request.decision
    reviewed_by = _optional_text(request.reviewed_by) or "operator"
    reviewed_at = _now()
    review_notes = _optional_text(request.review_notes)
    promoted = None

    if decision == "accept":
        candidate.status = "accepted"
        promoted = _promote_candidate_url(
            session,
            candidate,
            reviewed_url=_optional_text(request.reviewed_url) or _optional_text(candidate.candidate_url),
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            review_notes=review_notes,
        )
    elif decision == "replace_url":
        reviewed_url = _optional_text(request.reviewed_url)
        if not reviewed_url:
            raise HTTPException(status_code=400, detail="reviewed_url is required for replace_url.")
        candidate.status = "accepted"
        promoted = _promote_candidate_url(
            session,
            candidate,
            reviewed_url=reviewed_url,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            review_notes=review_notes,
        )
    elif decision == "reject":
        candidate.status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid review decision.")

    candidate.reviewed_by = reviewed_by
    candidate.reviewed_at = reviewed_at
    candidate.notes = _review_notes(candidate.notes, decision=decision, reviewed_by=reviewed_by, reviewed_at=reviewed_at, notes=review_notes)
    candidate.updated_at = reviewed_at
    session.flush()
    return promoted


def _promote_candidate_url(
    session: Session,
    candidate: SourceUrlCandidate,
    *,
    reviewed_url: str | None,
    reviewed_by: str,
    reviewed_at: datetime,
    review_notes: str | None,
) -> dict[str, Any]:
    if candidate.catalog_product_id is None:
        raise ValueError("catalog_product_id is required to promote a source URL.")
    if not reviewed_url:
        raise ValueError("candidate_url is required to promote a source URL.")
    notes = _promotion_notes(candidate, reviewed_by=reviewed_by, reviewed_at=reviewed_at, review_notes=review_notes)
    upsert = create_or_update_imported_source_url(
        session,
        catalog_product_id=int(candidate.catalog_product_id),
        url=reviewed_url,
        source_name=candidate.source_name,
        url_type="discovered",
        trust_level="manual",
        status="active",
        last_seen_at=reviewed_at,
        last_success_at=reviewed_at,
        notes=notes,
        apply=True,
    )
    return {
        "action": upsert.action,
        "source_url_id": upsert.source_url_id,
        "changed_fields": list(upsert.changed_fields),
        "item": source_url_to_dict(upsert.row) if upsert.row is not None else None,
    }


def _candidate_filters(
    *,
    status: str | None,
    source_name: str | None,
    run_id: str | None,
    model: str | None,
    catalog_product_id: str | None,
    min_confidence: str | None,
    max_confidence: str | None,
) -> list[Any]:
    filters: list[Any] = []
    status_text = _optional_text(status)
    if status_text and status_text.casefold() != "all":
        filters.append(SourceUrlCandidate.status == status_text)
    source_text = _optional_text(source_name)
    if source_text:
        filters.append(SourceUrlCandidate.source_name.ilike(f"%{_like_value(source_text)}%"))
    run_id_text = _optional_text(run_id)
    if run_id_text:
        filters.append(SourceUrlCandidate.run_id == run_id_text)
    model_text = _optional_text(model)
    if model_text:
        filters.append(SourceUrlCandidate.model.ilike(f"%{_like_value(model_text)}%"))
    product_id_text = _optional_text(catalog_product_id)
    if product_id_text:
        try:
            filters.append(SourceUrlCandidate.catalog_product_id == int(product_id_text))
        except ValueError:
            raise HTTPException(status_code=400, detail="catalog_product_id must be an integer.") from None
    min_value = _optional_decimal(min_confidence, "min_confidence")
    if min_value is not None:
        filters.append(SourceUrlCandidate.confidence_score >= min_value)
    max_value = _optional_decimal(max_confidence, "max_confidence")
    if max_value is not None:
        filters.append(SourceUrlCandidate.confidence_score <= max_value)
    return filters


def _require_source_url_agent_run_database_ready() -> None:
    readiness = collect_catalog_database_readiness()
    dialect = str(readiness.get("dialect") or "").lower()
    if bool(readiness.get("ready_for_catalog", False)) and dialect == "postgresql":
        return
    detail = catalog_database_unavailable_detail(readiness)
    detail.update(
        {
            "message": "PostgreSQL is required for Source URL Agent runs.",
            "code": "source_url_agent_database_required",
            "dialect": dialect or None,
            "ready_for_source_url_agent_runs": False,
        }
    )
    raise HTTPException(status_code=503, detail=detail)


def _validate_source_choice(value: str) -> None:
    source = value.strip().lower()
    if source not in SOURCE_CHOICES:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(SOURCE_CHOICES)}.")
    try:
        load_source_registry().selected(source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _api_run_limit(request: SourceUrlAgentRunRequest) -> int:
    limit = request.limit if request.limit is not None else DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    max_batch = request.max_products_per_batch or DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    return min(int(limit), int(max_batch), MAX_API_SOURCE_URL_AGENT_LIMIT)


def _selected_models(values: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        selected.append(text)
        seen.add(text)
    return selected


def _source_url_agent_input_path(request: SourceUrlAgentRunRequest) -> Path | None:
    if request.mode != "csv":
        return None
    raw_path = _optional_text(request.input_path)
    if raw_path is None:
        raise HTTPException(status_code=400, detail="input_path is required for csv mode.")
    path = Path(raw_path)
    if _contains_parent_reference(path):
        raise HTTPException(status_code=400, detail="input_path must not contain path traversal.")
    resolved = path.expanduser().resolve(strict=False)
    cwd = Path.cwd().resolve(strict=False)
    if not _same_or_child(resolved, cwd):
        raise HTTPException(status_code=400, detail="input_path must be inside the application working directory.")
    return resolved


def _source_url_agent_result_payload(result: SourceUrlAgentResult) -> dict[str, Any]:
    summary = json_safe_value(result.summary)
    return {
        "run_id": result.run_id,
        "mode": summary.get("mode"),
        "source": summary.get("source"),
        "dry_run": bool(summary.get("dry_run", True)),
        "apply_high_confidence": bool(summary.get("apply_high_confidence", False)),
        "summary": summary,
        "warnings": list(result.warnings),
        "artifacts": _artifact_refs_from_paths(result.artifacts.to_dict()),
    }


def _discovery_run_to_dict(
    row: SourceUrlDiscoveryRun,
    *,
    session: Session | None = None,
    include_tasks: bool = False,
) -> dict[str, Any]:
    task_counts = _discovery_task_counts(session, row.run_id) if session is not None else {}
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
        payload["tasks"] = _discovery_task_items(session, row.run_id)
    return payload


def _discovery_task_counts(session: Session, run_id: str) -> dict[str, int]:
    rows = session.execute(
        select(SourceUrlDiscoveryTask.status, func.count(SourceUrlDiscoveryTask.id))
        .where(SourceUrlDiscoveryTask.run_id == run_id)
        .group_by(SourceUrlDiscoveryTask.status)
    ).all()
    return {str(status): int(count) for status, count in rows}


def _discovery_task_items(session: Session, run_id: str) -> list[dict[str, Any]]:
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


def _source_url_agent_artifact_listing(run_id: str) -> dict[str, Any]:
    try:
        result = list_run_artifacts("source_url_agent", run_id)
    except ArtifactPathForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Source URL Agent artifact listing failed.") from exc
    return {
        "run_id": result.run_id,
        "run_type": result.run_type,
        "run_dir": _display_path(result.run_dir),
        "items": [item.to_api_dict() for item in result.items],
    }


def _source_url_agent_artifact_items(run_id: str) -> list[dict[str, Any]]:
    try:
        return _source_url_agent_artifact_listing(run_id)["items"]
    except HTTPException as exc:
        if exc.status_code == 404:
            return []
        raise


def _artifact_refs_from_paths(paths: dict[str, str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key, value in paths.items():
        if key == "run_dir" or not value:
            continue
        payload = artifact_link_payload(Path(value))
        payload["artifact_key"] = key
        refs.append(payload)
    return refs


def _contains_parent_reference(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


def _same_or_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return path == parent


def _display_path(path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(Path.cwd().resolve(strict=False)))
    except ValueError:
        return str(resolved)


def _candidate_to_dict(row: SourceUrlCandidate) -> dict[str, Any]:
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


def _candidate_review_panel_payload(row: SourceUrlCandidate) -> dict[str, Any]:
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
        "review_endpoint": f"/api/vendor-sources/candidates/{row.id}/review",
    }


def _get_view_preference(session: Session, user_key: str) -> UiViewPreference | None:
    statement = select(UiViewPreference).where(
        UiViewPreference.view_key == SOURCE_URL_CANDIDATE_REVIEW_VIEW_KEY,
        UiViewPreference.user_key == user_key,
    )
    return session.execute(statement).scalar_one_or_none()


def _review_layout_payload(user_key: str, preferences: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _merge_review_layout_preferences(preferences)
    return {
        "view_key": SOURCE_URL_CANDIDATE_REVIEW_VIEW_KEY,
        "user_key": user_key,
        "settings_card": {
            "collapsible": True,
            "collapsed": normalized["settings_card"]["collapsed"],
            "sections": ["columns"],
        },
        "columns": normalized["columns"],
        "actions": {
            "table_column_visible": False,
            "replacement": "inline_review_panel",
            "review_endpoint_template": "/api/vendor-sources/candidates/{candidate_id}/review",
        },
        "review_panel": normalized["review_panel"],
    }


def _normalize_review_layout_preferences(request: SourceUrlCandidateReviewLayoutRequest) -> dict[str, Any]:
    column_overrides: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for column in request.columns or []:
        key = _optional_text(column.key)
        if not key:
            raise HTTPException(status_code=400, detail="Column key is required.")
        if key not in DEFAULT_REVIEW_COLUMN_KEYS:
            raise HTTPException(status_code=400, detail=f"Unknown Source URL Candidate Review column: {key}.")
        if key in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate Source URL Candidate Review column: {key}.")
        seen.add(key)
        override: dict[str, Any] = {"key": key}
        if column.visible is not None:
            override["visible"] = bool(column.visible)
        if column.order is not None:
            if column.order < 0:
                raise HTTPException(status_code=400, detail=f"Column order must be greater than or equal to 0: {key}.")
            override["order"] = int(column.order)
        if column.width_px is not None:
            override["width_px"] = _bounded_width(column.width_px, f"Column width out of range for {key}.")
        column_overrides[key] = override

    review_panel_width = request.review_panel_width_px
    if review_panel_width is not None:
        review_panel_width = _bounded_width(review_panel_width, "Review panel width out of range.")

    return {
        "columns": list(column_overrides.values()),
        "settings_card": {"collapsed": True if request.settings_card_collapsed is None else bool(request.settings_card_collapsed)},
        "review_panel": {
            "mode": "inline_row",
            "open_on": "row_single_click",
            "width_px": review_panel_width or 420,
        },
    }


def _merge_review_layout_preferences(preferences: dict[str, Any] | None) -> dict[str, Any]:
    columns = deepcopy(DEFAULT_REVIEW_COLUMNS)
    by_key = {column["key"]: column for column in columns}
    if isinstance(preferences, dict):
        for override in preferences.get("columns") or []:
            if not isinstance(override, dict):
                continue
            key = override.get("key")
            if key not in by_key:
                continue
            target = by_key[key]
            if isinstance(override.get("visible"), bool):
                target["visible"] = override["visible"]
            if isinstance(override.get("order"), int) and override["order"] >= 0:
                target["order"] = override["order"]
            if isinstance(override.get("width_px"), int):
                target["width_px"] = _clamp_width(override["width_px"])
    columns.sort(key=lambda item: (int(item["order"]), str(item["key"])))

    stored_settings = preferences.get("settings_card") if isinstance(preferences, dict) else None
    stored_review_panel = preferences.get("review_panel") if isinstance(preferences, dict) else None
    collapsed = True
    if isinstance(stored_settings, dict) and isinstance(stored_settings.get("collapsed"), bool):
        collapsed = stored_settings["collapsed"]
    width_px = 420
    if isinstance(stored_review_panel, dict) and isinstance(stored_review_panel.get("width_px"), int):
        width_px = _clamp_width(stored_review_panel["width_px"])

    return {
        "columns": columns,
        "settings_card": {"collapsed": collapsed},
        "review_panel": {
            "mode": "inline_row",
            "open_on": "row_single_click",
            "width_px": width_px,
            "preserve_row_selection": True,
        },
    }


def _preference_user_key(value: str | None) -> str:
    text = _optional_text(value) or DEFAULT_USER_KEY
    if len(text) > 128:
        raise HTTPException(status_code=400, detail="user_key must be 128 characters or fewer.")
    return text


def _bounded_width(value: int, detail: str) -> int:
    if value < MIN_COLUMN_WIDTH_PX or value > MAX_COLUMN_WIDTH_PX:
        raise HTTPException(status_code=400, detail=f"{detail} Expected {MIN_COLUMN_WIDTH_PX}-{MAX_COLUMN_WIDTH_PX}px.")
    return int(value)


def _clamp_width(value: int) -> int:
    return min(MAX_COLUMN_WIDTH_PX, max(MIN_COLUMN_WIDTH_PX, int(value)))


def _promotion_notes(
    candidate: SourceUrlCandidate,
    *,
    reviewed_by: str,
    reviewed_at: datetime,
    review_notes: str | None,
) -> str:
    parts = [
        f"Source URL candidate review accepted candidate_id={candidate.id}",
        f"run_id={candidate.run_id}",
        f"match_method={candidate.match_method}",
        f"confidence={candidate.confidence_score}",
        f"reviewed_by={reviewed_by}",
        f"reviewed_at={reviewed_at.isoformat()}",
    ]
    if review_notes:
        parts.append(f"notes={review_notes}")
    return "; ".join(parts)


def _review_notes(
    current: str | None,
    *,
    decision: str,
    reviewed_by: str,
    reviewed_at: datetime,
    notes: str | None,
) -> str:
    entry = f"Review {decision} by {reviewed_by} at {reviewed_at.isoformat()}"
    if notes:
        entry = f"{entry}: {notes}"
    existing = _optional_text(current)
    return f"{existing}\n{entry}" if existing else entry


def _optional_decimal(value: str | None, field_name: str) -> Decimal | None:
    text = _optional_text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a number.") from None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _like_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _require_catalog_database_ready() -> None:
    require_database_ready_for_catalog()


def _safe_db_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return sanitize_database_error(message) or exc.__class__.__name__


def _make_api_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
