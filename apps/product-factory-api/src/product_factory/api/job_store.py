"""Compatibility shim for Product Factory job store imports.

Prefer importing from ``product_factory.jobs.store`` in new code.
"""

from __future__ import annotations

import sys

from product_factory.jobs import store as _store

sys.modules[__name__] = _store
