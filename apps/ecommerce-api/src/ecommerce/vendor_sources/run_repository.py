"""Compatibility wrapper. Vendor Sources run repository helpers moved to ecommerce.db.repositories.vendor_sources.

New code should import from ``ecommerce.db.repositories.vendor_sources``.
"""

from ecommerce.db.repositories.vendor_sources import *  # noqa: F401,F403
