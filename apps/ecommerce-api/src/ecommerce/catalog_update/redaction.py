"""Redaction helpers shared by catalog update modules."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ecommerce.catalog_update.paths import display_path
from ecommerce.catalog_update.types import CatalogUpdateConfig
from ecommerce.db.config import sanitize_database_error

REDACTED_VALUE = "[redacted]"
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "auth",
    "authorization",
    "cookie",
    "key",
    "password",
    "pass",
    "passwd",
    "pwd",
    "refresh_token",
    "secret",
    "session",
    "sessionid",
    "sid",
    "token",
    "user",
    "username",
    "user_token",
}


def redact_opencart_url(
    value: object, config: CatalogUpdateConfig | None = None
) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return redact_opencart_sensitive_data(text, config)
    if not parsed.scheme or not parsed.netloc:
        return redact_opencart_sensitive_data(text, config)

    query_items = [
        (
            key,
            (
                REDACTED_VALUE
                if is_sensitive_query_key(key)
                else redact_opencart_sensitive_data(value, config)
            ),
        )
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return redact_opencart_sensitive_data(
        urlunparse(parsed._replace(query=urlencode(query_items))), config
    )


def redact_opencart_sensitive_data(
    value: object, config: CatalogUpdateConfig | None = None
) -> str:
    text = str(value or "")
    if not text:
        return ""
    sensitive_values = {
        os.environ.get("OPENCART_ADMIN_PASS", ""),
        os.environ.get("OPENCART_ADMIN_USER", ""),
    }
    if config is not None:
        sensitive_values.update({config.admin_pass, config.admin_user})
    for secret in sorted(
        (item for item in sensitive_values if item), key=len, reverse=True
    ):
        text = text.replace(secret, REDACTED_VALUE)
    text = re.sub(
        r"(?i)\b(user_token|access_token|refresh_token|token|password|passwd|pwd|pass|cookie|secret|authorization)=([^&\s]+)",
        lambda match: f"{match.group(1)}={REDACTED_VALUE}",
        text,
    )
    return text


def sanitize_progress_details(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        normalized_key = str(key)
        if is_sensitive_query_key(normalized_key):
            continue
        sanitized_value = sanitize_progress_value(value)
        if sanitized_value is not None:
            sanitized[normalized_key] = sanitized_value
    return sanitized


def sanitize_progress_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return (
            redact_opencart_url(value)
            if "://" in value
            else redact_opencart_sensitive_data(value)
        )
    if isinstance(value, Path):
        return display_path(value)
    if isinstance(value, dict):
        nested = sanitize_progress_details(value)
        return nested if nested else None
    if isinstance(value, (list, tuple)):
        items = [sanitize_progress_value(item) for item in value[:20]]
        return [item for item in items if item is not None]
    return redact_opencart_sensitive_data(str(value))


def sanitize_output(value: object, database_url: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return sanitize_database_error(text, database_url)[:4000]


def is_sensitive_query_key(key: str) -> bool:
    normalized = key.strip().casefold()
    return normalized in SENSITIVE_QUERY_KEYS or any(
        part in normalized for part in ("token", "password", "cookie", "secret")
    )
