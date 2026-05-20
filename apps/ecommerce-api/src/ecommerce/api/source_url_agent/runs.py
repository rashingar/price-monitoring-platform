"""Run orchestration routes for the Source URL Agent API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.repositories.source_urls import (
    get_source_url_discovery_run,
    list_source_url_discovery_run_page,
)
from ecommerce.db.session import session_scope
from ecommerce.jobs.execution_policy import api_execute_durable_jobs_inline_enabled
from ecommerce.source_url_agent.enqueue_service import (
    SourceUrlAgentEnqueueCommand,
    enqueue_source_url_agent_run_setup,
)
from ecommerce.source_url_agent.job_handler import execute_source_url_agent_job
from ecommerce.source_url_agent.options import SourceUrlAgentOptions
from ecommerce.source_url_agent.products import (
    SourceUrlAgentInputError,
    read_products_from_catalog,
    read_products_from_csv,
)
from ecommerce.source_url_agent.runner import run_source_url_agent
from ecommerce.source_url_agent.sources import load_source_registry

from .artifacts import (
    source_url_agent_artifact_items,
    source_url_agent_artifact_listing,
)
from .errors import safe_db_error
from .schemas import SourceUrlAgentRunRequest
from .serializers import (
    discovery_run_to_dict,
    source_definition_to_dict,
    source_url_agent_result_payload,
)
from .state import get_api_resolver
from .validation import (
    api_run_limit,
    default_api_max_products_per_batch,
    optional_text,
    require_source_url_agent_run_database_ready,
    selected_models,
    source_url_agent_input_path,
    validate_source_choice,
)

router = APIRouter()


@router.get("/sources")
def list_source_url_agent_sources() -> dict[str, Any]:
    return {
        "items": [
            source_definition_to_dict(source)
            for source in load_source_registry().sources.values()
        ]
    }


@router.post("/runs/sync")
def launch_source_url_agent_run(request: SourceUrlAgentRunRequest) -> dict[str, Any]:
    require_source_url_agent_run_database_ready()
    validate_source_choice(request.source)
    if request.apply_high_confidence and request.dry_run:
        raise HTTPException(
            status_code=400, detail="apply_high_confidence requires dry_run=false."
        )

    limit = api_run_limit(request)
    max_products_per_batch = (
        request.max_products_per_batch or default_api_max_products_per_batch()
    )
    input_path = source_url_agent_input_path(request)
    request_selected_models = selected_models(request.selected_models)
    options = SourceUrlAgentOptions(
        mode=request.mode,
        source=request.source.strip().lower(),
        input_path=input_path,
        limit=limit,
        offset=request.offset,
        catalog_product_id=request.catalog_product_id,
        model=optional_text(request.model),
        selected_models=request_selected_models,
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
                    selected_models=request_selected_models,
                )
            result = run_source_url_agent(
                products=products,
                options=options,
                session=session,
                resolver=get_api_resolver(),
            )
    except HTTPException:
        raise
    except (FileNotFoundError, SourceUrlAgentInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500, detail=f"Source URL Agent run failed: {safe_db_error(exc)}"
        ) from exc
    return source_url_agent_result_payload(result)


@router.post("/runs")
def enqueue_source_url_agent_run(
    request: SourceUrlAgentRunRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    require_source_url_agent_run_database_ready()
    validate_source_choice(request.source)
    if request.apply_high_confidence and request.dry_run:
        raise HTTPException(
            status_code=400, detail="apply_high_confidence requires dry_run=false."
        )

    limit = api_run_limit(request)
    input_path = source_url_agent_input_path(request)
    request_selected_models = selected_models(request.selected_models)
    source_name = request.source.strip().lower()
    try:
        with session_scope() as session:
            result = enqueue_source_url_agent_run_setup(
                session,
                SourceUrlAgentEnqueueCommand(
                    source_name=source_name,
                    mode=request.mode,
                    input_path=input_path,
                    limit=limit,
                    offset=request.offset,
                    catalog_product_id=request.catalog_product_id,
                    model=optional_text(request.model),
                    selected_models=request_selected_models,
                    missing_only=bool(request.missing_only),
                    active_only=bool(request.active_only),
                    dry_run=bool(request.dry_run),
                    apply_high_confidence=bool(request.apply_high_confidence),
                    max_products_per_batch=request.max_products_per_batch,
                    max_searches_per_product_source=request.max_searches_per_product_source,
                    rate_limit_seconds=request.rate_limit_seconds,
                    headed=bool(request.headed),
                    no_browser_cache=bool(request.no_browser_cache),
                    request_payload=_request_payload(request),
                ),
            )
            payload = discovery_run_to_dict(
                result.run, session=session, include_tasks=True
            )
    except (FileNotFoundError, SourceUrlAgentInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Source URL Agent run enqueue failed: {safe_db_error(exc)}",
        ) from exc

    if api_execute_durable_jobs_inline_enabled():
        background_tasks.add_task(
            execute_source_url_agent_job, payload["run_id"], resolver=get_api_resolver()
        )
    return payload


@router.get("/runs")
def list_source_url_agent_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    require_source_url_agent_run_database_ready()
    try:
        with session_scope() as session:
            page = list_source_url_discovery_run_page(
                session, limit=limit, offset=offset
            )
            items = [discovery_run_to_dict(row, session=session) for row in page.items]
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Source URL Agent run history query failed: {safe_db_error(exc)}",
        ) from exc
    return {
        "items": items,
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/runs/{run_id}")
def get_source_url_agent_run(run_id: str) -> dict[str, Any]:
    require_source_url_agent_run_database_ready()
    try:
        with session_scope() as session:
            row = get_source_url_discovery_run(session, run_id)
            if row is None:
                raise HTTPException(
                    status_code=404, detail="Source URL Agent run not found."
                )
            payload = discovery_run_to_dict(row, session=session, include_tasks=True)
            payload["artifacts"] = source_url_agent_artifact_items(run_id)
            return payload
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Source URL Agent run query failed: {safe_db_error(exc)}",
        ) from exc


@router.get("/runs/{run_id}/artifacts")
def get_source_url_agent_run_artifacts(run_id: str) -> dict[str, Any]:
    return source_url_agent_artifact_listing(run_id)


def _request_payload(request: SourceUrlAgentRunRequest) -> dict[str, Any]:
    return request.model_dump() if hasattr(request, "model_dump") else request.dict()
