"""Database configuration helpers."""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from pricefetcher.env import load_local_env_if_present

DATABASE_URL_ENV_VAR = "PRICEFETCHER_DATABASE_URL"


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when a DB-backed feature is used without a configured database."""


def get_database_url() -> str | None:
    load_local_env_if_present()
    value = os.environ.get(DATABASE_URL_ENV_VAR)
    if value is None:
        return None
    text = value.strip()
    return text or None


def is_database_configured() -> bool:
    return get_database_url() is not None


def sanitize_database_url(database_url: str | None) -> str | None:
    if not database_url:
        return None
    try:
        parts = urlsplit(database_url)
    except ValueError:
        return "<invalid database url>"
    if not parts.password:
        return database_url
    username = parts.username or ""
    hostname = parts.hostname or ""
    netloc = f"{username}:***@{hostname}"
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def sanitize_database_error(message: object, database_url: str | None = None) -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    raw_url = database_url or get_database_url()
    sanitized_url = sanitize_database_url(raw_url)
    if raw_url and sanitized_url:
        text = text.replace(raw_url, sanitized_url)
        try:
            password = urlsplit(raw_url).password
        except ValueError:
            password = None
        if password:
            text = text.replace(password, "***")
    return text[:500]
