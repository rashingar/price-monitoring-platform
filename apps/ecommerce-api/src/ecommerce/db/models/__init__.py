"""Ecommerce SQLAlchemy model registration and compatibility exports.

Importing this package loads every workflow-owned model module so
``Base.metadata`` is complete for Alembic and metadata consumers. New
application code should import model classes from the domain modules below.
"""

from ecommerce.db.models.base import Base, JSON_DOCUMENT

# Import modules for metadata registration.
from . import alerts as alerts
from . import catalog as catalog
from . import jobs as jobs
from . import price_monitoring as price_monitoring
from . import products as products
from . import source_urls as source_urls
from . import vendor_sources as vendor_sources

# Compatibility re-exports for existing callers; prefer domain module imports.
from ecommerce.db.models.alerts import AlertEvent, AlertRule
from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.jobs import EcommerceJob
from ecommerce.db.models.price_monitoring import (
    CatalogSnapshot,
    MonitoringRun,
    OfferObservation,
    PriceObservation,
    PriceObservationListing,
)
from ecommerce.db.models.products import Product, ProductSource, SourceCaptureSnapshot
from ecommerce.db.models.source_urls import SourceUrl, SourceUrlCandidate, SourceUrlDiscoveryRun, SourceUrlDiscoveryTask
from ecommerce.db.models.vendor_sources import Vendor, VendorSourceCaptureRun

__all__ = [
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
]
