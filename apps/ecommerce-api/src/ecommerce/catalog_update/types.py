"""Shared catalog update types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecommerce.catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.catalog_update.paths import display_path

DEFAULT_EXPORT_PROFILE = DEFAULT_CATALOG_SOURCE
DEFAULT_EXPORT_TIMEOUT_SECONDS = 900
EXCLUDED_MODELS_ENV_VAR = "CATALOG_UPDATE_EXCLUDED_MODELS_PATH"
DEFAULT_EXCLUDED_MODELS_RELATIVE_PATH = Path("config") / "catalog" / "codes_not_in_entersoft.csv"


class CatalogUpdateError(RuntimeError):
    """Raised when the catalog update workflow cannot complete."""


class CatalogUpdateConfigError(CatalogUpdateError):
    """Raised when required OpenCart export configuration is missing."""


@dataclass(frozen=True)
class CatalogUpdateConfig:
    store_base: str
    admin_path: str
    admin_user: str
    admin_pass: str
    export_profile: str = DEFAULT_EXPORT_PROFILE
    timeout_seconds: int = DEFAULT_EXPORT_TIMEOUT_SECONDS
    headed: bool = False

    @property
    def admin_url(self) -> str:
        base = self.store_base.rstrip("/")
        path = self.admin_path.strip("/")
        return f"{base}/{path}" if path else base

    @property
    def admin_index_url(self) -> str:
        from ecommerce.catalog_update.admin_paths import build_admin_index

        return build_admin_index(self.store_base, self.admin_path)

    def safe_payload(self) -> dict[str, Any]:
        return {
            "admin_url": self.admin_url,
            "admin_index_url": self.admin_index_url,
            "export_profile": self.export_profile,
            "timeout_seconds": self.timeout_seconds,
            "headed": self.headed,
        }


@dataclass(frozen=True)
class CatalogExportResult:
    downloaded_path: Path
    downloaded_size: int


@dataclass(frozen=True)
class ExcludedModels:
    path: Path
    found: bool
    explicit_path: bool
    models: frozenset[str]

    @property
    def count(self) -> int:
        return len(self.models)


@dataclass(frozen=True)
class CatalogExclusionFilterResult:
    exclusion_file_path: Path
    exclusion_file_found: bool
    excluded_model_count: int
    input_row_count: int
    removed_row_count: int
    output_row_count: int
    filtered_csv_path: Path

    def to_payload(self) -> dict[str, Any]:
        return {
            "exclusion_file_path": display_path(self.exclusion_file_path),
            "exclusion_file_found": self.exclusion_file_found,
            "excluded_model_count": self.excluded_model_count,
            "input_row_count": self.input_row_count,
            "removed_row_count": self.removed_row_count,
            "output_row_count": self.output_row_count,
            "filtered_csv_path": display_path(self.filtered_csv_path),
        }


@dataclass(frozen=True)
class CatalogExclusionCleanupResult:
    purged_catalog_products: int = 0
    purged_source_urls: int = 0
    purged_source_url_discovery_tasks: int = 0
    purged_source_url_candidates: int = 0
    purged_product_sources: int = 0
    deactivated_products: int = 0

    def to_payload(self) -> dict[str, int]:
        return {
            "purged_catalog_products": self.purged_catalog_products,
            "purged_source_urls": self.purged_source_urls,
            "purged_source_url_discovery_tasks": self.purged_source_url_discovery_tasks,
            "purged_source_url_candidates": self.purged_source_url_candidates,
            "purged_product_sources": self.purged_product_sources,
            "deactivated_products": self.deactivated_products,
        }
