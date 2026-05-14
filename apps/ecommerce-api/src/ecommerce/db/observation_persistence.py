"""Compatibility wrapper. Observation persistence helpers moved to ecommerce.db.repositories.observation_persistence.

New code should import from ``ecommerce.db.repositories.observation_persistence``.
"""

from ecommerce.db.repositories.observation_persistence import *  # noqa: F401,F403
