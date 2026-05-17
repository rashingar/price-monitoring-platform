"""Ecommerce SQLAlchemy model registration.

Importing this package loads every workflow-owned model module so
``ecommerce.db.models.base.Base.metadata`` is complete for Alembic and metadata
consumers. Application code should import model classes from the concrete
workflow-owned model modules.
"""

# Import modules for metadata registration.
from . import alerts as alerts
from . import catalog as catalog
from . import jobs as jobs
from . import price_monitoring as price_monitoring
from . import products as products
from . import source_urls as source_urls
from . import vendor_sources as vendor_sources

__all__: list[str] = []
