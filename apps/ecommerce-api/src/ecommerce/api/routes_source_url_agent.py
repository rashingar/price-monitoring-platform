"""Source URL Agent candidate review API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ecommerce.artifacts import ArtifactPathError, ArtifactPathForbiddenError, artifact_link_payload, list_run_artifacts
from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.config import sanitize_database_error
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun, SourceUrlDiscoveryTask
from ecommerce.db.policy import catalog_database_unavailable_detail, collect_catalog_database_readiness, require_database_ready_for_catalog
from ecommerce.db.repositories.common import json_safe_value
from ecommerce.db.repositories.jobs import create_queued_job, get_job_by_id, mark_failed, mark_running, mark_succeeded
from ecommerce.db.session import session_scope
from ecommerce.db.repositories.source_urls import create_or_update_imported_source_url, source_url_to_dict
from ecommerce.source_urls import normalize_source_url
from ecommerce.source_url_agent.agent import Resolver, SourceUrlAgentOptions, SourceUrlAgentResult, run_source_url_agent
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate
from ecommerce.source_url_agent.products import AgentProduct, SourceUrlAgentInputError, read_products_from_catalog, read_products_from_csv
from ecommerce.source_url_agent.progress import SOURCE_URL_AGENT_JOB_TYPE, SourceUrlAgentProgressReporter
from ecommerce.source_url_agent.sources import SOURCE_CHOICES, SourceDefinition, load_source_registry

ReviewDecision = Literal["accept", "reject", "replace_url"]
SourceUrlAgentRunMode = Literal["catalog", "csv"]
DEFAULT_API_MAX_PRODUCTS_PER_BATCH = 25
MAX_API_SOURCE_URL_AGENT_LIMIT = 500
router = APIRouter(prefix="/api/source-url-agent", tags=["source-url-agent"])

# Test hook for exercising the API orchestration with the real service layer
# without launching browser-backed discovery.
SOURCE_URL_AGENT_API_RESOLVER: Resolver | None = None

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


@router.get("/sources")
def list_source_url_agent_sources() -> dict[str, Any]:
    return {"items": [_source_definition_to_dict(source) for source in load_source_registry().sources.values()]}


@router.post("/runs/sync")
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


@router.post("/runs")
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
            create_queued_job(
                session,
                job_id=run_id,
                job_type=SOURCE_URL_AGENT_JOB_TYPE,
                payload=_source_url_agent_job_payload(request, run_id=run_id, source_name=source_name),
            )
            payload = _discovery_run_to_dict(row, session=session, include_tasks=True)
    except (FileNotFoundError, SourceUrlAgentInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Source URL Agent run enqueue failed: {_safe_db_error(exc)}") from exc

    background_tasks.add_task(_run_enqueued_source_url_agent, run_id, request)
    return payload


def _run_enqueued_source_url_agent(run_id: str, request: SourceUrlAgentRunRequest) -> None:
    _mark_discovery_run_running(run_id)
    _mark_source_url_agent_job_running(run_id)
    limit = _api_run_limit(request)
    max_products_per_batch = request.max_products_per_batch or DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    input_path = _source_url_agent_input_path(request)
    selected_models = _selected_models(request.selected_models)
    try:
        with SourceUrlAgentProgressReporter(run_id) as progress_reporter:
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
                progress_reporter=progress_reporter,
                progress_callback=lambda event, product, source, candidates, error: _record_discovery_task_progress(
                    run_id,
                    event=event,
                    product=product,
                    source=source,
                    candidates=candidates,
                    error_message=error,
                ),
            )
            with session_scope() as session:
                products = _products_for_request(
                    session,
                    request=request,
                    limit=limit,
                    input_path=input_path,
                    selected_models=selected_models,
                )
                result = run_source_url_agent(
                    products=products,
                    options=options,
                    session=session,
                    resolver=SOURCE_URL_AGENT_API_RESOLVER,
                )
            final_progress = progress_reporter.current_payload()
        _mark_source_url_agent_job_succeeded(run_id, result, progress=final_progress)
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        _mark_discovery_run_failed(run_id, message)
        _mark_source_url_agent_job_failed(run_id, message)


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


def _mark_source_url_agent_job_running(run_id: str) -> None:
    try:
        with session_scope() as session:
            job = get_job_by_id(session, run_id)
            if job is None:
                return
            if job.status == "queued":
                mark_running(session, run_id)
    except Exception:
        return


def _mark_source_url_agent_job_succeeded(
    run_id: str,
    result: SourceUrlAgentResult,
    *,
    progress: dict[str, Any] | None = None,
) -> None:
    try:
        with session_scope() as session:
            job = get_job_by_id(session, run_id)
            if job is None:
                return
            existing_result = job.result_json if isinstance(job.result_json, dict) else {}
            payload: dict[str, Any] = {
                "run_id": result.run_id,
                "summary": json_safe_value(result.summary),
                "warnings": list(result.warnings),
                "artifacts": result.artifacts.to_dict(),
            }
            if progress is not None:
                payload["progress"] = progress
            elif "progress" in existing_result:
                payload["progress"] = existing_result["progress"]
            mark_succeeded(session, run_id, result=payload)
    except Exception:
        return


def _mark_source_url_agent_job_failed(run_id: str, message: str) -> None:
    try:
        with session_scope() as session:
            if get_job_by_id(session, run_id) is not None:
                mark_failed(session, run_id, error_message=message)
    except Exception:
        return


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


def _source_url_agent_job_payload(
    request: SourceUrlAgentRunRequest,
    *,
    run_id: str,
    source_name: str,
) -> dict[str, Any]:
    request_payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    return {
        "run_id": run_id,
        "source": source_name,
        "mode": request.mode,
        "request": json_safe_value(request_payload),
    }


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


@router.get("/runs")
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


@router.get("/runs/{run_id}")
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


@router.get("/runs/{run_id}/artifacts")
def get_source_url_agent_run_artifacts(run_id: str) -> dict[str, Any]:
    return _source_url_agent_artifact_listing(run_id)


@router.get("/candidates")
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


@router.get("/candidates/{candidate_id}")
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


@router.patch("/candidates/{candidate_id}/review")
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


def _source_definition_to_dict(source: SourceDefinition) -> dict[str, Any]:
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
        "review_endpoint": f"/api/source-url-agent/candidates/{row.id}/review",
    }


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
