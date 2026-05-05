"""Configurable source registry for Source URL Agent Mode."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlsplit

from pricefetcher.source_url_agent.page_rules import url_rejection_reason


DEFAULT_SOURCE_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "config" / "source_url_agent" / "sources.json"
SOURCE_CHOICES = ("bestprice", "skroutz", "electronet", "kotsovolos", "public", "plaisio", "all")


@dataclass(frozen=True)
class SourceDefinition:
    source_name: str
    source_domain: str
    source_type: str
    enabled: bool
    expected_listing_field: str | None
    public_search_url_templates: tuple[str, ...]
    product_url_patterns: tuple[str, ...]
    blocked_url_patterns: tuple[str, ...]
    rate_limit_seconds: float
    max_candidates_per_product: int
    max_searches_per_product: int
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceDefinition":
        return cls(
            source_name=_required_text(payload.get("source_name"), "source_name"),
            source_domain=_required_text(payload.get("source_domain"), "source_domain"),
            source_type=_required_text(payload.get("source_type"), "source_type"),
            enabled=bool(payload.get("enabled", True)),
            expected_listing_field=_optional_text(payload.get("expected_listing_field")),
            public_search_url_templates=tuple(_string_list(payload.get("public_search_url_templates"))),
            product_url_patterns=tuple(_string_list(payload.get("product_url_patterns"))),
            blocked_url_patterns=tuple(_string_list(payload.get("blocked_url_patterns"))),
            rate_limit_seconds=float(payload.get("rate_limit_seconds", 2.0)),
            max_candidates_per_product=max(1, int(payload.get("max_candidates_per_product", 6))),
            max_searches_per_product=max(1, int(payload.get("max_searches_per_product", 3))),
            notes=str(payload.get("notes") or "").strip(),
        )

    def build_search_urls(self, queries: list[str], *, max_searches: int | None = None) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        limit = max_searches if max_searches is not None else self.max_searches_per_product
        for query in queries[:limit]:
            encoded = quote_plus(query)
            for template in self.public_search_url_templates:
                url = template.replace("{query}", encoded).replace("{query_raw}", query)
                if url in seen:
                    continue
                seen.add(url)
                urls.append(url)
        return urls

    def is_product_url(self, url: str) -> bool:
        normalized = _without_query_fragment(url)
        if not self._host_matches(normalized):
            return False
        if url_rejection_reason(url):
            return False
        if url_rejection_reason(normalized):
            return False
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in self.blocked_url_patterns):
            return False
        return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in self.product_url_patterns)

    def canonical_candidate_url(self, url: str) -> str:
        return _without_query_fragment(url)

    def _host_matches(self, url: str) -> bool:
        host = str(urlsplit(url).hostname or "").casefold()
        expected = self.source_domain.casefold()
        return host == expected or host == expected.removeprefix("www.")


@dataclass(frozen=True)
class SourceRegistry:
    sources: dict[str, SourceDefinition]

    def get(self, source_name: str) -> SourceDefinition:
        normalized = source_name.strip().lower()
        try:
            return self.sources[normalized]
        except KeyError as exc:
            raise ValueError(f"Unknown source: {source_name}") from exc

    def selected(self, value: str) -> list[SourceDefinition]:
        normalized = value.strip().lower()
        if normalized == "all":
            return [source for source in self.sources.values() if source.enabled]
        source = self.get(normalized)
        return [source] if source.enabled else []


def load_source_registry(path: Path | None = None) -> SourceRegistry:
    registry_path = path or DEFAULT_SOURCE_REGISTRY_PATH
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("Source registry must contain a sources list.")
    sources = [SourceDefinition.from_dict(item) for item in raw_sources if isinstance(item, dict)]
    return SourceRegistry(sources={source.source_name: source for source in sources})


def _without_query_fragment(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path or ''}"


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required in source registry.")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]
