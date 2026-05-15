"""Public search strategies for Source URL Agent Mode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ecommerce.source_url_agent.browser import SourceUrlBrowserSession
from ecommerce.source_url_agent.brave_search import BraveSearchProvider
from ecommerce.source_url_agent.evidence import error_evidence, extract_page_evidence, provider_search_result_evidence
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.search_providers import (
    SearchProviderRegistry,
    discover_with_provider_cascade,
    load_search_provider_registry,
)
from ecommerce.source_url_agent.sources import SourceDefinition
from ecommerce.utils.text import collapse_internal_spaces, normalize_product_text


TEMPLATE_FIELD_RE = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")


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
    provider_summary: dict[str, Any] | None = None


def generate_search_queries(product: AgentProduct, source: SourceDefinition) -> list[str]:
    strategy = SourceQueryStrategy(source)
    return strategy.generate(product)


@dataclass(frozen=True)
class SourceQueryStrategy:
    source: SourceDefinition

    def generate(self, product: AgentProduct) -> list[str]:
        candidates: list[str] = []
        candidates.extend(self._template_queries(product))
        candidates.extend(_generic_query_candidates(product))
        return _dedupe_queries(candidates)[: self.source.max_searches_per_product]

    def _template_queries(self, product: AgentProduct) -> list[str]:
        fields = _template_fields(product)
        queries: list[str] = []
        for template in self.source.query_templates:
            required_fields = TEMPLATE_FIELD_RE.findall(template)
            if not required_fields or any(not fields.get(field) for field in required_fields):
                continue
            queries.append(template.format_map(fields))
        return queries


def discover_source_evidence(
    *,
    product: AgentProduct,
    source: SourceDefinition,
    browser: SourceUrlBrowserSession,
    max_searches: int | None = None,
    max_candidates: int | None = None,
    rate_limit_seconds: float | None = None,
    provider_registry: SearchProviderRegistry | None = None,
) -> SourceSearchResult:
    queries = generate_search_queries(product, source)
    search_limit = max_searches if max_searches is not None else source.max_searches_per_product
    candidate_limit = max_candidates if max_candidates is not None else source.max_candidates_per_product
    registry = provider_registry or load_search_provider_registry()
    provider_result = discover_with_provider_cascade(
        product=product,
        source=source,
        browser=browser,
        queries=queries,
        registry=registry,
        max_searches=search_limit,
        max_candidates=candidate_limit,
        rate_limit_seconds=rate_limit_seconds,
    )
    if provider_result.provider_errors:
        return SourceSearchResult(
            evidence=[
                error_evidence(
                    product=product,
                    requested_url=item.requested_url,
                    final_url=item.final_url,
                    title=item.title,
                    body_text=item.body_text,
                    error_code=item.error_code,
                    error_message=item.error_message,
                    provider_provenance=item.provenance.to_json(),
                )
                for item in provider_result.provider_errors
            ],
            searched_queries=provider_result.searched_queries,
            searched_urls=provider_result.searched_urls,
            errors=provider_result.errors,
        )

    evidence_items: list[object] = []
    for candidate in provider_result.candidates[:candidate_limit]:
        candidate_url = candidate.candidate_url
        snapshot = browser.fetch_snapshot(candidate_url, rate_limit_seconds=rate_limit_seconds or source.rate_limit_seconds)
        provider_provenance = _candidate_provider_provenance(candidate)
        if snapshot.status == "error":
            if candidate.has_provider_text:
                evidence_items.append(
                    _provider_fallback_evidence(
                        product=product,
                        source=source,
                        candidate=candidate,
                        final_url=snapshot.final_url,
                        page_fetch_error_code=snapshot.error_code,
                        page_fetch_error_message=snapshot.error_message,
                    )
                )
            else:
                evidence_items.append(
                    error_evidence(
                        product=product,
                        requested_url=candidate_url,
                        final_url=snapshot.final_url,
                        title=snapshot.title,
                        body_text=snapshot.body_text,
                        source=source,
                        error_code=snapshot.error_code,
                        error_message=snapshot.error_message,
                        provider_provenance=provider_provenance,
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
                provider_provenance=provider_provenance,
            )
        )

    return SourceSearchResult(
        evidence=evidence_items,
        searched_queries=provider_result.searched_queries,
        searched_urls=provider_result.searched_urls,
        errors=provider_result.errors,
        provider_summary=provider_result.provider_summary,
    )


def discover_product_level_search_evidence(
    *,
    product: AgentProduct,
    sources: list[SourceDefinition],
    browser: SourceUrlBrowserSession,
    provider_registry: SearchProviderRegistry,
    max_candidates: int | None = None,
    rate_limit_seconds: float | None = None,
) -> dict[str, SourceSearchResult]:
    definition = _product_level_provider_definition(provider_registry, sources)
    provider = BraveSearchProvider(definition)
    product_result = provider.discover_product(
        product=product,
        sources=sources,
        max_candidates_per_source=max_candidates,
    )
    results = {
        source.source_name: SourceSearchResult(
            evidence=[],
            searched_queries=[product_result.query] if product_result.query else [],
            searched_urls=product_result.searched_urls,
            errors=product_result.errors,
            provider_summary=product_result.to_summary(),
        )
        for source in sources
    }
    if product_result.provider_errors:
        for source in sources:
            results[source.source_name] = SourceSearchResult(
                evidence=[
                    error_evidence(
                        product=product,
                        requested_url=item.requested_url,
                        final_url=item.final_url,
                        title=item.title,
                        body_text=item.body_text,
                        error_code=item.error_code,
                        error_message=item.error_message,
                        provider_provenance={**item.provenance.to_json(), "source_name": source.source_name},
                    )
                    for item in product_result.provider_errors
                ],
                searched_queries=[product_result.query] if product_result.query else [],
                searched_urls=product_result.searched_urls,
                errors=product_result.errors,
                provider_summary=product_result.to_summary(),
            )
        return results

    source_by_name = {source.source_name: source for source in sources}
    for candidate in product_result.candidates:
        source = source_by_name.get(candidate.provenance.source_name)
        if source is None:
            continue
        snapshot = browser.fetch_snapshot(candidate.candidate_url, rate_limit_seconds=rate_limit_seconds or source.rate_limit_seconds)
        if snapshot.status == "error":
            if candidate.has_provider_text:
                evidence = _provider_fallback_evidence(
                    product=product,
                    source=source,
                    candidate=candidate,
                    final_url=snapshot.final_url,
                    page_fetch_error_code=snapshot.error_code,
                    page_fetch_error_message=snapshot.error_message,
                )
            else:
                evidence = error_evidence(
                    product=product,
                    requested_url=candidate.candidate_url,
                    final_url=snapshot.final_url,
                    title=snapshot.title,
                    body_text=snapshot.body_text,
                    source=source,
                    error_code=snapshot.error_code,
                    error_message=snapshot.error_message,
                    provider_provenance=_candidate_provider_provenance(candidate),
                )
        else:
            evidence = extract_page_evidence(
                product=product,
                source=source,
                requested_url=candidate.candidate_url,
                final_url=snapshot.final_url,
                html_text=snapshot.html,
                title=snapshot.title,
                body_text=snapshot.body_text,
                provider_provenance=_candidate_provider_provenance(candidate),
            )
        current = results[source.source_name]
        results[source.source_name] = SourceSearchResult(
            evidence=[*current.evidence, evidence],
            searched_queries=current.searched_queries,
            searched_urls=current.searched_urls,
            errors=current.errors,
            provider_summary=current.provider_summary,
        )
    return results


def _candidate_provider_provenance(candidate) -> dict[str, Any]:
    return {**candidate.provenance.to_json(), **candidate.provider_evidence_json()}


def _provider_fallback_evidence(
    *,
    product: AgentProduct,
    source: SourceDefinition,
    candidate,
    final_url: str,
    page_fetch_error_code: str,
    page_fetch_error_message: str,
):
    provenance = _candidate_provider_provenance(candidate)
    provenance["page_fetch_error_code"] = page_fetch_error_code
    provenance["page_fetch_error_message"] = page_fetch_error_message
    return provider_search_result_evidence(
        product=product,
        source=source,
        requested_url=candidate.candidate_url,
        final_url=final_url or candidate.candidate_url,
        title=candidate.provider_title,
        description=candidate.provider_description,
        extra_snippets=candidate.provider_extra_snippets,
        provider_provenance=provenance,
    )


def _product_level_provider_definition(
    provider_registry: SearchProviderRegistry,
    sources: list[SourceDefinition],
):
    for source in sources:
        for definition in provider_registry.cascade_for_source(source.source_name):
            if definition.enabled:
                return definition
    raise ValueError("No enabled product-level search provider is configured.")


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


def _generic_query_candidates(product: AgentProduct) -> list[str]:
    queries: list[str] = []
    manufacturers = _manufacturer_names(product)
    if product.mpn:
        for manufacturer in manufacturers:
            queries.append(_join_query(manufacturer, product.mpn))
        queries.append(product.mpn)
    if product.model:
        for manufacturer in manufacturers:
            queries.append(_join_query(manufacturer, product.model))
        queries.append(product.model)
    if product.name:
        for manufacturer in manufacturers:
            queries.append(_join_manufacturer_and_name(manufacturer, product.name))
        queries.append(product.name)
    return queries


def _template_fields(product: AgentProduct) -> dict[str, str]:
    return {
        "manufacturer": collapse_internal_spaces(product.manufacturer),
        "brand": collapse_internal_spaces(product.manufacturer),
        "mpn": collapse_internal_spaces(product.mpn),
        "model": collapse_internal_spaces(product.model),
        "name": collapse_internal_spaces(product.name),
        "product_name": collapse_internal_spaces(product.name),
        "title": collapse_internal_spaces(product.name),
    }


def _manufacturer_names(product: AgentProduct) -> tuple[str, ...]:
    manufacturer = collapse_internal_spaces(product.manufacturer)
    return (manufacturer,) if manufacturer else ()


def _join_query(*values: str) -> str:
    return collapse_internal_spaces(" ".join(value for value in values if value))


def _join_manufacturer_and_name(manufacturer: str, name: str) -> str:
    manufacturer_text = collapse_internal_spaces(manufacturer)
    name_text = collapse_internal_spaces(name)
    if not manufacturer_text or not name_text:
        return ""
    manufacturer_norm = normalize_product_text(manufacturer_text)
    name_norm = normalize_product_text(name_text)
    if name_norm == manufacturer_norm or name_norm.startswith(f"{manufacturer_norm} "):
        return name_text
    return _join_query(manufacturer_text, name_text)
