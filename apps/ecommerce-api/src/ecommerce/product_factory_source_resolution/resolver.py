"""Generic Product Factory source resolver service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ecommerce.product_factory_source_resolution.config import SourceResolutionConfig, load_source_resolution_config
from ecommerce.product_factory_source_resolution.fetchers import BraveResultFetcher, BraveSearchResultFetcher
from ecommerce.product_factory_source_resolution.models import (
    SourceResolutionCandidate,
    SourceResolutionProduct,
    SourceResolutionResult,
)
from ecommerce.product_factory_source_resolution.queries import build_queries, build_source_scoped_queries
from ecommerce.product_factory_source_resolution.scoring import score_candidate
from ecommerce.product_factory_source_resolution.urls import normalized_product_url


@dataclass(frozen=True)
class ProductFactorySourceResolver:
    config: SourceResolutionConfig
    fetcher: BraveResultFetcher = field(default_factory=BraveSearchResultFetcher)
    max_results_per_query: int = 10
    source_scoped_queries: bool = False

    def resolve(self, *, product: SourceResolutionProduct, source_scoped_queries: bool | None = None) -> SourceResolutionResult:
        scoped = self.source_scoped_queries if source_scoped_queries is None else source_scoped_queries
        queries = build_source_scoped_queries(product, self.config) if scoped else build_queries(product)
        raw_candidates: list[SourceResolutionCandidate] = []
        seen_urls: set[str] = set()
        for query in queries:
            for item in self.fetcher.search(query, max_results=self.max_results_per_query):
                source = self.config.classify_url(str(getattr(item, "url", "")))
                if source is None:
                    continue
                url = normalized_product_url(str(getattr(item, "url", "")), source)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                confidence = score_candidate(product=product, source=source, item=item, url=url)
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
            queries=tuple(queries),
        )


def resolver_from_config_path(path: str | Path | None = None) -> ProductFactorySourceResolver:
    return ProductFactorySourceResolver(config=load_source_resolution_config(path))
