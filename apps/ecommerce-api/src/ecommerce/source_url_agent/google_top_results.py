"""Google top-result discovery for Source URL Agent candidate URLs."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, quote_plus, unquote, urljoin, urlsplit, urlunsplit

from ecommerce.source_urls import SourceUrlValidationError, normalize_source_url
from ecommerce.source_url_agent.browser import PageSnapshot, SourceUrlBrowserSession
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.search_providers import (
    GOOGLE_TOP_RESULTS_PROVIDER_NAME,
    SearchProviderCandidate,
    SearchProviderDefinition,
    SearchProviderError,
    SearchProviderProvenance,
    SearchProviderResult,
)
from ecommerce.source_url_agent.sources import SourceDefinition
from ecommerce.utils.text import collapse_internal_spaces


DEFAULT_GOOGLE_SEARCH_URL_TEMPLATE = "https://www.google.gr/search?q={query}&hl=el&gl=GR&num=10&pws=0"
GOOGLE_DISCOVERY_METHOD = "google_top_results"


@dataclass(frozen=True)
class GoogleTopResultsProductResult:
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
            "query": self.query,
            "status": self.status,
            "kept_candidates_by_source": self.kept_candidates_by_source,
            "discarded_count": self.discarded_count,
        }


class CandidateUrlNormalizer:
    """Unwrap Google redirect URLs and normalize candidate URLs."""

    def normalize(self, raw_url: str, *, base_url: str = "") -> str:
        unwrapped = self.unwrap(raw_url, base_url=base_url)
        if not unwrapped:
            return ""
        try:
            return normalize_source_url(unwrapped)
        except SourceUrlValidationError:
            return ""

    def unwrap(self, raw_url: str, *, base_url: str = "") -> str:
        text = html.unescape(str(raw_url or "").strip())
        if not text:
            return ""
        absolute = urljoin(base_url, text) if base_url else text
        parsed = urlsplit(absolute)
        host = str(parsed.hostname or "").casefold()
        if _is_google_host(host):
            query = dict(parse_qsl(parsed.query or "", keep_blank_values=True))
            if parsed.path == "/url" and query.get("q"):
                return _decoded_url(query["q"])
            if query.get("url"):
                return _decoded_url(query["url"])
            return ""
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            return absolute
        return ""


class KnownSourceUrlClassifier:
    """Map URLs to configured Source URL Agent sources by domain."""

    def __init__(self, sources: list[SourceDefinition]) -> None:
        self._sources_by_host: dict[str, SourceDefinition] = {}
        for source in sources:
            domain = source.source_domain.casefold()
            self._sources_by_host[domain] = source
            if domain.startswith("www."):
                self._sources_by_host[domain.removeprefix("www.")] = source

    def classify(self, url: str) -> SourceDefinition | None:
        host = str(urlsplit(url).hostname or "").casefold()
        return self._sources_by_host.get(host)


class SourceProductUrlFilter:
    """Apply configured source product URL rules and canonical cleanup."""

    def keep(self, source: SourceDefinition, url: str) -> str:
        if not source.is_product_url(url):
            return ""
        return source.canonical_candidate_url(url)


class GoogleTopResultsProvider:
    def __init__(self, definition: SearchProviderDefinition) -> None:
        if definition.provider_name != GOOGLE_TOP_RESULTS_PROVIDER_NAME:
            raise ValueError(f"Google top results provider requires provider_name={GOOGLE_TOP_RESULTS_PROVIDER_NAME}.")
        self.definition = definition
        self.normalizer = CandidateUrlNormalizer()

    def discover(
        self,
        *,
        product: AgentProduct,
        source: SourceDefinition,
        browser: SourceUrlBrowserSession,
        queries: list[str],
        max_searches: int | None,
        max_candidates: int | None,
        rate_limit_seconds: float | None,
    ) -> SearchProviderResult:
        del queries, max_searches
        result = self.discover_product(
            product=product,
            sources=[source],
            browser=browser,
            max_candidates_per_source=max_candidates,
            rate_limit_seconds=rate_limit_seconds,
        )
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
        browser: SourceUrlBrowserSession,
        max_candidates_per_source: int | None = None,
        rate_limit_seconds: float | None = None,
    ) -> GoogleTopResultsProductResult:
        queries = build_google_product_queries(product)
        if not queries:
            return GoogleTopResultsProductResult(query="", status="no_query", candidates=[], searched_urls=[])

        query = queries[0]
        search_url = self.search_url(query)
        snapshot = browser.fetch_snapshot(search_url, rate_limit_seconds=rate_limit_seconds)
        if snapshot.status == "error":
            status = _provider_status_for_error(snapshot.error_code)
            return GoogleTopResultsProductResult(
                query=query,
                status=status,
                candidates=[],
                searched_urls=[search_url],
                errors=[f"{GOOGLE_TOP_RESULTS_PROVIDER_NAME}:{status}"],
                provider_errors=[self._provider_error(query=query, search_url=search_url, snapshot=snapshot)],
            )

        blocked_status = google_block_status(snapshot)
        if blocked_status:
            return GoogleTopResultsProductResult(
                query=query,
                status=blocked_status,
                candidates=[],
                searched_urls=[search_url],
                errors=[f"{GOOGLE_TOP_RESULTS_PROVIDER_NAME}:{blocked_status}"],
                provider_errors=[self._provider_error(query=query, search_url=search_url, snapshot=snapshot, error_code=blocked_status)],
            )

        return self._candidates_from_snapshot(
            product=product,
            sources=sources,
            query=query,
            search_url=search_url,
            snapshot=snapshot,
            max_candidates_per_source=max_candidates_per_source,
        )

    def search_url(self, query: str) -> str:
        template = self.definition.search_url_template or DEFAULT_GOOGLE_SEARCH_URL_TEMPLATE
        return template.replace("{query}", quote_plus(query)).replace("{query_raw}", query)

    def _candidates_from_snapshot(
        self,
        *,
        product: AgentProduct,
        sources: list[SourceDefinition],
        query: str,
        search_url: str,
        snapshot: PageSnapshot,
        max_candidates_per_source: int | None,
    ) -> GoogleTopResultsProductResult:
        del product
        classifier = KnownSourceUrlClassifier(sources)
        product_filter = SourceProductUrlFilter()
        raw_urls = google_result_urls(snapshot, base_url=search_url, max_results=self.definition.max_results_per_query)
        candidates: list[SearchProviderCandidate] = []
        seen_candidates: set[str] = set()
        kept_by_source: dict[str, int] = {}
        discarded_count = 0
        for rank, raw_url in enumerate(raw_urls, start=1):
            normalized = self.normalizer.normalize(raw_url, base_url=search_url)
            if not normalized:
                discarded_count += 1
                continue
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
                        search_url=search_url,
                        candidate_url=candidate_url,
                        result_index=rank,
                        discovery_method=GOOGLE_DISCOVERY_METHOD,
                        allow_high_confidence_auto_apply=self.definition.allow_high_confidence_auto_apply,
                    ),
                )
            )
        status = "found_candidates" if candidates else ("no_results" if not raw_urls else "no_known_source_product_candidates")
        return GoogleTopResultsProductResult(
            query=query,
            status=status,
            candidates=candidates,
            searched_urls=[search_url],
            discarded_count=discarded_count,
        )

    def _provider_error(
        self,
        *,
        query: str,
        search_url: str,
        snapshot: PageSnapshot,
        error_code: str | None = None,
    ) -> SearchProviderError:
        code = error_code or snapshot.error_code or "error"
        provenance = SearchProviderProvenance(
            provider_name=self.definition.provider_name,
            source_name="",
            original_query=query,
            search_url=search_url,
            candidate_url="",
            result_index=None,
            discovery_method=GOOGLE_DISCOVERY_METHOD,
            allow_high_confidence_auto_apply=self.definition.allow_high_confidence_auto_apply,
        )
        return SearchProviderError(
            provider_name=self.definition.provider_name,
            requested_url=search_url,
            final_url=snapshot.final_url,
            title=snapshot.title,
            body_text=snapshot.body_text,
            error_code=code,
            error_message=snapshot.error_message or code,
            provenance=provenance,
        )


def build_google_product_queries(product: AgentProduct) -> list[str]:
    brand = collapse_internal_spaces(product.manufacturer)
    identifier = collapse_internal_spaces(product.mpn) or collapse_internal_spaces(product.model)
    if not identifier and brand:
        identifier = collapse_internal_spaces(product.name)
    if not identifier:
        return []
    query = collapse_internal_spaces(f"{identifier} {brand}") if brand else identifier
    return [query] if query else []


def google_result_urls(snapshot: PageSnapshot, *, base_url: str = "", max_results: int = 10) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for href in [*_hrefs_from_html(snapshot.html), *snapshot.links]:
        normalized_key = _organic_result_key(href, base_url=base_url)
        if not normalized_key or normalized_key in seen:
            continue
        seen.add(normalized_key)
        urls.append(href)
        if len(urls) >= max_results:
            break
    return urls


def google_block_status(snapshot: PageSnapshot) -> str:
    final_host = str(urlsplit(snapshot.final_url or snapshot.requested_url).hostname or "").casefold()
    final_path = str(urlsplit(snapshot.final_url or snapshot.requested_url).path or "").casefold()
    text = " ".join((snapshot.title, snapshot.body_text, snapshot.html[:2000])).casefold()
    if "consent.google." in final_host or "/consent" in final_path or "before you continue to google" in text:
        return "consent_required"
    if "captcha" in text or "recaptcha" in text:
        return "blocked"
    if "unusual traffic" in text or "our systems have detected" in text:
        return "blocked"
    return ""


class _GoogleHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        values = dict(attrs)
        href = str(values.get("href") or "").strip()
        if href:
            self.hrefs.append(href)


def _hrefs_from_html(html_text: str) -> list[str]:
    parser = _GoogleHrefParser()
    try:
        parser.feed(html_text or "")
        parser.close()
    except Exception:
        return []
    return parser.hrefs


def _organic_result_key(href: str, *, base_url: str) -> str:
    target = CandidateUrlNormalizer().unwrap(href, base_url=base_url)
    if not target:
        return ""
    parsed = urlsplit(target)
    host = str(parsed.hostname or "").casefold()
    if not host or _is_google_host(host):
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    path = re.sub(r"/+$", "", parsed.path or "/")
    return urlunsplit((parsed.scheme.casefold(), host, path, parsed.query, ""))


def _decoded_url(value: str) -> str:
    previous = str(value or "").strip()
    for _ in range(2):
        decoded = unquote(previous)
        if decoded == previous:
            break
        previous = decoded
    return previous


def _is_google_host(host: str) -> bool:
    return host == "google.com" or host.endswith(".google.com") or host == "google.gr" or host.endswith(".google.gr")


def _provider_status_for_error(error_code: str) -> str:
    if error_code == "blocked_or_captcha":
        return "blocked"
    return error_code or "error"
