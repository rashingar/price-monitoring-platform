"""Safe formatting helpers for platform health responses."""

from __future__ import annotations

import re

from ecommerce.platform_health.models import HealthStatus, PlatformHealthGroup, PlatformHealthLink


def safe_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)\b[a-z][a-z0-9+.-]*://[^@\s]+@[^/\s]+", "<redacted-connection-string>", text)
    return text[:500]


def list_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [safe_text(item) for item in value if safe_text(item)]


def unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def flag_detail(label: str, value: object) -> str:
    if value is True:
        state = "yes"
    elif value is False:
        state = "no"
    else:
        state = "unknown"
    return f"{label}: {state}."


def int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def group(
    group_id: str,
    label: str,
    status: HealthStatus,
    summary: str,
    *,
    details: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    warnings: list[str] | None = None,
    links: list[PlatformHealthLink] | None = None,
) -> PlatformHealthGroup:
    return PlatformHealthGroup(
        id=group_id,
        label=label,
        status=status,
        summary=safe_text(summary) or "No summary available.",
        details=[item for item in (safe_text(value) for value in (details or [])) if item],
        blocking_reasons=[item for item in (safe_text(value) for value in (blocking_reasons or [])) if item],
        warnings=[item for item in (safe_text(value) for value in (warnings or [])) if item],
        links=links or [],
    )


def link(label: str, url: str) -> PlatformHealthLink:
    return PlatformHealthLink(label=label, url=url)
