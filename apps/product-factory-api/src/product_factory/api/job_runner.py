"""Compatibility shim for Product Factory job runner imports.

Prefer importing from ``product_factory.jobs.runner`` in new code.
"""

from __future__ import annotations

import sys

from product_factory.jobs import runner as _runner

sys.modules[__name__] = _runner
