"""Ecommerce DB repository compatibility barrel.

New application code should import repository helpers from the workflow-owned
modules in this package. Compatibility exports are resolved lazily to avoid
cross-workflow import cycles during startup.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "ObservationReplacementResult": "price_monitoring",
    "ProductFromSourceResult": "products",
    "backfill_price_observation_listings_from_offer_observations": "price_monitoring",
    "catalog_snapshot_to_dict": "price_monitoring",
    "count_catalog_snapshots": "price_monitoring",
    "count_price_observations": "price_monitoring",
    "count_run_observations_by_match_status": "price_monitoring",
    "create_or_reuse_product_source": "products",
    "create_product_from_source_urls": "products",
    "ensure_catalog_snapshots_from_rows": "price_monitoring",
    "ensure_vendor_rows": "products",
    "find_or_create_product_from_model": "products",
    "find_product_by_identity": "products",
    "get_monitoring_run": "price_monitoring",
    "json_safe_value": "common",
    "list_catalog_snapshot": "price_monitoring",
    "list_model_price_history": "price_monitoring",
    "list_monitoring_runs": "price_monitoring",
    "list_price_observation_listings": "price_monitoring",
    "list_price_observation_listings_for_run": "price_monitoring",
    "list_price_observations": "price_monitoring",
    "list_product_price_history": "price_monitoring",
    "match_product_for_observation": "products",
    "monitoring_run_to_dict": "price_monitoring",
    "persist_monitoring_run_creation": "price_monitoring",
    "price_observation_listing_to_dict": "price_monitoring",
    "price_observation_to_dict": "price_monitoring",
    "product_source_to_dict": "products",
    "product_to_dict": "products",
    "replace_catalog_snapshots": "price_monitoring",
    "replace_price_observations": "price_monitoring",
    "update_monitoring_run_from_fetch": "price_monitoring",
    "upsert_product_from_catalog_row": "products",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value
