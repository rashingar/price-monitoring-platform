"""Search provider registry and browser fallback provider."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ecommerce.source_url_agent.browser import PageSnapshot, SourceUrlBrowserSession
from ecommerce.source_url_agent.products import AgentProduct
from ecommerce.source_url_agent.sources import SourceDefinition

DEFAULT_SEARCH_PROVIDER_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "source_url_agent"
    / "search_providers.json"
)
BROWSER_FALLBACK_PROVIDER_NAME = "browser_fallback"


@dataclass(frozen=True)
class SearchProviderDefinition:
    provider_name: str
    provider_type: str
    enabled: bool
    allow_high_confidence_auto_apply: bool
    search_url_template: str = ""
    max_results_per_query: int = 10
    stop_after_first_query_with_candidates: bool = True
    endpoint_url: str = ""
    country: str = "GR"
    search_lang: str = "el"
    ui_lang: str = "el-GR"
    count: int = 10
    offset: int = 0
    safesearch: str = "moderate"
    result_filter: str = "web"
    spellcheck: bool = False
    extra_snippets: bool = False
    text_decorations: bool = True
    include_fetch_metadata: bool = False
    operators: bool = False
    timeout_seconds: float = 10.0
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SearchProviderDefinition":
        provider_name = _required_text(payload.get("provider_name"), "provider_name")
        provider_type = _required_text(payload.get("provider_type"), "provider_type")
        return cls(
            provider_name=provider_name,
            provider_type=provider_type,
            enabled=bool(payload.get("enabled", True)),
            allow_high_confidence_auto_apply=bool(
                payload.get("allow_high_confidence_auto_apply", False)
            ),
            search_url_template=str(payload.get("search_url_template") or "").strip(),
            max_results_per_query=max(1, int(payload.get("max_results_per_query", 10))),
            stop_after_first_query_with_candidates=bool(
                payload.get("stop_after_first_query_with_candidates", True)
            ),
            endpoint_url=str(payload.get("endpoint_url") or "").strip(),
            country=str(payload.get("country") or "GR").strip(),
            search_lang=str(payload.get("search_lang") or "el").strip(),
            ui_lang=str(payload.get("ui_lang") or "el-GR").strip(),
            count=min(
                20,
                max(
                    1,
                    int(payload.get("count", payload.get("max_results_per_query", 10))),
                ),
            ),
            offset=max(0, int(payload.get("offset", 0))),
            safesearch=str(payload.get("safesearch") or "moderate").strip(),
            result_filter=str(payload.get("result_filter") or "web").strip(),
            spellcheck=bool(payload.get("spellcheck", False)),
            extra_snippets=bool(payload.get("extra_snippets", False)),
            text_decorations=bool(payload.get("text_decorations", True)),
            include_fetch_metadata=bool(payload.get("include_fetch_metadata", False)),
            operators=bool(payload.get("operators", False)),
            timeout_seconds=max(0.1, float(payload.get("timeout_seconds", 10))),
            notes=str(payload.get("notes") or "").strip(),
        )


@dataclass(frozen=True)
class SearchProviderProvenance:
    provider_name: str
    source_name: str
    original_query: str
    search_url: str
    candidate_url: str
    result_index: int | None
    discovery_method: str
    allow_high_confidence_auto_apply: bool
    identifier_variant: str = ""

    def to_json(self) -> dict[str, Any]:
        payload = {
            "provider_name": self.provider_name,
            "source_name": self.source_name,
            "original_query": self.original_query,
            "search_url": self.search_url,
            "candidate_url": self.candidate_url,
            "result_index": self.result_index,
            "discovery_method": self.discovery_method,
            "allow_high_confidence_auto_apply": self.allow_high_confidence_auto_apply,
        }
        if self.identifier_variant:
            payload["identifier_variant"] = self.identifier_variant
        return payload


@dataclass(frozen=True)
class SearchProviderCandidate:
    candidate_url: str
    provenance: SearchProviderProvenance
    provider_title: str = ""
    provider_description: str = ""
    provider_extra_snippets: tuple[str, ...] = ()
    provider_profile: dict[str, Any] = field(default_factory=dict)
    provider_fetch_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_provider_text(self) -> bool:
        return bool(
            self.provider_title
            or self.provider_description
            or self.provider_extra_snippets
        )

    def provider_evidence_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.provider_title:
            payload["provider_title"] = self.provider_title
        if self.provider_description:
            payload["provider_description"] = self.provider_description
        if self.provider_extra_snippets:
            payload["provider_extra_snippets"] = list(self.provider_extra_snippets)
        if self.provider_profile:
            payload["provider_profile"] = self.provider_profile
        if self.provider_fetch_metadata:
            payload["provider_fetch_metadata"] = self.provider_fetch_metadata
        return payload


@dataclass(frozen=True)
class SearchProviderError:
    provider_name: str
    requested_url: str
    final_url: str
    title: str
    body_text: str
    error_code: str
    error_message: str
    provenance: SearchProviderProvenance


@dataclass(frozen=True)
class SearchProviderResult:
    candidates: list[SearchProviderCandidate]
    searched_queries: list[str]
    searched_urls: list[str]
    errors: list[str]
    provider_errors: list[SearchProviderError]
    provider_summary: dict[str, Any] | None = None


class SourceUrlSearchProvider(Protocol):
    definition: SearchProviderDefinition

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
    ) -> SearchProviderResult: ...


@dataclass(frozen=True)
class SearchProviderRegistry:
    default_cascade: tuple[str, ...]
    providers: dict[str, SearchProviderDefinition]
    source_cascades: dict[str, tuple[str, ...]]

    def get(self, provider_name: str) -> SearchProviderDefinition:
        normalized = provider_name.strip().lower()
        try:
            return self.providers[normalized]
        except KeyError as exc:
            raise ValueError(
                f"Unknown source URL search provider: {provider_name}"
            ) from exc

    def cascade_for_source(self, source_name: str) -> list[SearchProviderDefinition]:
        normalized = source_name.strip().lower()
        provider_names = self.source_cascades.get(normalized) or self.default_cascade
        return [self.get(provider_name) for provider_name in provider_names]


class BrowserFallbackSearchProvider:
    def __init__(self, definition: SearchProviderDefinition) -> None:
        if definition.provider_name != BROWSER_FALLBACK_PROVIDER_NAME:
            raise ValueError(
                f"Browser fallback provider requires provider_name={BROWSER_FALLBACK_PROVIDER_NAME}."
            )
        if definition.provider_type != "browser":
            raise ValueError(
                "Browser fallback provider requires provider_type=browser."
            )
        self.definition = definition

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
        del product
        search_limit = (
            max_searches
            if max_searches is not None
            else source.max_searches_per_product
        )
        candidate_limit = (
            max_candidates
            if max_candidates is not None
            else source.max_candidates_per_product
        )
        query_items = queries[:search_limit]
        search_items = _search_url_query_items(source, query_items)
        searched_urls = [item.search_url for item in search_items]
        discovered_urls: list[str] = []
        candidates: list[SearchProviderCandidate] = []
        errors: list[str] = []
        provider_errors: list[SearchProviderError] = []

        for search_item in search_items:
            snapshot = browser.fetch_snapshot(
                search_item.search_url,
                rate_limit_seconds=rate_limit_seconds or source.rate_limit_seconds,
            )
            if snapshot.status == "error":
                errors.append(f"{search_item.search_url}: {snapshot.error_code}")
                if snapshot.error_code == "blocked_or_captcha":
                    provider_errors.append(
                        _provider_error(
                            definition=self.definition,
                            source=source,
                            query=search_item.query,
                            search_url=search_item.search_url,
                            snapshot=snapshot,
                        )
                    )
                    return SearchProviderResult(
                        candidates=candidates,
                        searched_queries=query_items,
                        searched_urls=searched_urls,
                        errors=errors,
                        provider_errors=provider_errors,
                    )
                continue
            for url in _candidate_urls_from_snapshot(source, snapshot):
                if url in discovered_urls:
                    continue
                discovered_urls.append(url)
                candidates.append(
                    SearchProviderCandidate(
                        candidate_url=url,
                        provenance=SearchProviderProvenance(
                            provider_name=self.definition.provider_name,
                            source_name=source.source_name,
                            original_query=search_item.query,
                            search_url=search_item.search_url,
                            candidate_url=url,
                            result_index=len(discovered_urls),
                            discovery_method="public_source_search_page",
                            allow_high_confidence_auto_apply=self.definition.allow_high_confidence_auto_apply,
                        ),
                    )
                )
                if len(discovered_urls) >= candidate_limit:
                    break
            if len(discovered_urls) >= candidate_limit:
                break

        return SearchProviderResult(
            candidates=candidates,
            searched_queries=query_items,
            searched_urls=searched_urls,
            errors=errors,
            provider_errors=provider_errors,
        )


def load_search_provider_registry(path: Path | None = None) -> SearchProviderRegistry:
    registry_path = path or DEFAULT_SEARCH_PROVIDER_REGISTRY_PATH
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    raw_default_cascade = _string_list(
        payload.get("default_provider_order")
    ) or _string_list(payload.get("default_cascade"))
    if not raw_default_cascade:
        raise ValueError(
            "Search provider registry must contain default_provider_order."
        )
    raw_providers = payload.get("providers")
    if isinstance(raw_providers, dict):
        provider_items = [
            SearchProviderDefinition.from_dict({"provider_name": name, **item})
            for name, item in raw_providers.items()
            if isinstance(item, dict)
        ]
    elif isinstance(raw_providers, list):
        provider_items = [
            SearchProviderDefinition.from_dict(item)
            for item in raw_providers
            if isinstance(item, dict)
        ]
    else:
        raise ValueError("Search provider registry must contain providers.")
    providers = {item.provider_name: item for item in provider_items}
    if len(providers) != len(provider_items):
        raise ValueError(
            "Search provider registry contains duplicate provider_name values."
        )
    source_cascades = _source_cascades(payload.get("source_cascades"))
    registry = SearchProviderRegistry(
        default_cascade=tuple(raw_default_cascade),
        providers=providers,
        source_cascades=source_cascades,
    )
    _validate_cascade_names(registry.default_cascade, providers)
    for cascade in registry.source_cascades.values():
        _validate_cascade_names(cascade, providers)
    return registry


def discover_with_provider_cascade(
    *,
    product: AgentProduct,
    source: SourceDefinition,
    browser: SourceUrlBrowserSession,
    queries: list[str],
    registry: SearchProviderRegistry,
    max_searches: int | None = None,
    max_candidates: int | None = None,
    rate_limit_seconds: float | None = None,
) -> SearchProviderResult:
    candidate_limit = (
        max_candidates
        if max_candidates is not None
        else source.max_candidates_per_product
    )
    all_candidates: list[SearchProviderCandidate] = []
    all_errors: list[str] = []
    all_provider_errors: list[SearchProviderError] = []
    searched_queries = queries[
        : (
            max_searches
            if max_searches is not None
            else source.max_searches_per_product
        )
    ]
    searched_urls: list[str] = []

    for definition in registry.cascade_for_source(source.source_name):
        if not definition.enabled:
            all_errors.append(f"provider_disabled:{definition.provider_name}")
            continue
        provider = _provider_for_definition(definition)
        try:
            result = provider.discover(
                product=product,
                source=source,
                browser=browser,
                queries=queries,
                max_searches=max_searches,
                max_candidates=max(0, candidate_limit - len(all_candidates)),
                rate_limit_seconds=rate_limit_seconds,
            )
        except Exception as exc:
            all_errors.append(
                f"{definition.provider_name}: {str(exc).strip() or exc.__class__.__name__}"
            )
            continue
        searched_queries = result.searched_queries or searched_queries
        searched_urls.extend(
            url for url in result.searched_urls if url not in searched_urls
        )
        all_errors.extend(result.errors)
        all_provider_errors.extend(result.provider_errors)
        for candidate in result.candidates:
            if any(
                existing.candidate_url == candidate.candidate_url
                for existing in all_candidates
            ):
                continue
            all_candidates.append(candidate)
            if len(all_candidates) >= candidate_limit:
                break
        if all_candidates:
            break

    return SearchProviderResult(
        candidates=all_candidates[:candidate_limit],
        searched_queries=searched_queries,
        searched_urls=searched_urls,
        errors=all_errors,
        provider_errors=all_provider_errors,
    )


@dataclass(frozen=True)
class _SearchUrlQueryItem:
    query: str
    search_url: str


def _provider_for_definition(
    definition: SearchProviderDefinition,
) -> SourceUrlSearchProvider:
    if (
        definition.provider_name == BROWSER_FALLBACK_PROVIDER_NAME
        and definition.provider_type == "browser"
    ):
        return BrowserFallbackSearchProvider(definition)
    if (
        definition.provider_name == "brave_search"
        and definition.provider_type == "brave"
    ):
        from ecommerce.source_url_agent.brave_search import BraveSearchProvider

        return BraveSearchProvider(definition)
    raise ValueError(
        f"Unsupported source URL search provider: {definition.provider_name} ({definition.provider_type})"
    )


def supports_product_level_discovery(definition: SearchProviderDefinition) -> bool:
    return (
        definition.provider_name == "brave_search"
        and definition.provider_type == "brave"
    )


def uses_product_level_search_provider(
    registry: SearchProviderRegistry, sources: list[SourceDefinition]
) -> bool:
    first_provider_name = ""
    for source in sources:
        enabled = [
            definition
            for definition in registry.cascade_for_source(source.source_name)
            if definition.enabled
        ]
        if not enabled or not supports_product_level_discovery(enabled[0]):
            return False
        if not first_provider_name:
            first_provider_name = enabled[0].provider_name
        elif enabled[0].provider_name != first_provider_name:
            return False
    return True


def _search_url_query_items(
    source: SourceDefinition, queries: list[str]
) -> list[_SearchUrlQueryItem]:
    items: list[_SearchUrlQueryItem] = []
    seen: set[str] = set()
    for query in queries:
        for search_url in source.build_search_urls([query], max_searches=1):
            if search_url in seen:
                continue
            seen.add(search_url)
            items.append(_SearchUrlQueryItem(query=query, search_url=search_url))
    return items


def _candidate_urls_from_snapshot(
    source: SourceDefinition, snapshot: PageSnapshot
) -> list[str]:
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


def _provider_error(
    *,
    definition: SearchProviderDefinition,
    source: SourceDefinition,
    query: str,
    search_url: str,
    snapshot: PageSnapshot,
) -> SearchProviderError:
    provenance = SearchProviderProvenance(
        provider_name=definition.provider_name,
        source_name=source.source_name,
        original_query=query,
        search_url=search_url,
        candidate_url="",
        result_index=None,
        discovery_method="public_source_search_page",
        allow_high_confidence_auto_apply=definition.allow_high_confidence_auto_apply,
    )
    return SearchProviderError(
        provider_name=definition.provider_name,
        requested_url=search_url,
        final_url=snapshot.final_url,
        title=snapshot.title,
        body_text=snapshot.body_text,
        error_code=snapshot.error_code,
        error_message=snapshot.error_message,
        provenance=provenance,
    )


def _source_cascades(value: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for source_name, cascade in value.items():
        normalized = str(source_name or "").strip().lower()
        if not normalized:
            continue
        out[normalized] = tuple(_string_list(cascade))
    return out


def _validate_cascade_names(
    cascade: tuple[str, ...], providers: dict[str, SearchProviderDefinition]
) -> None:
    for provider_name in cascade:
        if provider_name not in providers:
            raise ValueError(
                f"Unknown source URL search provider in cascade: {provider_name}"
            )


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise ValueError(f"{field_name} is required in search provider registry.")
    return text


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().lower() for item in value if str(item or "").strip()]
