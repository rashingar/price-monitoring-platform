"""Query building for Product Factory source resolution."""

from __future__ import annotations

from ecommerce.product_factory_source_resolution.config import SourceResolutionConfig
from ecommerce.product_factory_source_resolution.models import SourceResolutionProduct
from ecommerce.utils.text import collapse_internal_spaces


def build_queries(product: SourceResolutionProduct) -> list[str]:
    name = collapse_internal_spaces(product.name)
    brand = collapse_internal_spaces(product.brand or product.metadata.get("manufacturer", ""))
    mpn = collapse_internal_spaces(product.mpn or product.metadata.get("mpn", ""))
    barcode = collapse_internal_spaces(product.barcode or product.metadata.get("barcode", ""))
    category = collapse_internal_spaces(product.category or product.metadata.get("category", ""))
    raw_queries = [
        collapse_internal_spaces(f'"{mpn}" {brand} {name}') if mpn else "",
        collapse_internal_spaces(f'"{barcode}" {brand} {name}') if barcode else "",
        collapse_internal_spaces(f"{brand} {name} {category}"),
        name,
    ]
    return _unique_queries(raw_queries)


def build_source_scoped_queries(product: SourceResolutionProduct, config: SourceResolutionConfig) -> list[str]:
    name = collapse_internal_spaces(product.name)
    brand = collapse_internal_spaces(product.brand or product.metadata.get("manufacturer", ""))
    identity = collapse_internal_spaces(f"{brand} {name}") or name
    raw_queries: list[str] = []
    for source in config.preferred_sources:
        raw_queries.append(collapse_internal_spaces(f"{identity} site:{source.primary_domain}"))
    if identity:
        raw_queries.append(identity)
    return _unique_queries(raw_queries)


def _unique_queries(raw_queries: list[str]) -> list[str]:
    queries: list[str] = []
    for query in raw_queries:
        if query and query not in queries:
            queries.append(query)
    return queries
