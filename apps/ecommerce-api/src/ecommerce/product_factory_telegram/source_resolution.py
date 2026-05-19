"""Telegram compatibility layer for Product Factory source resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ecommerce.product_factory_source_resolution.config import (
    DEFAULT_SOURCE_RESOLUTION_CONFIG_PATH,
    PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_ENV,
    PreferredSourceConfig,
    SourceResolutionConfig,
    SourceResolutionConfigError,
    load_source_resolution_config,
)
from ecommerce.product_factory_source_resolution.exceptions import SourceResolutionError
from ecommerce.product_factory_source_resolution.fetchers import (
    BraveResultFetcher,
    BraveSearchResultFetcher,
    default_brave_definition as _default_brave_definition,
)
from ecommerce.product_factory_source_resolution.models import (
    SourceResolutionCandidate,
    SourceResolutionProduct,
    SourceResolutionResult,
)
from ecommerce.product_factory_source_resolution.resolver import ProductFactorySourceResolver as _GenericProductFactorySourceResolver
from ecommerce.product_factory_telegram.warehouse import WarehouseProduct


@dataclass(frozen=True)
class ProductFactorySourceResolver(_GenericProductFactorySourceResolver):
    def resolve(
        self,
        *,
        product: WarehouseProduct | SourceResolutionProduct,
        source_scoped_queries: bool | None = None,
    ) -> SourceResolutionResult:
        return super().resolve(product=_source_resolution_product(product), source_scoped_queries=source_scoped_queries)


def resolver_from_config_path(path: str | Path | None = None) -> ProductFactorySourceResolver:
    return ProductFactorySourceResolver(config=load_source_resolution_config(path))


def _source_resolution_product(product: WarehouseProduct | SourceResolutionProduct) -> SourceResolutionProduct:
    if isinstance(product, SourceResolutionProduct):
        return product
    metadata = dict(product.metadata)
    return SourceResolutionProduct(
        model=product.model,
        name=product.name,
        brand=str(metadata.get("manufacturer") or "").strip() or None,
        mpn=str(metadata.get("mpn") or "").strip() or None,
        barcode=str(metadata.get("barcode") or "").strip() or None,
        category=str(metadata.get("category") or "").strip() or None,
        metadata=metadata,
    )


__all__ = [
    "DEFAULT_SOURCE_RESOLUTION_CONFIG_PATH",
    "PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_ENV",
    "BraveResultFetcher",
    "BraveSearchResultFetcher",
    "PreferredSourceConfig",
    "ProductFactorySourceResolver",
    "SourceResolutionCandidate",
    "SourceResolutionConfig",
    "SourceResolutionConfigError",
    "SourceResolutionError",
    "SourceResolutionProduct",
    "SourceResolutionResult",
    "_default_brave_definition",
    "load_source_resolution_config",
    "resolver_from_config_path",
]
