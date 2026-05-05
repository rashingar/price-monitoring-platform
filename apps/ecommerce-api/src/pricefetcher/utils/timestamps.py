"""Timestamp helpers for Greece-local output fields."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

GREECE_TIMEZONE = ZoneInfo("Europe/Athens")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_greece() -> datetime:
    return datetime.now(tz=GREECE_TIMEZONE)


def format_greece_timestamp(value: datetime | None = None) -> str:
    timestamp = value or now_greece()
    return timestamp.astimezone(GREECE_TIMEZONE).strftime(TIMESTAMP_FORMAT)
