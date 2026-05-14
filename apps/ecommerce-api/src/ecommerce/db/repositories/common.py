"""Shared repository serialization and parsing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text.replace("EUR", "").replace("€", "").replace(" ", "").replace(",", "."))
    except Exception:
        return None


def _first_text(row: dict[str, Any], aliases: tuple[str, ...]) -> str:
    normalized = {_normalize_key(key): key for key in row.keys()}
    for alias in aliases:
        key = normalized.get(_normalize_key(alias))
        if key is not None:
            return str(row.get(key) or "").strip()
    return ""


def _normalize_key(value: object) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _empty_to_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def json_safe_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    return value


def _json_safe(row: dict[str, Any]) -> dict[str, Any]:
    return json_safe_value(dict(row))  # type: ignore[return-value]


def _now() -> datetime:
    return datetime.now(timezone.utc)
