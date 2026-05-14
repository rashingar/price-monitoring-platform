"""Compatibility wrapper. Product source repository helpers moved to ecommerce.db.repositories.products.

New code should import from ``ecommerce.db.repositories.products``.
"""

from ecommerce.db.repositories.products import *  # noqa: F401,F403
