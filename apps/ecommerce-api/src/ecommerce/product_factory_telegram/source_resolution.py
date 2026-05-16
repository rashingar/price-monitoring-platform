"""Config-driven source URL resolution for Telegram Product Factory intake."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from ecommerce.product_factory_telegram.warehouse import WarehouseProduct
from ecommerce.source_url_agent.brave_search import (
    BRAVE_SEARCH_API_KEY_ENV_VAR,
    DEFAULT_BRAVE_SEARCH_ENDPOINT_URL,
    BraveSearchHttpClient,
    HttpxBraveSearchClient,
    brave_web_results,
)
from ecommerce.source_url_agent.search_providers import SearchProviderDefinition
from ecommerce.utils.text import collapse_internal_spaces


PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_ENV = "PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_PATH"
DEFAULT_SOURCE_RESOLUTION_CONFIG_PATH = Path(__file__).resolve().parents[5] / "config" / "product_factory_source_resolution.json"


class SourceResolutionConfigError(ValueError):
    """Raised when the source resolution config is invalid."""


class SourceResolutionError(RuntimeError):
    """Raised when source resolution cannot safely run."""


@dataclass(frozen=True)
class PreferredSourceConfig:
    source_name: str
    weight: int
    domains: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    product_url_patterns: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PreferredSourceConfig":
        source_name = _required_text(payload.get("source_name"), "preferred_sources.source_name").casefold()
        domains = tuple(_text_list(payload.get("domains")))
        if not domains:
            raise SourceResolutionConfigError(f"preferred source {source_name} must define at least one domain.")
        patterns = tuple(_text_list(payload.get("product_url_patterns")))
        if not patterns:
            raise SourceResolutionConfigError(f"preferred source {source_name} must define product_url_patterns.")
        try:
            weight = int(payload.get("weight"))
        except (TypeError, ValueError) as exc:
            raise SourceResolutionConfigError(f"preferred source {source_name} has an invalid weight.") from exc
        if weight < 0:
            raise SourceResolutionConfigError(f"preferred source {source_name} weight must be non-negative.")
        aliases = tuple(item.casefold() for item in _text_list(payload.get("aliases")))
        return cls(
            source_name=source_name,
            weight=weight,
            domains=tuple(domain.casefold().removeprefix("https://").removeprefix("http://").strip("/") for domain in domains),
            aliases=aliases,
            product_url_patterns=patterns,
        )

    def matches_host(self, host: str) -> bool:
        normalized = host.casefold().removeprefix("www.")
        return any(normalized == domain.casefold().removeprefix("www.") for domain in self.domains)


@dataclass(frozen=True)
class SourceResolutionConfig:
    minimum_confidence: int
    suggestion_confidence: int
    max_suggestions: int
    pending_choice_ttl_minutes: int
    preferred_sources: tuple[PreferredSourceConfig, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceResolutionConfig":
        if not isinstance(payload, dict):
            raise SourceResolutionConfigError("Source resolution config must be a JSON object.")
        minimum_confidence = _int_range(payload.get("minimum_confidence"), "minimum_confidence", minimum=1, maximum=100)
        suggestion_confidence = _int_range(payload.get("suggestion_confidence"), "suggestion_confidence", minimum=1, maximum=100)
        if suggestion_confidence > minimum_confidence:
            raise SourceResolutionConfigError("suggestion_confidence must be less than or equal to minimum_confidence.")
        max_suggestions = _int_range(payload.get("max_suggestions"), "max_suggestions", minimum=1, maximum=10)
        pending_choice_ttl_minutes = _int_range(
            payload.get("pending_choice_ttl_minutes"),
            "pending_choice_ttl_minutes",
            minimum=1,
            maximum=1440,
        )
        raw_sources = payload.get("preferred_sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise SourceResolutionConfigError("preferred_sources must contain at least one source.")
        sources = tuple(PreferredSourceConfig.from_dict(item) for item in raw_sources if isinstance(item, dict))
        if len(sources) != len(raw_sources):
            raise SourceResolutionConfigError("preferred_sources must contain only objects.")
        names = [source.source_name for source in sources]
        if len(set(names)) != len(names):
            raise SourceResolutionConfigError("preferred_sources contains duplicate source_name values.")
        return cls(
            minimum_confidence=minimum_confidence,
            suggestion_confidence=suggestion_confidence,
            max_suggestions=max_suggestions,
            pending_choice_ttl_minutes=pending_choice_ttl_minutes,
            preferred_sources=sources,
        )

    @property
    def pending_choice_ttl(self) -> timedelta:
        return timedelta(minutes=self.pending_choice_ttl_minutes)

    @property
    def preferred_source_names(self) -> list[str]:
        return [source.source_name for source in self.preferred_sources]

    def classify_url(self, url: str) -> PreferredSourceConfig | None:
        host = str(urlsplit(url).hostname or "")
        for source in self.preferred_sources:
            if source.matches_host(host):
                return source
        return None

    def source_for_alias(self, value: str) -> PreferredSourceConfig | None:
        normalized = value.strip().casefold()
        for source in self.preferred_sources:
            if normalized == source.source_name or normalized in source.aliases:
                return source
        return None


@dataclass(frozen=True)
class SourceResolutionCandidate:
    source_name: str
    url: str
    title: str
    description: str
    confidence: int
    result_rank: int | None = None

    def to_metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_name": self.source_name,
            "url": self.url,
            "confidence": self.confidence,
        }
        if self.title:
            payload["title"] = self.title
        if self.result_rank is not None:
            payload["result_rank"] = self.result_rank
        return payload


@dataclass(frozen=True)
class SourceResolutionResult:
    method: str
    selected: SourceResolutionCandidate | None
    candidates: tuple[SourceResolutionCandidate, ...]
    config: SourceResolutionConfig

    @property
    def status(self) -> str:
        if self.selected is not None and self.selected.confidence >= self.config.minimum_confidence:
            return "selected"
        if self.candidates:
            return "suggestions"
        return "no_usable_source"

    def metadata_for(self, candidate: SourceResolutionCandidate) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "method": self.method,
            "selected_source": candidate.source_name,
            "selected_url": candidate.url,
            "confidence": candidate.confidence,
            "candidate_count": len(self.candidates),
            "preferred_sources": self.config.preferred_source_names,
        }
        if candidate.title:
            payload["selected_title"] = candidate.title
        return payload


class BraveResultFetcher(Protocol):
    def search(self, query: str, *, max_results: int) -> list[Any]: ...


class BraveSearchResultFetcher:
    def __init__(
        self,
        *,
        definition: SearchProviderDefinition | None = None,
        client: BraveSearchHttpClient | None = None,
    ) -> None:
        self.definition = definition or _default_brave_definition()
        self.client = client or HttpxBraveSearchClient()

    def search(self, query: str, *, max_results: int) -> list[Any]:
        api_key = str(os.environ.get(BRAVE_SEARCH_API_KEY_ENV_VAR) or "").strip()
        if not api_key:
            raise SourceResolutionError("Missing Brave Search API key.")
        definition = replace(self.definition, count=min(20, max(1, max_results)))
        try:
            response = self.client.search(definition=definition, query=query, api_key=api_key)
        except httpx.TimeoutException as exc:
            raise SourceResolutionError("Brave Search API request timed out.") from exc
        except Exception as exc:
            raise SourceResolutionError(str(exc).strip() or exc.__class__.__name__) from exc
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            raise SourceResolutionError(f"Brave Search API returned HTTP {status_code}.")
        try:
            payload = response.json()
        except Exception as exc:
            raise SourceResolutionError("Brave Search API returned invalid JSON.") from exc
        return brave_web_results(payload, max_results=max_results)


@dataclass(frozen=True)
class ProductFactorySourceResolver:
    config: SourceResolutionConfig
    fetcher: BraveResultFetcher = field(default_factory=BraveSearchResultFetcher)
    max_results_per_query: int = 10

    def resolve(self, *, product: WarehouseProduct) -> SourceResolutionResult:
        raw_candidates: list[SourceResolutionCandidate] = []
        seen_urls: set[str] = set()
        for query in _build_queries(product):
            for item in self.fetcher.search(query, max_results=self.max_results_per_query):
                source = self.config.classify_url(str(getattr(item, "url", "")))
                if source is None:
                    continue
                url = _normalized_product_url(str(getattr(item, "url", "")), source)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                confidence = _score_candidate(product=product, source=source, item=item, url=url)
                if confidence < self.config.suggestion_confidence:
                    continue
                raw_candidates.append(
                    SourceResolutionCandidate(
                        source_name=source.source_name,
                        url=url,
                        title=str(getattr(item, "title", "") or ""),
                        description=str(getattr(item, "description", "") or ""),
                        confidence=confidence,
                        result_rank=getattr(item, "rank", None),
                    )
                )
        candidates = tuple(sorted(raw_candidates, key=lambda item: (-item.confidence, item.result_rank or 9999, item.url)))
        selected = candidates[0] if candidates and candidates[0].confidence >= self.config.minimum_confidence else None
        return SourceResolutionResult(
            method="brave_weighted",
            selected=selected,
            candidates=candidates[: self.config.max_suggestions],
            config=self.config,
        )


def load_source_resolution_config(path: str | Path | None = None) -> SourceResolutionConfig:
    raw_path = str(path or os.environ.get(PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_ENV) or "").strip()
    config_path = Path(raw_path).expanduser() if raw_path else DEFAULT_SOURCE_RESOLUTION_CONFIG_PATH
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SourceResolutionConfigError(f"Source resolution config file was not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SourceResolutionConfigError(f"Source resolution config is invalid JSON: {config_path}") from exc
    except OSError as exc:
        raise SourceResolutionConfigError(f"Source resolution config file is not readable: {config_path}") from exc
    return SourceResolutionConfig.from_dict(payload)


def resolver_from_config_path(path: str | Path | None = None) -> ProductFactorySourceResolver:
    return ProductFactorySourceResolver(config=load_source_resolution_config(path))


def _score_candidate(*, product: WarehouseProduct, source: PreferredSourceConfig, item: Any, url: str) -> int:
    title = str(getattr(item, "title", "") or "")
    description = str(getattr(item, "description", "") or "")
    extra_snippets = " ".join(str(value) for value in getattr(item, "extra_snippets", ()) or ())
    haystack = " ".join([url, title, description, extra_snippets])
    score = min(40.0, max(0.0, source.weight * 0.4))
    score += _identity_score(product, haystack)
    score += _manufacturer_score(product, haystack)
    score += _name_overlap_score(product.name, haystack, limit=12.0)
    score += 8.0
    score += _title_description_score(product.name, title, description)
    rank = getattr(item, "rank", None)
    if isinstance(rank, int) and rank > 0:
        score += max(0.0, 6.0 - min(rank, 6))
    return min(100, int(round(score)))


def _identity_score(product: WarehouseProduct, haystack: str) -> float:
    normalized = _alnum(haystack)
    metadata = product.metadata
    score = 0.0
    for key in ("mpn", "barcode"):
        value = _alnum(metadata.get(key, ""))
        if value and value in normalized:
            score += 20.0
            break
    model = _alnum(product.model)
    if model and model in normalized:
        score += 5.0
    return min(score, 25.0)


def _manufacturer_score(product: WarehouseProduct, haystack: str) -> float:
    manufacturer = str(product.metadata.get("manufacturer") or "").strip()
    if manufacturer and _alnum(manufacturer) in _alnum(haystack):
        return 8.0
    return 0.0


def _name_overlap_score(name: str, haystack: str, *, limit: float) -> float:
    tokens = _token_set(name)
    if not tokens:
        return 0.0
    haystack_tokens = _token_set(haystack)
    if not haystack_tokens:
        return 0.0
    overlap = len(tokens & haystack_tokens) / len(tokens)
    return limit * overlap


def _title_description_score(name: str, title: str, description: str) -> float:
    title_score = _name_overlap_score(name, title, limit=4.0)
    description_score = _name_overlap_score(name, description, limit=3.0)
    return title_score + description_score


def _build_queries(product: WarehouseProduct) -> list[str]:
    metadata = product.metadata
    name = collapse_internal_spaces(product.name)
    manufacturer = collapse_internal_spaces(metadata.get("manufacturer", ""))
    mpn = collapse_internal_spaces(metadata.get("mpn", ""))
    barcode = collapse_internal_spaces(metadata.get("barcode", ""))
    category = collapse_internal_spaces(metadata.get("category", ""))
    raw_queries = [
        collapse_internal_spaces(f'"{mpn}" {manufacturer} {name}') if mpn else "",
        collapse_internal_spaces(f'"{barcode}" {manufacturer} {name}') if barcode else "",
        collapse_internal_spaces(f"{manufacturer} {name} {category}"),
        name,
    ]
    queries: list[str] = []
    for query in raw_queries:
        if query and query not in queries:
            queries.append(query)
    return queries


def _normalized_product_url(url: str, source: PreferredSourceConfig) -> str:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    normalized = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
    if not _looks_like_product_path(path):
        return ""
    if not _matches_product_pattern(normalized, path, source.product_url_patterns):
        return ""
    return normalized


def _looks_like_product_path(path: str) -> bool:
    normalized = path.strip().casefold()
    if normalized in {"", "/"}:
        return False
    blocked = (
        "/search",
        "/category",
        "/categories",
        "/cat/",
        "/cart",
        "/checkout",
        "/account",
        "/login",
        "/blog",
        "/compare",
        "/wishlist",
    )
    return not any(item in normalized for item in blocked)


def _matches_product_pattern(url: str, path: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern == "/":
            return True
        try:
            if re.search(pattern, url, flags=re.IGNORECASE) or re.search(pattern, path, flags=re.IGNORECASE):
                return True
        except re.error:
            if pattern.casefold() in path.casefold() or pattern.casefold() in url.casefold():
                return True
    return False


def _default_brave_definition() -> SearchProviderDefinition:
    return SearchProviderDefinition(
        provider_name="brave_search",
        provider_type="brave",
        enabled=True,
        allow_high_confidence_auto_apply=False,
        endpoint_url=DEFAULT_BRAVE_SEARCH_ENDPOINT_URL,
        country="GR",
        search_lang="el",
        ui_lang="el-GR",
        count=10,
        safesearch="moderate",
        result_filter="web",
        spellcheck=False,
        extra_snippets=True,
        text_decorations=False,
        include_fetch_metadata=True,
        operators=True,
        timeout_seconds=10.0,
    )


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SourceResolutionConfigError(f"{field_name} is required.")
    return text


def _text_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _int_range(value: object, field_name: str, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SourceResolutionConfigError(f"{field_name} must be an integer.") from exc
    if number < minimum or number > maximum:
        raise SourceResolutionConfigError(f"{field_name} must be between {minimum} and {maximum}.")
    return number


def _token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w]+", value.casefold()) if len(token) >= 3}


def _alnum(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", value.casefold())
