import sys
from pathlib import Path

from sqlalchemy.orm import configure_mappers

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import ecommerce.db.models as model_registration  # noqa: E402,F401
from ecommerce.db.models.base import Base as BaseFromBase  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.models.jobs import EcommerceJob  # noqa: E402
from ecommerce.db.models.products import Product, ProductSource, SourceCaptureSnapshot  # noqa: E402
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun, SourceUrlDiscoveryTask  # noqa: E402
from ecommerce.db.models.vendor_sources import Vendor, VendorSourceCaptureRun  # noqa: E402
from ecommerce.db.models.price_monitoring import (  # noqa: E402
    CatalogSnapshot,
    MonitoringRun,
    OfferObservation,
    PriceObservation,
    PriceObservationListing,
)
from ecommerce.db.models.alerts import AlertEvent, AlertRule  # noqa: E402


EXPECTED_TABLE_NAMES = [
    "alert_events",
    "alert_rules",
    "catalog_products",
    "catalog_snapshots",
    "ecommerce_jobs",
    "monitoring_runs",
    "offer_observations",
    "price_observation_listings",
    "price_observations",
    "product_sources",
    "products",
    "source_capture_snapshots",
    "source_url_candidates",
    "source_url_discovery_runs",
    "source_url_discovery_tasks",
    "source_urls",
    "vendor_source_capture_runs",
    "vendors",
]


def test_model_package_metadata_contains_all_current_tables() -> None:
    assert sorted(BaseFromBase.metadata.tables) == EXPECTED_TABLE_NAMES


def test_domain_model_imports_share_one_metadata_registry() -> None:
    representative_models = [
        AlertEvent,
        AlertRule,
        CatalogProductRow,
        CatalogSnapshot,
        EcommerceJob,
        MonitoringRun,
        OfferObservation,
        PriceObservation,
        PriceObservationListing,
        Product,
        ProductSource,
        SourceCaptureSnapshot,
        SourceUrl,
        SourceUrlCandidate,
        SourceUrlDiscoveryRun,
        SourceUrlDiscoveryTask,
        Vendor,
        VendorSourceCaptureRun,
    ]

    assert {model.__table__.metadata for model in representative_models} == {BaseFromBase.metadata}


def test_metadata_loader_path_supports_alembic_table_discovery() -> None:
    configure_mappers()

    assert sorted(table.name for table in BaseFromBase.metadata.sorted_tables) == EXPECTED_TABLE_NAMES


def test_model_package_does_not_reexport_model_classes_or_base() -> None:
    import ecommerce.db.models as model_package  # noqa: E402

    removed_exports = {
        "AlertEvent",
        "AlertRule",
        "Base",
        "CatalogProductRow",
        "CatalogSnapshot",
        "EcommerceJob",
        "JSON_DOCUMENT",
        "MonitoringRun",
        "OfferObservation",
        "PriceObservation",
        "PriceObservationListing",
        "Product",
        "ProductSource",
        "SourceCaptureSnapshot",
        "SourceUrl",
        "SourceUrlCandidate",
        "SourceUrlDiscoveryRun",
        "SourceUrlDiscoveryTask",
        "Vendor",
        "VendorSourceCaptureRun",
    }

    assert model_package.__all__ == []
    assert [name for name in sorted(removed_exports) if hasattr(model_package, name)] == []
