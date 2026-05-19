"""Exceptions for Product Factory source resolution."""

from __future__ import annotations


class SourceResolutionError(RuntimeError):
    """Raised when source resolution cannot safely run."""
