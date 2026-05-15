"""Orchestration for Source URL Agent Mode."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.config import DatabaseNotConfiguredError
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.source_url_agent.artifacts import (
    SourceUrlAgentArtifactPaths,
    build_summary_payload,
    write_run_artifacts,
)
from ecommerce.source_url_agent.browser import SourceUrlBrowserSession
from ecommerce.source_url_agent.candidates import (
    MIN_CANDIDATE_CONFIDENCE_TO_KEEP,
    SourceUrlAgentCandidate,
    candidate_from_evidence,
    keep_candidate,
    synthetic_candidate,
)
from ecommerce.source_url_agent.evidence import PageEvidence
from ecommerce.source_url_agent.persistence import (
    apply_high_confidence_source_urls,
    persist_candidate_rows,
    persist_discovery_run,
)
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.progress import SourceUrlAgentProgressReporter
from ecommerce.source_url_agent.scoring import score_candidate
from ecommerce.source_url_agent.search import SourceSearchResult, discover_source_evidence, generate_search_queries
from ecommerce.source_url_agent.sources import SourceDefinition, SourceRegistry, load_source_registry


Resolver = Callable[[AgentProduct, SourceDefinition], SourceSearchResult]
ProgressCallback = Callable[[str, AgentProduct, SourceDefinition, list[SourceUrlAgentCandidate], str | None], None]


@dataclass(frozen=True)
class SourceUrlAgentOptions:
    mode: str
    run_id: str | None = None
    source: str = "all"
    input_path: Path | None = None
    output_dir: Path | None = None
    limit: int | None = None
    offset: int = 0
    catalog_product_id: int | None = None
    model: str | None = None
    selected_models: list[str] | None = None
    missing_only: bool = False
    active_only: bool = True
    dry_run: bool = True
    apply_high_confidence: bool = False
    max_products_per_batch: int | None = None
    max_searches_per_product_source: int | None = None
    rate_limit_seconds: float | None = None
    headed: bool = False
    no_browser_cache: bool = False
    progress_callback: ProgressCallback | None = None
    progress_reporter: SourceUrlAgentProgressReporter | None = None


@dataclass(frozen=True)
class SourceUrlAgentResult:
    run_id: str
    summary: dict
    candidates: list[SourceUrlAgentCandidate]
    artifacts: SourceUrlAgentArtifactPaths
    warnings: list[str]


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

    candidates: list[SourceUrlAgentCandidate]
    if progress is not None:
        progress.report(
            "discovery_started",
            details=_progress_details(
                selected_products,
                sources,
                [],
                completed_product_source_task_count=0,
                applied_high_confidence_url_count=0,
                persisted_candidate_count=0,
            ),
        )
    if resolver is not None:
        candidates = _run_with_resolver(
            run_id=run_id,
            products=selected_products,
            sources=sources,
            options=options,
            session=session,
            resolver=resolver,
        )
    else:
        try:
            with SourceUrlBrowserSession(
                headed=options.headed,
                no_browser_cache=options.no_browser_cache,
                default_rate_limit_seconds=options.rate_limit_seconds or 2.0,
            ) as browser:
                candidates = _run_with_browser(
                    run_id=run_id,
                    products=selected_products,
                    sources=sources,
                    options=options,
                    session=session,
                    browser=browser,
                )
        except Exception as exc:
            warning = f"Browser unavailable; all tasks marked error: {str(exc).strip() or exc.__class__.__name__}"
            warnings.append(warning)
            if progress is not None:
                progress.add_error(warning, {"run_id": run_id})
            candidates = _browser_unavailable_candidates(run_id, selected_products, sources, options, str(exc) or exc.__class__.__name__)

    apply_source_urls = bool(options.apply_high_confidence and not options.dry_run and session is not None)
    write_results = []
    if apply_source_urls:
        if progress is not None:
            progress.report(
                "high_confidence_apply_started",
                details=_progress_details(
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
                details=_progress_details(
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
    candidates_to_persist = _candidates_for_candidate_storage(
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
            details=_progress_details(
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
                **_progress_details(
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
                details=_progress_details(
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
                details=_progress_details(
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
            details=_progress_details(
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


def _run_with_browser(
    *,
    run_id: str,
    products: list[AgentProduct],
    sources: list[SourceDefinition],
    options: SourceUrlAgentOptions,
    session: Session | None,
    browser: SourceUrlBrowserSession,
) -> list[SourceUrlAgentCandidate]:
    return _run_with_resolver(
        run_id=run_id,
        products=products,
        sources=sources,
        options=options,
        session=session,
        resolver=lambda product, source: discover_source_evidence(
            product=product,
            source=source,
            browser=browser,
            max_searches=options.max_searches_per_product_source,
            rate_limit_seconds=options.rate_limit_seconds,
        ),
    )


def _run_with_resolver(
    *,
    run_id: str,
    products: list[AgentProduct],
    sources: list[SourceDefinition],
    options: SourceUrlAgentOptions,
    session: Session | None,
    resolver: Resolver,
) -> list[SourceUrlAgentCandidate]:
    candidates: list[SourceUrlAgentCandidate] = []
    completed_task_count = 0
    total_task_count = len(products) * len(sources)
    for product in products:
        for source in sources:
            expected_listing = product.expected_listing(source.source_name)
            if options.progress_reporter is not None:
                options.progress_reporter.report(
                    "product_source_started",
                    details={
                        **_progress_details(
                            products,
                            sources,
                            candidates,
                            completed_product_source_task_count=completed_task_count,
                            applied_high_confidence_url_count=0,
                            persisted_candidate_count=0,
                        ),
                        "product_source_task_count": total_task_count,
                        "model": product.model,
                        "mpn": product.mpn,
                        "manufacturer": product.manufacturer,
                        "source_name": source.source_name,
                    },
                )
            if options.progress_callback is not None:
                options.progress_callback("started", product, source, [], None)
            if options.missing_only and session is not None and product.catalog_product_id is not None:
                if _has_active_source_url(session, product.catalog_product_id, source.source_name):
                    source_candidates = [
                        synthetic_candidate(
                            run_id=run_id,
                            product=product,
                            source=source,
                            expected_listing=expected_listing,
                            match_status="skipped",
                            status="pending",
                            match_method="existing_active_source_url",
                            searched_queries=[],
                            notes="Skipped because active source URL already exists for this source.",
                        )
                    ]
                    candidates.extend(source_candidates)
                    completed_task_count += 1
                    if options.progress_reporter is not None:
                        options.progress_reporter.report(
                            "product_source_completed",
                            details={
                                **_progress_details(
                                    products,
                                    sources,
                                    candidates,
                                    completed_product_source_task_count=completed_task_count,
                                    applied_high_confidence_url_count=0,
                                    persisted_candidate_count=0,
                                ),
                                "model": product.model,
                                "source_name": source.source_name,
                            },
                        )
                    if options.progress_callback is not None:
                        options.progress_callback("completed", product, source, source_candidates, None)
                    continue
            search_result = resolver(product, source)
            if options.progress_reporter is not None:
                options.progress_reporter.report(
                    "candidate_scoring_started",
                    details={
                        **_progress_details(
                            products,
                            sources,
                            candidates,
                            completed_product_source_task_count=completed_task_count,
                            applied_high_confidence_url_count=0,
                            persisted_candidate_count=0,
                        ),
                        "model": product.model,
                        "source_name": source.source_name,
                        "searched_query_count": len(search_result.searched_queries),
                        "searched_url_count": len(search_result.searched_urls),
                    },
                    errors=search_result.errors,
                )
            source_candidates = _candidates_from_search_result(
                run_id=run_id,
                product=product,
                source=source,
                expected_listing=expected_listing,
                result=search_result,
            )
            candidates.extend(source_candidates)
            completed_task_count += 1
            if options.progress_reporter is not None:
                options.progress_reporter.report(
                    "candidate_scoring_completed",
                    details={
                        **_progress_details(
                            products,
                            sources,
                            candidates,
                            completed_product_source_task_count=completed_task_count,
                            applied_high_confidence_url_count=0,
                            persisted_candidate_count=0,
                        ),
                        "model": product.model,
                        "source_name": source.source_name,
                        "candidate_count": len(source_candidates),
                    },
                    errors=search_result.errors,
                )
                options.progress_reporter.report(
                    "product_source_completed",
                    details={
                        **_progress_details(
                            products,
                            sources,
                            candidates,
                            completed_product_source_task_count=completed_task_count,
                            applied_high_confidence_url_count=0,
                            persisted_candidate_count=0,
                        ),
                        "model": product.model,
                        "source_name": source.source_name,
                    },
                    errors=search_result.errors,
                )
            if options.progress_callback is not None:
                options.progress_callback("completed", product, source, source_candidates, None)
    return candidates


def _candidates_from_search_result(
    *,
    run_id: str,
    product: AgentProduct,
    source: SourceDefinition,
    expected_listing: str,
    result: SourceSearchResult,
) -> list[SourceUrlAgentCandidate]:
    evidence_items = [item for item in result.evidence if isinstance(item, PageEvidence)]
    if not evidence_items:
        queries = result.searched_queries or generate_search_queries(product, source)
        if result.errors:
            return [
                synthetic_candidate(
                    run_id=run_id,
                    product=product,
                    source=source,
                    expected_listing=expected_listing,
                    match_status="error",
                    status="error",
                    match_method="search_error",
                    searched_queries=queries,
                    notes="; ".join(result.errors),
                )
            ]
        return [
            synthetic_candidate(
                run_id=run_id,
                product=product,
                source=source,
                expected_listing=expected_listing,
                match_status="not_found",
                status="not_found",
                match_method="no_candidate_urls",
                searched_queries=queries,
                notes="No credible product page found.",
            )
        ]

    first_scores = [
        score_candidate(product=product, source=source, evidence=evidence, competing_candidates_count=0)
        for evidence in evidence_items
    ]
    plausible_count = sum(1 for score in first_scores if score.confidence_score >= 0.50 and score.match_status != "error")
    candidates: list[SourceUrlAgentCandidate] = []
    for evidence in evidence_items:
        score = score_candidate(product=product, source=source, evidence=evidence, competing_candidates_count=plausible_count)
        status = _candidate_status(score.match_status)
        candidates.append(
            candidate_from_evidence(
                run_id=run_id,
                product=product,
                source=source,
                evidence=evidence,
                score=score,
                expected_listing=expected_listing,
                competing_candidates_count=plausible_count,
                searched_queries=result.searched_queries,
                status=status,
            )
        )
    return candidates


def _browser_unavailable_candidates(
    run_id: str,
    products: list[AgentProduct],
    sources: list[SourceDefinition],
    options: SourceUrlAgentOptions,
    message: str,
) -> list[SourceUrlAgentCandidate]:
    out: list[SourceUrlAgentCandidate] = []
    for product in products:
        for source in sources:
            out.append(
                candidate := synthetic_candidate(
                    run_id=run_id,
                    product=product,
                    source=source,
                    expected_listing=product.expected_listing(source.source_name),
                    match_status="error",
                    status="error",
                    match_method="browser_unavailable",
                    searched_queries=generate_search_queries(product, source)[: source.max_searches_per_product],
                    notes=message,
                )
            )
            if options.progress_callback is not None:
                options.progress_callback("completed", product, source, [candidate], message)
    return out


def _candidate_status(match_status: str) -> str:
    if match_status == "matched":
        return "pending"
    if match_status == "needs_review":
        return "needs_review"
    if match_status == "not_found":
        return "not_found"
    if match_status == "error":
        return "error"
    return "pending"


def _candidates_for_candidate_storage(
    candidates: list[SourceUrlAgentCandidate],
    *,
    apply_source_urls: bool,
    apply_high_confidence_requested: bool,
) -> list[SourceUrlAgentCandidate]:
    del apply_source_urls, apply_high_confidence_requested
    return [candidate for candidate in candidates if keep_candidate(candidate)]


def _has_active_source_url(session: Session, catalog_product_id: int, source_name: str) -> bool:
    return (
        session.execute(
            select(SourceUrl.id)
            .where(
                SourceUrl.catalog_product_id == catalog_product_id,
                SourceUrl.source_name == source_name,
                SourceUrl.status == "active",
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _limited_products(products: list[AgentProduct], options: SourceUrlAgentOptions) -> list[AgentProduct]:
    limit = options.limit
    if options.max_products_per_batch is not None:
        limit = min(limit, options.max_products_per_batch) if limit is not None else options.max_products_per_batch
    if limit is None:
        return products
    return products[: max(0, limit)]


def _progress_details(
    products: list[AgentProduct],
    sources: list[SourceDefinition],
    candidates: list[SourceUrlAgentCandidate],
    *,
    completed_product_source_task_count: int,
    applied_high_confidence_url_count: int,
    persisted_candidate_count: int,
) -> dict:
    counts = _candidate_counts(candidates)
    return {
        "product_count": len(products),
        "source_count": len(sources),
        "product_source_task_count": len(products) * len(sources),
        "completed_product_source_task_count": completed_product_source_task_count,
        "candidate_count": len(candidates),
        "matched_count": counts["matched_count"],
        "needs_review_count": counts["needs_review_count"],
        "not_found_count": counts["not_found_count"],
        "error_count": counts["error_count"],
        "applied_high_confidence_url_count": applied_high_confidence_url_count,
        "persisted_candidate_count": persisted_candidate_count,
    }


def _candidate_counts(candidates: list[SourceUrlAgentCandidate]) -> dict[str, int]:
    return {
        "matched_count": sum(1 for candidate in candidates if candidate.match_status == "matched"),
        "needs_review_count": sum(1 for candidate in candidates if candidate.match_status == "needs_review"),
        "not_found_count": sum(1 for candidate in candidates if candidate.match_status == "not_found"),
        "error_count": sum(1 for candidate in candidates if candidate.match_status == "error"),
    }


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
