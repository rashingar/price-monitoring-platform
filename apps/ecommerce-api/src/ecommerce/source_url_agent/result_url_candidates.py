"""Provider-agnostic filtering for top-result candidate URLs."""

from __future__ import annotations

from urllib.parse import urlsplit

from ecommerce.source_urls import SourceUrlValidationError, normalize_source_url
from ecommerce.source_url_agent.sources import SourceDefinition


class CandidateUrlNormalizer:
    """Normalize absolute HTTP(S) result URLs and remove tracking parameters."""

    def normalize(self, raw_url: str) -> str:
        text = str(raw_url or "").strip()
        if not text:
            return ""
        parsed = urlsplit(text)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        try:
            return normalize_source_url(text)
        except SourceUrlValidationError:
            return ""


class KnownSourceUrlClassifier:
    """Map URLs to configured Source URL Agent sources by exact host."""

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
