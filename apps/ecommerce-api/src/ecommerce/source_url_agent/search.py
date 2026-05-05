"""Public search strategies for Source URL Agent Mode."""

from __future__ import annotations

from dataclasses import dataclass

from ecommerce.source_url_agent.browser import PageSnapshot, SourceUrlBrowserSession
from ecommerce.source_url_agent.evidence import error_evidence, extract_page_evidence
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.sources import SourceDefinition
from ecommerce.utils.text import collapse_internal_spaces


@dataclass(frozen=True)
class EvidenceCandidate:
    url: str
    evidence: object


@dataclass(frozen=True)
class SourceSearchResult:
    evidence: list[object]
    searched_queries: list[str]
    searched_urls: list[str]
    errors: list[str]


def generate_search_queries(product: AgentProduct, source: SourceDefinition) -> list[str]:
    queries: list[str] = []
    if product.mpn and product.manufacturer:
        queries.append(f"{product.manufacturer} {product.mpn}")
    return _dedupe_queries(queries)


def discover_source_evidence(
    *,
    product: AgentProduct,
    source: SourceDefinition,
    browser: SourceUrlBrowserSession,
    max_searches: int | None = None,
    max_candidates: int | None = None,
    rate_limit_seconds: float | None = None,
) -> SourceSearchResult:
    queries = generate_search_queries(product, source)
    search_limit = max_searches if max_searches is not None else source.max_searches_per_product
    candidate_limit = max_candidates if max_candidates is not None else source.max_candidates_per_product
    search_urls = source.build_search_urls(queries, max_searches=search_limit)
    discovered_urls: list[str] = []
    errors: list[str] = []

    for search_url in search_urls:
        snapshot = browser.fetch_snapshot(search_url, rate_limit_seconds=rate_limit_seconds or source.rate_limit_seconds)
        if snapshot.status == "error":
            errors.append(f"{search_url}: {snapshot.error_code}")
            if snapshot.error_code == "blocked_or_captcha":
                return SourceSearchResult(
                    evidence=[
                        error_evidence(
                            product=product,
                            requested_url=search_url,
                            final_url=snapshot.final_url,
                            title=snapshot.title,
                            body_text=snapshot.body_text,
                            error_code="blocked_or_captcha",
                            error_message=snapshot.error_message,
                        )
                    ],
                    searched_queries=queries[:search_limit],
                    searched_urls=search_urls,
                    errors=errors,
                )
            continue
        for url in _candidate_urls_from_snapshot(source, snapshot):
            if url in discovered_urls:
                continue
            discovered_urls.append(url)
            if len(discovered_urls) >= candidate_limit:
                break
        if len(discovered_urls) >= candidate_limit:
            break

    evidence_items: list[object] = []
    for candidate_url in discovered_urls[:candidate_limit]:
        snapshot = browser.fetch_snapshot(candidate_url, rate_limit_seconds=rate_limit_seconds or source.rate_limit_seconds)
        if snapshot.status == "error":
            evidence_items.append(
                error_evidence(
                    product=product,
                    requested_url=candidate_url,
                    final_url=snapshot.final_url,
                    title=snapshot.title,
                    body_text=snapshot.body_text,
                    error_code=snapshot.error_code,
                    error_message=snapshot.error_message,
                )
            )
            continue
        evidence_items.append(
            extract_page_evidence(
                product=product,
                source=source,
                requested_url=candidate_url,
                final_url=snapshot.final_url,
                html_text=snapshot.html,
                title=snapshot.title,
                body_text=snapshot.body_text,
            )
        )

    return SourceSearchResult(
        evidence=evidence_items,
        searched_queries=queries[:search_limit],
        searched_urls=search_urls,
        errors=errors,
    )


def _candidate_urls_from_snapshot(source: SourceDefinition, snapshot: PageSnapshot) -> list[str]:
    urls = [snapshot.final_url, *snapshot.links]
    candidates: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not source.is_product_url(url):
            continue
        candidate = source.canonical_candidate_url(url)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    return candidates


def _dedupe_queries(values: list[str]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        query = collapse_internal_spaces(value)
        if not query:
            continue
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
    return queries
