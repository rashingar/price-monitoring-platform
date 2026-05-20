"""Error formatting helpers for Source URL Agent API routes."""

from __future__ import annotations

from ecommerce.db.config import sanitize_database_error


def safe_db_error(exc: Exception) -> str:
    message = (
        str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    )
    return sanitize_database_error(message) or exc.__class__.__name__
