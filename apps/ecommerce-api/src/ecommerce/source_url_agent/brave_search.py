"""Brave Web Search discovery for Source URL Agent candidate URLs."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.result_url_candidates import (
    CandidateUrlNormalizer,
    KnownSourceUrlClassifier,
    SourceProductUrlFilter,
)
from ecommerce.source_url_agent.search_providers import (
    SearchProviderCandidate,
    SearchProviderDefinition,
    SearchProviderError,
    SearchProviderProvenance,
    SearchProviderResult,
)
from ecommerce.source_url_agent.sources import SourceDefinition
from ecommerce.utils.text import collapse_internal_spaces


BRAVE_SEARCH_PROVIDER_NAME = "brave_search"
BRAVE_DISCOVERY_METHOD = "brave_web_search"
DEFAULT_BRAVE_SEARCH_ENDPOINT_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_SEARCH_API_KEY_ENV_VAR = "BRAVE_SEARCH_API_KEY"


@dataclass(frozen=True)
class BraveSearchResultItem:
    url: str
    title: str
    description: str
    extra_snippets: tuple[str, ...]
    profile: dict[str, Any]
    fetch_metadata: dict[str, Any]
    rank: int


@dataclass(frozen=True)
class BraveSearchProductResult:
    query: str
    status: str
    candidates: list[SearchProviderCandidate]
    searched_urls: list[str]
    errors: list[str] = field(default_factory=list)
    provider_errors: list[SearchProviderError] = field(default_factory=list)
    discarded_count: int = 0

    @property
    def kept_candidates_by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate in self.candidates:
            source_name = candidate.provenance.source_name
            counts[source_name] = counts.get(source_name, 0) + 1
        return counts

    def to_summary(self) -> dict[str, Any]:
        return {
            "provider_name": BRAVE_SEARCH_PROVIDER_NAME,
            "query": self.query,
            "status": self.status,
            "kept_candidates_by_source": self.kept_candidates_by_source,
            "discarded_count": self.discarded_count,
        }


class BraveSearchHttpClient(Protocol):
    def search(self, *, definition: SearchProviderDefinition, query: str, api_key: str) -> Any:
        ...


class HttpxBraveSearchClient:
    def search(self, *, definition: SearchProviderDefinition, query: str, api_key: str) -> Any:
        params = _brave_query_params(definition, query)
        headers = {
            "X-Subscription-Token": api_key,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
        timeout = httpx.Timeout(definition.timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            return client.get(definition.endpoint_url or DEFAULT_BRAVE_SEARCH_ENDPOINT_URL, params=params, headers=headers)


class BraveSearchProvider:
    def __init__(self, definition: SearchProviderDefinition, *, client: BraveSearchHttpClient | None = None) -> None:
        if definition.provider_name != BRAVE_SEARCH_PROVIDER_NAME:
            raise ValueError(f"Brave Search provider requires provider_name={BRAVE_SEARCH_PROVIDER_NAME}.")
        if definition.provider_type != "brave":
            raise ValueError("Brave Search provider requires provider_type=brave.")
        self.definition = definition
        self.client = client or HttpxBraveSearchClient()
        self.normalizer = CandidateUrlNormalizer()

    def discover(
        self,
        *,
        product: AgentProduct,
        source: SourceDefinition,
        browser: object,
        queries: list[str],
        max_searches: int | None,
        max_candidates: int | None,
        rate_limit_seconds: float | None,
    ) -> SearchProviderResult:
        del browser, queries, max_searches, rate_limit_seconds
        result = self.discover_product(product=product, sources=[source], max_candidates_per_source=max_candidates)
        return SearchProviderResult(
            candidates=result.candidates,
            searched_queries=[result.query] if result.query else [],
            searched_urls=result.searched_urls,
            errors=result.errors,
            provider_errors=result.provider_errors,
            provider_summary=result.to_summary(),
        )

    def discover_product(
        self,
        *,
        product: AgentProduct,
        sources: list[SourceDefinition],
        max_candidates_per_source: int | None = None,
    ) -> BraveSearchProductResult:
        query_source = sources[0] if len(sources) == 1 else None
        queries = build_brave_product_queries(product, source=query_source)
        if not queries:
            return BraveSearchProductResult(query="", status="no_query", candidates=[], searched_urls=[])
        query = queries[0]
        request_url = self.request_url(query)
        api_key = str(os.environ.get(BRAVE_SEARCH_API_KEY_ENV_VAR) or "").strip()
        if not api_key:
            return self._error_result(
                query=query,
                request_url=request_url,
                status="missing_api_key",
                message="Missing Brave Search API key.",
            )

        try:
            response = self.client.search(definition=self.definition, query=query, api_key=api_key)
        except httpx.TimeoutException:
            return self._error_result(query=query, request_url=request_url, status="timeout", message="Brave Search API request timed out.")
        except Exception as exc:
            return self._error_result(
                query=query,
                request_url=request_url,
                status="error",
                message=str(exc).strip() or exc.__class__.__name__,
            )

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code in {401, 403}:
            return self._error_result(
                query=query,
                request_url=request_url,
                status="unauthorized",
                message=f"Brave Search API returned HTTP {status_code}.",
            )
        if status_code == 429:
            return self._error_result(
                query=query,
                request_url=request_url,
                status="rate_limited",
                message="Brave Search API returned HTTP 429.",
            )
        if status_code >= 400:
            return self._error_result(
                query=query,
                request_url=request_url,
                status="error",
                message=f"Brave Search API returned HTTP {status_code}.",
            )

        try:
            payload = response.json()
        except Exception as exc:
            return self._error_result(
                query=query,
                request_url=request_url,
                status="error",
                message=f"Invalid Brave Search API JSON response: {exc.__class__.__name__}.",
            )

        result_items = brave_web_results(payload, max_results=self.definition.count)
        return self._candidates_from_results(
            sources=sources,
            query=query,
            request_url=request_url,
            result_items=result_items,
            max_candidates_per_source=max_candidates_per_source,
        )

    def request_url(self, query: str) -> str:
        endpoint = self.definition.endpoint_url or DEFAULT_BRAVE_SEARCH_ENDPOINT_URL
        return f"{endpoint}?{urlencode(_brave_query_params(self.definition, query))}"

    def _candidates_from_results(
        self,
        *,
        sources: list[SourceDefinition],
        query: str,
        request_url: str,
        result_items: list[BraveSearchResultItem],
        max_candidates_per_source: int | None,
    ) -> BraveSearchProductResult:
        classifier = KnownSourceUrlClassifier(sources)
        product_filter = SourceProductUrlFilter()
        candidates: list[SearchProviderCandidate] = []
        seen_candidates: set[str] = set()
        seen_result_urls: set[str] = set()
        kept_by_source: dict[str, int] = {}
        discarded_count = 0
        for item in result_items:
            normalized = self.normalizer.normalize(item.url)
            if not normalized:
                discarded_count += 1
                continue
            if normalized in seen_result_urls:
                continue
            seen_result_urls.add(normalized)
            source = classifier.classify(normalized)
            if source is None:
                discarded_count += 1
                continue
            candidate_url = product_filter.keep(source, normalized)
            if not candidate_url:
                discarded_count += 1
                continue
            source_count = kept_by_source.get(source.source_name, 0)
            source_limit = max_candidates_per_source if max_candidates_per_source is not None else source.max_candidates_per_product
            if source_count >= source_limit:
                discarded_count += 1
                continue
            if candidate_url in seen_candidates:
                continue
            seen_candidates.add(candidate_url)
            kept_by_source[source.source_name] = source_count + 1
            candidates.append(
                SearchProviderCandidate(
                    candidate_url=candidate_url,
                    provenance=SearchProviderProvenance(
                        provider_name=self.definition.provider_name,
                        source_name=source.source_name,
                        original_query=query,
                        search_url=request_url,
                        candidate_url=candidate_url,
                        result_index=item.rank,
                        discovery_method=BRAVE_DISCOVERY_METHOD,
                        allow_high_confidence_auto_apply=self.definition.allow_high_confidence_auto_apply,
                    ),
                    provider_title=item.title,
                    provider_description=item.description,
                    provider_extra_snippets=item.extra_snippets,
                    provider_profile=item.profile,
                    provider_fetch_metadata=item.fetch_metadata,
                )
            )
        status = "found_candidates" if candidates else ("no_results" if not result_items else "no_known_source_product_candidates")
        return BraveSearchProductResult(
            query=query,
            status=status,
            candidates=candidates,
            searched_urls=[request_url],
            discarded_count=discarded_count,
        )

    def _error_result(self, *, query: str, request_url: str, status: str, message: str) -> BraveSearchProductResult:
        error = SearchProviderError(
            provider_name=self.definition.provider_name,
            requested_url=request_url,
            final_url=request_url,
            title="",
            body_text="",
            error_code=status,
            error_message=message,
            provenance=SearchProviderProvenance(
                provider_name=self.definition.provider_name,
                source_name="",
                original_query=query,
                search_url=request_url,
                candidate_url="",
                result_index=None,
                discovery_method=BRAVE_DISCOVERY_METHOD,
                allow_high_confidence_auto_apply=self.definition.allow_high_confidence_auto_apply,
            ),
        )
        return BraveSearchProductResult(
            query=query,
            status=status,
            candidates=[],
            searched_urls=[request_url] if request_url else [],
            errors=[f"{BRAVE_SEARCH_PROVIDER_NAME}:{status}"],
            provider_errors=[error],
        )


def build_brave_product_queries(product: AgentProduct, *, source: SourceDefinition | None = None) -> list[str]:
    brand = collapse_internal_spaces(product.manufacturer)
    identifier = collapse_internal_spaces(product.mpn) or collapse_internal_spaces(product.model)
    if not identifier and brand:
        name = collapse_internal_spaces(product.name)
        if _name_is_precise_enough(name):
            identifier = name
    if not identifier:
        return []
    if source is not None:
        domain = source.source_domain.removeprefix("www.")
        source_queries = [f'site:{domain} "{identifier}"']
        if brand:
            source_queries.append(f'site:{domain} "{brand}" "{identifier}"')
        return source_queries
    query = collapse_internal_spaces(f"{identifier} {brand}") if brand else identifier
    return [query] if query else []


def brave_web_results(payload: object, *, max_results: int = 10) -> list[BraveSearchResultItem]:
    if not isinstance(payload, dict):
        return []
    web = payload.get("web")
    if not isinstance(web, dict):
        return []
    raw_results = web.get("results")
    if not isinstance(raw_results, list):
        return []
    items: list[BraveSearchResultItem] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url:
            continue
        items.append(
            BraveSearchResultItem(
                url=url,
                title=_clean_result_text(raw.get("title")),
                description=_clean_result_text(raw.get("description") or raw.get("snippet")),
                extra_snippets=tuple(_clean_result_text(item) for item in _raw_extra_snippets(raw)),
                profile=_compact_mapping(raw.get("profile")),
                fetch_metadata=_fetch_metadata(raw),
                rank=len(items) + 1,
            )
        )
        if len(items) >= max_results:
            break
    return items


def _brave_query_params(definition: SearchProviderDefinition, query: str) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "q": query,
        "country": definition.country,
        "search_lang": definition.search_lang,
        "ui_lang": definition.ui_lang,
        "count": definition.count,
        "offset": definition.offset,
        "safesearch": definition.safesearch,
        "result_filter": definition.result_filter,
        "spellcheck": str(definition.spellcheck).lower(),
    }
    if definition.extra_snippets:
        params["extra_snippets"] = "true"
    if not definition.text_decorations:
        params["text_decorations"] = "false"
    if definition.include_fetch_metadata:
        params["include_fetch_metadata"] = "true"
    if definition.operators:
        params["operators"] = "true"
    return params


def _raw_extra_snippets(raw: dict[str, Any]) -> list[object]:
    value = raw.get("extra_snippets")
    if not isinstance(value, list):
        return []
    return [item for item in value if str(item or "").strip()]


def _clean_result_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return collapse_internal_spaces(text)


def _compact_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        if isinstance(item, (str, int, float, bool)):
            out[key_text] = item
    return out


def _fetch_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    metadata = _compact_mapping(raw.get("fetch_metadata"))
    for key in ("page_age", "page_fetched", "language", "family_friendly"):
        if key in raw and key not in metadata:
            value = raw.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                metadata[key] = value
    return metadata


def _name_is_precise_enough(name: str) -> bool:
    if not name:
        return False
    return any(character.isdigit() for character in name) and len(name.split()) <= 8
