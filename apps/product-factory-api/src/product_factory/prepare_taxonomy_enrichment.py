from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import ParsedProduct, TaxonomyResolution
from .taxonomy import TaxonomyResolver


@dataclass(slots=True)
class PrepareTaxonomyEnrichmentResult:
    taxonomy: TaxonomyResolution
    taxonomy_candidates: list[dict[str, Any]]
    manufacturer_enrichment: dict[str, Any]


def resolve_prepare_taxonomy_enrichment(
    *,
    source: str,
    parsed: ParsedProduct,
    fetcher: Any,
    model_dir: Path,
    taxonomy_resolver_factory: Callable[[], TaxonomyResolver] = TaxonomyResolver,
    enrich_source_from_manufacturer_docs_fn: (
        Callable[..., dict[str, Any]] | None
    ) = None,
) -> PrepareTaxonomyEnrichmentResult:
    del fetcher, model_dir, enrich_source_from_manufacturer_docs_fn
    taxonomy_resolver = taxonomy_resolver_factory()
    taxonomy, taxonomy_candidates = taxonomy_resolver.resolve(
        breadcrumbs=parsed.source.breadcrumbs,
        url=parsed.source.canonical_url or parsed.source.url,
        name=parsed.source.name,
        key_specs=parsed.source.key_specs,
        spec_sections=parsed.source.spec_sections,
    )

    manufacturer_enrichment = {
        "applied": False,
        "provider": "",
        "providers_considered": [],
        "matched_providers": [],
        "documents": [],
        "documents_discovered": 0,
        "documents_parsed": 0,
        "warnings": [],
        "section_count": 0,
        "field_count": 0,
        "hero_summary_applied": False,
        "presentation_applied": False,
        "presentation_block_count": 0,
        "fallback_reason": "manufacturer_enrichment_disabled",
    }

    return PrepareTaxonomyEnrichmentResult(
        taxonomy=taxonomy,
        taxonomy_candidates=taxonomy_candidates,
        manufacturer_enrichment=manufacturer_enrichment,
    )


execute_prepare_taxonomy_enrichment = resolve_prepare_taxonomy_enrichment
