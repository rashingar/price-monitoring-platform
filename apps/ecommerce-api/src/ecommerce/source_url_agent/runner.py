"""Top-level orchestration for Source URL Agent runs."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ecommerce.source_url_agent.artifacts import build_summary_payload, write_run_artifacts
from ecommerce.source_url_agent.candidate_results import candidates_for_candidate_storage
from ecommerce.source_url_agent.candidates import MIN_CANDIDATE_CONFIDENCE_TO_KEEP, SourceUrlAgentCandidate
from ecommerce.source_url_agent.options import Resolver, SourceUrlAgentOptions, SourceUrlAgentResult
from ecommerce.source_url_agent.persistence import (
    apply_high_confidence_source_urls,
    persist_candidate_rows,
    persist_discovery_run,
)
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.sources import SourceDefinition, SourceRegistry, load_source_registry
from ecommerce.source_url_agent.task_execution import (
    browser_unavailable_candidates,
    progress_details,
    run_with_browser,
    run_with_resolver,
)


def run_source_url_agent(
    *,
    products: list[AgentProduct],
    options: SourceUrlAgentOptions,
    registry: SourceRegistry | None = None,
    session: Session | None = None,
    resolver: Resolver | None = None,
) -> SourceUrlAgentResult:
    progress = options.progress_reporter
    if progress is not None:
        progress.report(
            "product_selection_started",
            details={
                "product_count": len(products),
                "source": options.source,
                "mode": options.mode,
                "dry_run": options.dry_run,
                "apply_high_confidence": options.apply_high_confidence,
            },
        )
    registry = registry or load_source_registry()
    sources = registry.selected(options.source)
    run_id = options.run_id or _make_run_id()
    started_at = _now()
    warnings: list[str] = []
    selected_products = _limited_products(products, options)
    if progress is not None:
        progress.report(
            "product_selection_completed",
            details={
                "run_id": run_id,
                "product_count": len(selected_products),
                "input_product_count": len(products),
                "source": options.source,
            },
        )
        progress.report(
            "source_registry_loaded",
            details={
                "run_id": run_id,
                "source_count": len(sources),
                "sources": [source.source_name for source in sources],
                "product_source_task_count": len(selected_products) * len(sources),
            },
        )

    if options.missing_only and session is None:
        warning = "missing_only was requested but the database is unavailable; missing coverage cannot be checked."
        warnings.append(warning)
        if progress is not None:
            progress.add_warning(warning, {"run_id": run_id})

    if progress is not None:
        progress.report(
            "discovery_started",
            details=progress_details(
                selected_products,
                sources,
                [],
                completed_product_source_task_count=0,
                applied_high_confidence_url_count=0,
                persisted_candidate_count=0,
            ),
        )
    if resolver is not None:
        candidates = run_with_resolver(
            run_id=run_id,
            products=selected_products,
            sources=sources,
            options=options,
            session=session,
            resolver=resolver,
        )
    else:
        candidates = _run_browser_tasks(
            run_id=run_id,
            products=selected_products,
            sources=sources,
            options=options,
            session=session,
            warnings=warnings,
        )

    apply_source_urls = bool(options.apply_high_confidence and not options.dry_run and session is not None)
    write_results = []
    if apply_source_urls:
        if progress is not None:
            progress.report(
                "high_confidence_apply_started",
                details=progress_details(
                    selected_products,
                    sources,
                    candidates,
                    completed_product_source_task_count=len(selected_products) * len(sources),
                    applied_high_confidence_url_count=0,
                    persisted_candidate_count=0,
                ),
            )
        write_results = apply_high_confidence_source_urls(session, candidates, apply=True)
        accepted_indexes = {item.candidate_index for item in write_results if item.action in {"created", "updated", "duplicate"}}
        candidates = [
            replace(candidate, status="accepted") if index in accepted_indexes else candidate
            for index, candidate in enumerate(candidates)
        ]
        skipped_reasons = [item.reason for item in write_results if item.reason]
        if skipped_reasons:
            warnings.extend(f"source_url_write_skipped: {reason}" for reason in skipped_reasons)
            if progress is not None:
                for reason in skipped_reasons:
                    progress.add_warning(f"source_url_write_skipped: {reason}", {"run_id": run_id})
        if progress is not None:
            progress.report(
                "high_confidence_apply_completed",
                details=progress_details(
                    selected_products,
                    sources,
                    candidates,
                    completed_product_source_task_count=len(selected_products) * len(sources),
                    applied_high_confidence_url_count=len(accepted_indexes),
                    persisted_candidate_count=0,
                ),
            )
    elif options.apply_high_confidence and session is None:
        warning = "apply_high_confidence requested but database is not configured; no source_urls were written."
        warnings.append(warning)
        if progress is not None:
            progress.add_warning(warning, {"run_id": run_id})

    completed_at = _now()
    candidates_to_persist = candidates_for_candidate_storage(
        candidates,
        apply_source_urls=apply_source_urls,
        apply_high_confidence_requested=options.apply_high_confidence,
    )
    summary = build_summary_payload(
        run_id=run_id,
        mode=options.mode,
        source=options.source,
        input_path=str(options.input_path) if options.input_path else None,
        selected_count=len(selected_products),
        candidates=candidates,
        dry_run=not apply_source_urls,
        apply_high_confidence=apply_source_urls,
        warnings=warnings,
    )
    summary["source_url_write_results"] = [item.__dict__ for item in write_results]
    summary["persisted_candidate_count"] = len(candidates_to_persist) if session is not None else 0
    summary["discarded_low_confidence_candidate_count"] = len(candidates) - len(candidates_to_persist)
    summary["candidate_retention_min_confidence"] = MIN_CANDIDATE_CONFIDENCE_TO_KEEP
    if progress is not None:
        progress.report(
            "artifact_writing_started",
            details=progress_details(
                selected_products,
                sources,
                candidates,
                completed_product_source_task_count=len(selected_products) * len(sources),
                applied_high_confidence_url_count=_applied_write_count(write_results),
                persisted_candidate_count=len(candidates_to_persist) if session is not None else 0,
            ),
        )
    try:
        artifacts = write_run_artifacts(run_id=run_id, candidates=candidates_to_persist, summary=summary, output_dir=options.output_dir)
    except Exception as exc:
        if progress is not None:
            progress.add_error(str(exc).strip() or exc.__class__.__name__, {"run_id": run_id})
        raise
    if progress is not None:
        progress.report(
            "artifact_writing_completed",
            details={
                **progress_details(
                    selected_products,
                    sources,
                    candidates,
                    completed_product_source_task_count=len(selected_products) * len(sources),
                    applied_high_confidence_url_count=_applied_write_count(write_results),
                    persisted_candidate_count=len(candidates_to_persist) if session is not None else 0,
                ),
                "run_dir": artifacts.run_dir,
            },
        )

    if session is not None:
        if progress is not None:
            progress.report(
                "candidate_persistence_started",
                details=progress_details(
                    selected_products,
                    sources,
                    candidates,
                    completed_product_source_task_count=len(selected_products) * len(sources),
                    applied_high_confidence_url_count=_applied_write_count(write_results),
                    persisted_candidate_count=0,
                ),
            )
        try:
            persist_discovery_run(
                session,
                summary=summary,
                filters_json=_filters_json(options),
                started_at=started_at,
                completed_at=completed_at,
            )
            if candidates_to_persist:
                persist_candidate_rows(session, candidates_to_persist)
        except Exception as exc:
            if progress is not None:
                progress.add_error(str(exc).strip() or exc.__class__.__name__, {"run_id": run_id})
            raise
        if progress is not None:
            progress.report(
                "candidate_persistence_completed",
                details=progress_details(
                    selected_products,
                    sources,
                    candidates,
                    completed_product_source_task_count=len(selected_products) * len(sources),
                    applied_high_confidence_url_count=_applied_write_count(write_results),
                    persisted_candidate_count=len(candidates_to_persist),
                ),
            )
    if progress is not None:
        progress.report(
            "run_completed",
            details=progress_details(
                selected_products,
                sources,
                candidates,
                completed_product_source_task_count=len(selected_products) * len(sources),
                applied_high_confidence_url_count=_applied_write_count(write_results),
                persisted_candidate_count=len(candidates_to_persist) if session is not None else 0,
            ),
            warnings=warnings,
        )

    return SourceUrlAgentResult(run_id=run_id, summary=summary, candidates=candidates, artifacts=artifacts, warnings=warnings)


def _run_browser_tasks(
    *,
    run_id: str,
    products: list[AgentProduct],
    sources: list[SourceDefinition],
    options: SourceUrlAgentOptions,
    session: Session | None,
    warnings: list[str],
) -> list[SourceUrlAgentCandidate]:
    try:
        return run_with_browser(
            run_id=run_id,
            products=products,
            sources=sources,
            options=options,
            session=session,
        )
    except Exception as exc:
        warning = f"Browser unavailable; all tasks marked error: {str(exc).strip() or exc.__class__.__name__}"
        warnings.append(warning)
        if options.progress_reporter is not None:
            options.progress_reporter.add_error(warning, {"run_id": run_id})
        return browser_unavailable_candidates(run_id, products, sources, options, str(exc) or exc.__class__.__name__)


def _limited_products(products: list[AgentProduct], options: SourceUrlAgentOptions) -> list[AgentProduct]:
    limit = options.limit
    if options.max_products_per_batch is not None:
        limit = min(limit, options.max_products_per_batch) if limit is not None else options.max_products_per_batch
    if limit is None:
        return products
    return products[: max(0, limit)]


def _applied_write_count(write_results: list) -> int:
    return sum(1 for item in write_results if item.action in {"created", "updated", "duplicate"})


def _filters_json(options: SourceUrlAgentOptions) -> dict:
    return {
        "run_id": options.run_id,
        "source": options.source,
        "limit": options.limit,
        "offset": options.offset,
        "catalog_product_id": options.catalog_product_id,
        "model": options.model,
        "selected_models": options.selected_models or [],
        "missing_only": options.missing_only,
        "active_only": options.active_only,
        "dry_run": options.dry_run,
        "apply_high_confidence": options.apply_high_confidence,
        "max_products_per_batch": options.max_products_per_batch,
        "max_searches_per_product_source": options.max_searches_per_product_source,
        "rate_limit_seconds": options.rate_limit_seconds,
        "headed": options.headed,
        "no_browser_cache": options.no_browser_cache,
    }


def _make_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
