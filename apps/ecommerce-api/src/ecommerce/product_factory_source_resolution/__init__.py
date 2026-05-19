"""Generic Product Factory source URL resolution services."""

from .config import (
    DEFAULT_SOURCE_RESOLUTION_CONFIG_PATH,
    PRODUCT_FACTORY_SOURCE_RESOLUTION_CONFIG_ENV,
    PreferredSourceConfig,
    SourceResolutionConfig,
    SourceResolutionConfigError,
    load_source_resolution_config,
)
from .exceptions import SourceResolutionError
from .fetchers import BraveResultFetcher, BraveSearchResultFetcher
from .models import SourceResolutionCandidate, SourceResolutionProduct, SourceResolutionResult
from .resolver import ProductFactorySourceResolver, resolver_from_config_path
from .urls import classify_supported_product_url, normalized_product_url

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
    "classify_supported_product_url",
    "load_source_resolution_config",
    "normalized_product_url",
    "resolver_from_config_path",
]
