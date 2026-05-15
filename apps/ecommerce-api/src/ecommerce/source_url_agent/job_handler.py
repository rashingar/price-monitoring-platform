"""Durable job execution handler for Source URL Agent runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.source_urls import SourceUrlDiscoveryRun, SourceUrlDiscoveryTask
from ecommerce.db.repositories.common import json_safe_value
from ecommerce.db.repositories.jobs import get_job_by_id
from ecommerce.db.session import session_scope
from ecommerce.jobs.durable import execute_job
from ecommerce.source_url_agent.agent import Resolver, SourceUrlAgentOptions, SourceUrlAgentResult, run_source_url_agent
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate
from ecommerce.source_url_agent.products import AgentProduct, read_products_from_catalog, read_products_from_csv
from ecommerce.source_url_agent.progress import SourceUrlAgentProgressReporter
from ecommerce.source_url_agent.sources import SourceDefinition

DEFAULT_API_MAX_PRODUCTS_PER_BATCH = 25
MAX_API_SOURCE_URL_AGENT_LIMIT = 500

# Test hook for worker/background orchestration without browser-backed discovery.
SOURCE_URL_AGENT_JOB_RESOLVER: Resolver | None = None


@dataclass(frozen=True)
class SourceUrlAgentJobRequest:
    source: str = "all"
    mode: str = "catalog"
    input_path: str | None = None
    limit: int | None = None
    offset: int = 0
    catalog_product_id: int | None = None
    model: str | None = None
    selected_models: list[str] = field(default_factory=list)
    missing_only: bool = False
    active_only: bool = True
    dry_run: bool = True
    apply_high_confidence: bool = False
    max_products_per_batch: int | None = None
    max_searches_per_product_source: int | None = None
    rate_limit_seconds: float | None = None
    headed: bool = False
    no_browser_cache: bool = False


def execute_source_url_agent_job(
    job_id: str,
    payload: dict[str, Any] | None = None,
    *,
    claimed: bool = False,
    resolver: Resolver | None = None,
) -> Any:
    """Execute a queued Source URL Agent job through durable job semantics."""

    with session_scope() as session:
        if payload is not None:
            job = get_job_by_id(session, job_id)
            if job is None:
                return None
            job.payload_json = payload
            session.flush()
        return execute_job(
            session,
            job_id,
            lambda job_payload: run_source_url_agent_job(job_id, job_payload, resolver=resolver),
            reraise=False,
            claimed=claimed,
        )


def run_source_url_agent_job(
    job_id: str,
    payload: dict[str, Any] | None,
    *,
    resolver: Resolver | None = None,
) -> dict[str, Any]:
    """Run Source URL Agent discovery for an already-claimed durable job."""

    job_payload = payload if isinstance(payload, dict) else {}
    request = source_url_agent_job_request_from_payload(job_payload)
    run_id = str(job_payload.get("run_id") or job_id)
    if not run_id:
        run_id = job_id

    _mark_discovery_run_running(run_id)
    limit = _job_run_limit(request, payload=job_payload)
    input_path = _job_input_path(request, payload=job_payload)
    selected_models = _selected_models(request.selected_models)
    max_products_per_batch = request.max_products_per_batch or DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    selected_resolver = resolver or SOURCE_URL_AGENT_JOB_RESOLVER

    try:
        with SourceUrlAgentProgressReporter(job_id) as progress_reporter:
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
                progress_callback=lambda event, product, source, candidates, error: record_discovery_task_progress(
                    run_id,
                    event=event,
                    product=product,
                    source=source,
                    candidates=candidates,
                    error_message=error,
                ),
            )
            with session_scope() as session:
                products = products_for_source_url_agent_request(
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
                    resolver=selected_resolver,
                )
            final_progress = progress_reporter.current_payload()
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        mark_discovery_run_failed(run_id, message)
        raise

    return source_url_agent_job_result_payload(result, progress=final_progress)


def source_url_agent_job_request_from_payload(payload: dict[str, Any] | None) -> SourceUrlAgentJobRequest:
    job_payload = payload if isinstance(payload, dict) else {}
    data = job_payload.get("request")
    if not isinstance(data, dict):
        data = job_payload
    return SourceUrlAgentJobRequest(
        source=str(data.get("source") or job_payload.get("source") or "all").strip().lower(),
        mode=str(data.get("mode") or job_payload.get("mode") or "catalog"),
        input_path=_optional_text(data.get("input_path")),
        limit=_optional_int(data.get("limit")),
        offset=max(0, _optional_int(data.get("offset")) or 0),
        catalog_product_id=_optional_int(data.get("catalog_product_id")),
        model=_optional_text(data.get("model")),
        selected_models=_selected_models(data.get("selected_models") if isinstance(data.get("selected_models"), list) else []),
        missing_only=_optional_bool(data.get("missing_only"), default=False),
        active_only=_optional_bool(data.get("active_only"), default=True),
        dry_run=_optional_bool(data.get("dry_run"), default=True),
        apply_high_confidence=_optional_bool(data.get("apply_high_confidence"), default=False),
        max_products_per_batch=_optional_int(data.get("max_products_per_batch")),
        max_searches_per_product_source=_optional_int(data.get("max_searches_per_product_source")),
        rate_limit_seconds=_optional_float(data.get("rate_limit_seconds")),
        headed=_optional_bool(data.get("headed"), default=False),
        no_browser_cache=_optional_bool(data.get("no_browser_cache"), default=False),
    )


def products_for_source_url_agent_request(
    session: Session,
    *,
    request: Any,
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


def source_url_agent_job_payload(
    request: Any,
    *,
    run_id: str,
    source_name: str,
    limit: int,
    input_path: Path | None,
    selected_models: list[str],
) -> dict[str, Any]:
    request_payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    return {
        "run_id": run_id,
        "source": source_name,
        "mode": request.mode,
        "request": json_safe_value(request_payload),
        "effective_limit": limit,
        "effective_input_path": str(input_path) if input_path else None,
        "selected_models": list(selected_models),
    }


def source_url_agent_job_result_payload(
    result: SourceUrlAgentResult,
    *,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": result.run_id,
        "summary": json_safe_value(result.summary),
        "warnings": list(result.warnings),
        "artifacts": result.artifacts.to_dict(),
    }
    if progress is not None:
        payload["progress"] = progress
    return payload


def mark_discovery_run_failed(run_id: str, message: str) -> None:
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


def record_discovery_task_progress(
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


def _mark_discovery_run_running(run_id: str) -> None:
    with session_scope() as session:
        row = session.execute(select(SourceUrlDiscoveryRun).where(SourceUrlDiscoveryRun.run_id == run_id)).scalar_one_or_none()
        if row is None:
            return
        timestamp = _now()
        row.status = "running"
        row.started_at = row.started_at or timestamp
        row.updated_at = timestamp


def _job_run_limit(request: SourceUrlAgentJobRequest, *, payload: dict[str, Any]) -> int:
    effective_limit = _optional_int(payload.get("effective_limit"))
    if effective_limit is not None:
        return min(effective_limit, MAX_API_SOURCE_URL_AGENT_LIMIT)
    limit = request.limit if request.limit is not None else DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    max_batch = request.max_products_per_batch or DEFAULT_API_MAX_PRODUCTS_PER_BATCH
    return min(int(limit), int(max_batch), MAX_API_SOURCE_URL_AGENT_LIMIT)


def _job_input_path(request: SourceUrlAgentJobRequest, *, payload: dict[str, Any]) -> Path | None:
    value = _optional_text(payload.get("effective_input_path")) or request.input_path
    if request.mode != "csv" or value is None:
        return None
    return Path(value)


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


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _now() -> datetime:
    return datetime.now(timezone.utc)
