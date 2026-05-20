from __future__ import annotations

from datetime import datetime, timezone

from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_capture.egress_policy import (
    EgressPolicyError,
    EgressTimeoutConfig,
    safe_get,
    validate_outbound_url,
)
from ecommerce.source_capture.parsing import (
    parse_bestprice_html,
    parse_bestprice_offers,
    parse_electronet_html,
)
from ecommerce.source_capture.sanitize import content_hash
from ecommerce.source_capture.skroutz_firecrawl import capture_skroutz_firecrawl
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload

CAPTURE_IMPLEMENTED_VENDOR_SLUGS = frozenset({"bestprice", "electronet", "skroutz"})


class CaptureError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def capture_source_url(
    url: str, *, vendor_slug: str | None = None, timeout_seconds: float = 30.0
) -> CaptureResult:
    resolved_vendor = vendor_slug or detect_vendor_slug(url)
    if not resolved_vendor:
        return _failed_result(
            "unknown", url, "UNKNOWN_VENDOR", "Source URL host is not registered."
        )
    try:
        validate_outbound_url(
            url, expected_vendor_slug=resolved_vendor, require_known_vendor=True
        )
    except EgressPolicyError as exc:
        return _failed_result(resolved_vendor, url, exc.code, exc.message)
    if resolved_vendor == "electronet":
        return _capture_electronet(url, timeout_seconds=timeout_seconds)
    if resolved_vendor == "bestprice":
        return _capture_bestprice(url, timeout_seconds=timeout_seconds)
    if resolved_vendor == "skroutz":
        return capture_skroutz_firecrawl(url, timeout_seconds=timeout_seconds)
    return _failed_result(
        resolved_vendor,
        url,
        "VENDOR_NOT_IMPLEMENTED",
        f"{resolved_vendor} capture is scaffolded but not implemented.",
    )


def _capture_electronet(url: str, *, timeout_seconds: float) -> CaptureResult:
    started = _now()
    status_code: int | None = None
    content_type = ""
    try:
        response = safe_get(
            url,
            expected_vendor_slug="electronet",
            require_known_vendor=True,
            timeout=EgressTimeoutConfig(
                connect=min(timeout_seconds, 5.0),
                read=timeout_seconds,
                total=timeout_seconds,
            ),
        )
        fetched_at = _now()
        status_code = response.status_code
        content_type = response.headers.get("content-type", "")
        html = response.text
        parsed, flags = parse_electronet_html(html, page_url=response.final_url)
        parsed_at = _now()
        latency_ms = int((fetched_at - started).total_seconds() * 1000)
        snapshot = CaptureSnapshotPayload(
            capture_strategy="electronet_httpx_html",
            page_url=url,
            final_url=response.final_url,
            request_url=url,
            request_method="GET",
            response_status=response.status_code,
            response_content_type=content_type,
            raw_html=html,
            content_hash=content_hash(html),
            parser_version="electronet_html_v1",
            fetch_status_code=response.status_code,
            fetch_latency_ms=latency_ms,
            data_quality_flags=flags,
            captured_at=fetched_at,
            fetched_at=fetched_at,
            parsed_at=parsed_at,
        )
        if status_code >= 400:
            return CaptureResult(
                vendor_slug="electronet",
                status="failed",
                snapshot=snapshot,
                error_code="FETCH_FAILED",
                error_message=f"Electronet returned HTTP {status_code}.",
            )
        return CaptureResult(
            vendor_slug="electronet",
            status="success",
            snapshot=snapshot,
            price_observations=(parsed,) if parsed.price is not None else (),
            error_code=None if parsed.price is not None else "PRICE_MISSING",
            error_message=(
                None
                if parsed.price is not None
                else "Electronet parser did not find a price."
            ),
        )
    except Exception as exc:
        error_code = exc.code if isinstance(exc, EgressPolicyError) else "FETCH_FAILED"
        error_message = (
            exc.message
            if isinstance(exc, EgressPolicyError)
            else (str(exc) or exc.__class__.__name__)
        )
        return _failed_result(
            "electronet",
            url,
            error_code,
            error_message,
            capture_strategy="electronet_httpx_html",
            response_status=status_code,
            response_content_type=content_type,
        )


def _capture_bestprice(url: str, *, timeout_seconds: float) -> CaptureResult:
    started = _now()
    status_code: int | None = None
    content_type = ""
    try:
        response = safe_get(
            url,
            expected_vendor_slug="bestprice",
            require_known_vendor=True,
            timeout=EgressTimeoutConfig(
                connect=min(timeout_seconds, 5.0),
                read=timeout_seconds,
                total=timeout_seconds,
            ),
            headers={
                "User-Agent": "EcommerceSourceCapture/1.0",
                "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
            },
        )
        fetched_at = _now()
        status_code = response.status_code
        content_type = response.headers.get("content-type", "")
        html = response.text
        parsed, flags = parse_bestprice_html(html, page_url=response.final_url)
        offers, offer_flags = parse_bestprice_offers(html, page_url=response.final_url)
        flags.extend(flag for flag in offer_flags if flag not in flags)
        parsed_at = _now()
        latency_ms = int((fetched_at - started).total_seconds() * 1000)
        snapshot = CaptureSnapshotPayload(
            capture_strategy="bestprice_httpx_html",
            page_url=url,
            final_url=response.final_url,
            request_url=url,
            request_method="GET",
            response_status=response.status_code,
            response_content_type=content_type,
            raw_html=html,
            content_hash=content_hash(html),
            parser_version="bestprice_html_v1",
            fetch_status_code=response.status_code,
            fetch_latency_ms=latency_ms,
            data_quality_flags=flags,
            captured_at=fetched_at,
            fetched_at=fetched_at,
            parsed_at=parsed_at,
        )
        if status_code >= 400:
            return CaptureResult(
                vendor_slug="bestprice",
                status="failed",
                snapshot=snapshot,
                error_code="FETCH_FAILED",
                error_message=f"BestPrice returned HTTP {status_code}.",
            )
        return CaptureResult(
            vendor_slug="bestprice",
            status="success",
            snapshot=snapshot,
            price_observations=(parsed,) if parsed.price is not None else (),
            offer_observations=tuple(offers),
            error_code=None if parsed.price is not None else "PRICE_MISSING",
            error_message=(
                None
                if parsed.price is not None
                else "BestPrice parser did not find a price."
            ),
        )
    except Exception as exc:
        error_code = exc.code if isinstance(exc, EgressPolicyError) else "FETCH_FAILED"
        error_message = (
            exc.message
            if isinstance(exc, EgressPolicyError)
            else (str(exc) or exc.__class__.__name__)
        )
        return _failed_result(
            "bestprice",
            url,
            error_code,
            error_message,
            capture_strategy="bestprice_httpx_html",
            response_status=status_code,
            response_content_type=content_type,
        )


def _failed_result(
    vendor_slug: str,
    url: str,
    error_code: str,
    error_message: str,
    *,
    capture_strategy: str = "unsupported",
    response_status: int | None = None,
    response_content_type: str | None = None,
) -> CaptureResult:
    now = _now()
    return CaptureResult(
        vendor_slug=vendor_slug,
        status="failed",
        snapshot=CaptureSnapshotPayload(
            capture_strategy=capture_strategy,
            page_url=url,
            response_status=response_status,
            response_content_type=response_content_type,
            data_quality_flags=[error_code],
            error_code=error_code,
            error_message=error_message,
            captured_at=now,
            fetched_at=now,
            parsed_at=now,
        ),
        error_code=error_code,
        error_message=error_message,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
