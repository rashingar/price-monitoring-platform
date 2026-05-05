"""Repository-root import shim for the ``src`` layout.

This file lets ``python -m pricefetcher.dev.start`` work from the repository
root even when an editable install in ``.venv`` still points at an older parent
directory. The actual application package remains in ``src/pricefetcher``.
"""

from __future__ import annotations

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "pricefetcher"

if _SRC_PACKAGE.is_dir():
    __path__.insert(0, str(_SRC_PACKAGE))

__all__ = ["__version__"]

__version__ = "0.1.0"
