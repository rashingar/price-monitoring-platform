"""Compatibility wrapper. Alert repository helpers moved to ecommerce.db.repositories.alerts.

New code should import from ``ecommerce.db.repositories.alerts``.
"""

from ecommerce.db.repositories.alerts import *  # noqa: F401,F403
