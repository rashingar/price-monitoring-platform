"""Compatibility shim for Product Factory job model imports.

Prefer importing from ``product_factory.jobs.models`` in new code.
"""

from __future__ import annotations

import sys

from product_factory.jobs import models as _models

sys.modules[__name__] = _models
