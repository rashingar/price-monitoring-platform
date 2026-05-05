"""Optional database infrastructure for PriceFetcher."""

from pricefetcher.db.config import (
    DATABASE_URL_ENV_VAR,
    DatabaseNotConfiguredError,
    get_database_url,
    is_database_configured,
    sanitize_database_error,
    sanitize_database_url,
)
from pricefetcher.db.models import Base
from pricefetcher.db.session import check_database_reachable, get_engine, session_scope

__all__ = [
    "Base",
    "DATABASE_URL_ENV_VAR",
    "DatabaseNotConfiguredError",
    "check_database_reachable",
    "get_database_url",
    "get_engine",
    "is_database_configured",
    "sanitize_database_error",
    "sanitize_database_url",
    "session_scope",
]
