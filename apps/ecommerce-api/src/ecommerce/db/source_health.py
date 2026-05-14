"""Compatibility wrapper. Source health helpers moved to ecommerce.db.repositories.source_health.

New code should import from ``ecommerce.db.repositories.source_health``.
"""

from ecommerce.db.repositories.source_health import *  # noqa: F401,F403
