from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_BESTPRICE_STATUS = 1
DEFAULT_SKR_OUTZ_STATUS = 0
DEFAULT_BOXNOW_STATUS = 0

_TRUE_STRINGS = {"1", "true", "yes", "y", "enabled", "on"}
_FALSE_STRINGS = {"0", "false", "no", "n", "disabled", "off"}


def parse_status_value(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        if value in (0, 1):
            return value
        raise ValueError(f"{field_name} must be 0 or 1")
    if isinstance(value, float):
        if value in (0.0, 1.0):
            return int(value)
        raise ValueError(f"{field_name} must be 0 or 1")

    normalized = str(value or "").strip().casefold()
    if normalized in _TRUE_STRINGS:
        return 1
    if normalized in _FALSE_STRINGS:
        return 0
    raise ValueError(
        f"{field_name} must be one of 1/0, true/false, yes/no, or enabled/disabled"
    )


def status_or_default(value: Any, *, default: int, field_name: str) -> int:
    if value in (None, ""):
        return default
    return parse_status_value(value, field_name=field_name)


def status_from_payload(
    payload: Mapping[str, Any],
    *,
    key: str,
    default: int,
    legacy_key: str | None = None,
) -> int:
    if key in payload and payload.get(key) not in (None, ""):
        return status_or_default(payload.get(key), default=default, field_name=key)
    if legacy_key and legacy_key in payload and payload.get(legacy_key) not in (None, ""):
        return status_or_default(
            payload.get(legacy_key), default=default, field_name=legacy_key
        )
    return default
