"""Compatibility wrapper. Capture persistence helpers moved to ecommerce.db.repositories.capture_persistence.

New code should import from ``ecommerce.db.repositories.capture_persistence``.
"""

from ecommerce.db.repositories.capture_persistence import *  # noqa: F401,F403
