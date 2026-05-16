"""Queued run setup service for Source URL Agent durable jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import SourceUrlDiscoveryRun, SourceUrlDiscoveryTask
from ecommerce.db.repositories.jobs import create_queued_job
from ecommerce.source_url_agent.job_handler import (
    products_for_source_url_agent_request,
    source_url_agent_job_payload,
)
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.progress import SOURCE_URL_AGENT_JOB_TYPE
from ecommerce.source_url_agent.sources import SourceDefinition, load_source_registry


@dataclass(frozen=True)
class SourceUrlAgentEnqueueCommand:
    source_name: str
    mode: str
    input_path: Path | None
    limit: int
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
    request_payload: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None

    @property
    def source(self) -> str:
        return self.source_name

    def model_dump(self) -> dict[str, Any]:
        return dict(self.request_payload)


@dataclass(frozen=True)
class SourceUrlAgentEnqueueResult:
    run_id: str
    run: SourceUrlDiscoveryRun
    selected_count: int
    task_count: int


def enqueue_source_url_agent_run_setup(
    session: Session,
    command: SourceUrlAgentEnqueueCommand,
) -> SourceUrlAgentEnqueueResult:
    """Create queued discovery state and the durable Source URL Agent job."""

    run_id = command.run_id or make_source_url_agent_run_id()
    source_name = command.source_name.strip().lower()
    sources = load_source_registry().selected(source_name)
    products = products_for_source_url_agent_request(
        session,
        request=command,
        limit=command.limit,
        input_path=command.input_path,
        selected_models=command.selected_models,
    )
    task_count = len(products) * len(sources)
    row = create_queued_discovery_run(
        session,
        run_id=run_id,
        command=command,
        source_name=source_name,
        selected_count=len(products),
        task_count=task_count,
    )
    create_queued_discovery_tasks(session, run_id=run_id, products=products, sources=sources)
    create_queued_job(
        session,
        job_id=run_id,
        job_type=SOURCE_URL_AGENT_JOB_TYPE,
        payload=source_url_agent_job_payload(
            command,
            run_id=run_id,
            source_name=source_name,
            limit=command.limit,
            input_path=command.input_path,
            selected_models=command.selected_models,
        ),
    )
    return SourceUrlAgentEnqueueResult(
        run_id=run_id,
        run=row,
        selected_count=len(products),
        task_count=task_count,
    )


def create_queued_discovery_run(
    session: Session,
    *,
    run_id: str,
    command: SourceUrlAgentEnqueueCommand,
    source_name: str,
    selected_count: int,
    task_count: int,
) -> SourceUrlDiscoveryRun:
    timestamp = _now()
    row = SourceUrlDiscoveryRun(
        run_id=run_id,
        source_name=source_name,
        mode=command.mode,
        status="queued",
        input_path=str(command.input_path) if command.input_path else None,
        filters_json={
            "source": source_name,
            "limit": command.limit,
            "offset": command.offset,
            "catalog_product_id": command.catalog_product_id,
            "model": command.model,
            "selected_models": list(command.selected_models),
            "missing_only": command.missing_only,
            "active_only": command.active_only,
            "dry_run": command.dry_run,
            "apply_high_confidence": command.apply_high_confidence,
            "max_products_per_batch": command.max_products_per_batch,
            "max_searches_per_product_source": command.max_searches_per_product_source,
            "rate_limit_seconds": command.rate_limit_seconds,
            "headed": command.headed,
            "no_browser_cache": command.no_browser_cache,
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


def create_queued_discovery_tasks(
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


def make_source_url_agent_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
