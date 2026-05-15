"""Product/source task execution for Source URL Agent runs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.source_url_agent.browser import SourceUrlBrowserSession
from ecommerce.source_url_agent.candidate_results import candidates_from_search_result
from ecommerce.source_url_agent.candidates import SourceUrlAgentCandidate, synthetic_candidate
from ecommerce.source_url_agent.options import Resolver, SourceUrlAgentOptions
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.search import (
    SourceSearchResult,
    discover_product_level_search_evidence,
    discover_source_evidence,
    generate_search_queries,
)
from ecommerce.source_url_agent.search_providers import load_search_provider_registry, uses_product_level_search_provider
from ecommerce.source_url_agent.sources import SourceDefinition


def run_with_browser(
    *,
    run_id: str,
    products: list[AgentProduct],
    sources: list[SourceDefinition],
    options: SourceUrlAgentOptions,
    session: Session | None,
) -> list[SourceUrlAgentCandidate]:
    provider_registry = load_search_provider_registry()
    with SourceUrlBrowserSession(
        headed=options.headed,
        no_browser_cache=options.no_browser_cache,
        default_rate_limit_seconds=options.rate_limit_seconds or 2.0,
    ) as browser:
        if uses_product_level_search_provider(provider_registry, sources):
            product_level_cache: dict[tuple[int | None, str, str, str], dict[str, SourceSearchResult]] = {}

            def product_level_resolver(product: AgentProduct, source: SourceDefinition) -> SourceSearchResult:
                key = (product.catalog_product_id, product.model, product.mpn, product.manufacturer)
                if key not in product_level_cache:
                    product_level_cache[key] = discover_product_level_search_evidence(
                        product=product,
                        sources=sources,
                        browser=browser,
                        provider_registry=provider_registry,
                        max_candidates=None,
                        rate_limit_seconds=options.rate_limit_seconds,
                    )
                return product_level_cache[key].get(
                    source.source_name,
                    SourceSearchResult(evidence=[], searched_queries=[], searched_urls=[], errors=[]),
                )

            return run_with_resolver(
                run_id=run_id,
                products=products,
                sources=sources,
                options=options,
                session=session,
                resolver=product_level_resolver,
            )
        return run_with_resolver(
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


def run_with_resolver(
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
                        **progress_details(
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
                                **progress_details(
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
                        **progress_details(
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
            source_candidates = candidates_from_search_result(
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
                        **progress_details(
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
                        **progress_details(
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


def browser_unavailable_candidates(
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


def progress_details(
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
