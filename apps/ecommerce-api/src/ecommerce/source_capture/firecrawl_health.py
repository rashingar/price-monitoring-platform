"""Firecrawl source capture health classification and escalation config."""

from __future__ import annotations

import os
from typing import Iterable

FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD_ENV = "ECOMMERCE_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD"
DEFAULT_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD = 2
MIN_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD = 1

FIRECRAWL_HEALTH_REASONS = (
    "firecrawl_api_key_missing",
    "firecrawl_timeout",
    "firecrawl_rate_limited",
    "firecrawl_blocked",
    "firecrawl_http_error",
    "firecrawl_parse_failed",
    "firecrawl_no_offers",
    "firecrawl_unknown_error",
)

FIRECRAWL_SOURCE_REVIEW_HEALTH_REASONS = frozenset(
    {
        "firecrawl_blocked",
        "firecrawl_parse_failed",
    }
)


def firecrawl_source_review_failure_threshold() -> int:
    raw = os.getenv(FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD_ENV, "").strip()
    if not raw:
        return DEFAULT_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD
    return max(MIN_FIRECRAWL_SOURCE_REVIEW_FAILURE_THRESHOLD, value)


def firecrawl_health_reason(
    *,
    vendor_slug: str | None = None,
    capture_strategy: str | None = None,
    error_code: str | None = None,
    response_status: int | None = None,
    data_quality_flags: Iterable[object] | None = None,
    error_message: str | None = None,
) -> str | None:
    flags = {_normalize(item) for item in data_quality_flags or [] if _normalize(item)}
    strategy = _normalize(capture_strategy)
    code = _normalize(error_code)
    message = _normalize(error_message)
    vendor = _normalize(vendor_slug)
    if vendor and vendor != "skroutz" and strategy != "skroutz_firecrawl":
        return None
    for reason in FIRECRAWL_HEALTH_REASONS:
        if reason in flags:
            return reason
    is_firecrawl = strategy == "skroutz_firecrawl" or code.startswith("firecrawl_") or any(
        flag.startswith("firecrawl_") for flag in flags
    )
    if not is_firecrawl and vendor != "skroutz":
        return None

    if code == "firecrawl_api_key_missing":
        return "firecrawl_api_key_missing"
    if code == "firecrawl_timeout":
        return "firecrawl_timeout"
    if code == "firecrawl_parse_failed":
        return "firecrawl_parse_failed"
    if "no_offer_observations_parsed" in flags:
        return "firecrawl_no_offers"

    if response_status == 429 or "rate_limit" in message or "rate limited" in message:
        return "firecrawl_rate_limited"
    if response_status in {401, 403, 423} or any(token in message for token in ("blocked", "captcha", "challenge", "forbidden")):
        return "firecrawl_blocked"
    if response_status is not None and response_status >= 400:
        return "firecrawl_http_error"
    if code in {"firecrawl_api_failed", "firecrawl_network_error"}:
        return "firecrawl_http_error" if code == "firecrawl_api_failed" else "firecrawl_unknown_error"
    if is_firecrawl:
        return "firecrawl_unknown_error"
    return None


def firecrawl_health_flags(
    *,
    vendor_slug: str | None = None,
    capture_strategy: str | None = None,
    error_code: str | None = None,
    response_status: int | None = None,
    data_quality_flags: Iterable[object] | None = None,
    error_message: str | None = None,
) -> list[str]:
    flags = [str(item) for item in data_quality_flags or [] if str(item or "").strip()]
    reason = firecrawl_health_reason(
        vendor_slug=vendor_slug,
        capture_strategy=capture_strategy,
        error_code=error_code,
        response_status=response_status,
        data_quality_flags=flags,
        error_message=error_message,
    )
    if reason and reason not in flags:
        flags.append(reason)
    return list(dict.fromkeys(flags))


def _normalize(value: object) -> str:
    return str(value or "").strip().lower()
