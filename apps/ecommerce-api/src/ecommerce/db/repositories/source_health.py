"""Product source health update helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from ecommerce.db.models.products import ProductSource, SourceCaptureSnapshot
from ecommerce.source_capture.firecrawl_health import firecrawl_health_flags
from ecommerce.source_capture.types import CaptureResult


def update_source_health(
    source: ProductSource, result: CaptureResult, snapshot: SourceCaptureSnapshot
) -> None:
    now = _now()
    source.last_seen_at = now
    source.last_fetch_status = result.status
    source.last_capture_strategy = snapshot.capture_strategy
    source.last_parser_version = snapshot.parser_version
    source.content_hash = snapshot.content_hash
    source.data_quality_flags = firecrawl_health_flags(
        vendor_slug=result.vendor_slug,
        capture_strategy=snapshot.capture_strategy,
        error_code=snapshot.error_code or result.error_code,
        response_status=snapshot.response_status,
        data_quality_flags=snapshot.data_quality_flags or [],
        error_message=snapshot.error_message or result.error_message,
    )
    if result.successful:
        source.last_success_at = now
        source.last_error_code = None
        source.last_error_message = None
        source.consecutive_failures = 0
    else:
        source.last_error_at = now
        source.last_error_code = result.error_code
        source.last_error_message = _short_text(result.error_message)
        source.consecutive_failures = int(source.consecutive_failures or 0) + 1
    source.updated_at = now


def _short_text(value: object, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
