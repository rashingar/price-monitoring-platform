from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ecommerce.source_capture.egress_policy import EgressPolicyError, validate_outbound_url
from ecommerce.source_capture.firecrawl_health import firecrawl_health_flags
from ecommerce.source_capture.parsing import parse_skroutz_firecrawl_content
from ecommerce.source_capture.sanitize import content_hash, sanitize_json
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload


CAPTURE_STRATEGY = "skroutz_firecrawl"
PARSER_VERSION = "skroutz_firecrawl_v1"
FIRECRAWL_API_KEY_MISSING = "FIRECRAWL_API_KEY_MISSING"
FIRECRAWL_API_FAILED = "FIRECRAWL_API_FAILED"
FIRECRAWL_NETWORK_ERROR = "FIRECRAWL_NETWORK_ERROR"
FIRECRAWL_PARSE_FAILED = "FIRECRAWL_PARSE_FAILED"
FIRECRAWL_TIMEOUT = "FIRECRAWL_TIMEOUT"

DEFAULT_FIRECRAWL_API_BASE_URL = "https://api.firecrawl.dev/v2"
DEFAULT_FIRECRAWL_TIMEOUT_SECONDS = 30.0
MAX_PERSISTED_TEXT_CHARS = 2_000
MAX_CONTENT_SAMPLE_CHARS = 500

CONTENT_KEYS = {"html", "rawhtml", "markdown", "text", "content"}
URL_KEYS = ("sourceURL", "sourceUrl", "url", "finalUrl", "finalURL", "requestedUrl")


def capture_skroutz_firecrawl(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_FIRECRAWL_TIMEOUT_SECONDS,
    transport: httpx.BaseTransport | None = None,
) -> CaptureResult:
    started = _now()
    started_monotonic = time.monotonic()
    api_endpoint = _firecrawl_scrape_endpoint()
    response_status: int | None = None
    response_content_type = ""
    payload: Any | None = None
    body_text = ""

    try:
        source_decision = validate_outbound_url(url, expected_vendor_slug="skroutz", require_known_vendor=True)
        validate_outbound_url(api_endpoint)
    except EgressPolicyError as exc:
        return _failed_result(
            url=url,
            error_code=exc.code,
            error_message=exc.message,
            started=started,
            request_url=api_endpoint,
        )

    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        return _failed_result(
            url=source_decision.url,
            error_code=FIRECRAWL_API_KEY_MISSING,
            error_message="FIRECRAWL_API_KEY is required for Skroutz production capture.",
            started=started,
            request_url=api_endpoint,
        )

    effective_timeout = _effective_timeout(timeout_seconds)
    request_body = {
        "url": source_decision.url,
        "formats": ["markdown", "html"],
        "onlyMainContent": False,
        "timeout": int(effective_timeout * 1000),
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(effective_timeout),
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "EcommerceSourceCapture/1.0",
            },
        ) as client:
            response = client.post(api_endpoint, json=request_body)
        fetched_at = _now()
        response_status = response.status_code
        response_content_type = response.headers.get("content-type", "")
        body_text = response.text
        payload = _json_or_none(body_text)
    except httpx.TimeoutException as exc:
        return _failed_result(
            url=source_decision.url,
            error_code=FIRECRAWL_TIMEOUT,
            error_message=str(exc) or "Firecrawl request timed out.",
            started=started,
            request_url=api_endpoint,
        )
    except httpx.HTTPError as exc:
        return _failed_result(
            url=source_decision.url,
            error_code=FIRECRAWL_NETWORK_ERROR,
            error_message=_short_message(str(exc) or exc.__class__.__name__),
            started=started,
            request_url=api_endpoint,
        )

    latency_ms = int((time.monotonic() - started_monotonic) * 1000)
    final_url = _extract_final_url(payload) or source_decision.url
    snapshot_base = {
        "url": source_decision.url,
        "final_url": final_url,
        "request_url": api_endpoint,
        "response_status": response_status,
        "response_content_type": response_content_type,
        "payload": payload,
        "body_text": body_text,
        "fetched_at": fetched_at,
        "latency_ms": latency_ms,
    }

    api_error = _api_error(payload, response_status)
    if api_error is not None:
        error_code, error_message = api_error
        return _failed_result(
            **snapshot_base,
            error_code=error_code,
            error_message=error_message,
            started=started,
        )

    content = _extract_content_text(payload)
    data = payload.get("data") if isinstance(payload, dict) else payload
    offers, price_observation, flags = parse_skroutz_firecrawl_content(content, page_url=final_url, data=data)
    parsed_at = _now()
    if offers:
        snapshot = _snapshot(
            **snapshot_base,
            started=started,
            data_quality_flags=flags,
            parsed_at=parsed_at,
            content_text=content,
        )
        return CaptureResult(vendor_slug="skroutz", status="success", snapshot=snapshot, offer_observations=tuple(offers))
    if price_observation is not None:
        snapshot = _snapshot(
            **snapshot_base,
            started=started,
            data_quality_flags=flags,
            parsed_at=parsed_at,
            content_text=content,
        )
        return CaptureResult(
            vendor_slug="skroutz",
            status="success",
            snapshot=snapshot,
            price_observations=(price_observation,),
        )

    return _failed_result(
        **snapshot_base,
        error_code=FIRECRAWL_PARSE_FAILED,
        error_message="Firecrawl returned content but no Skroutz offers or aggregate price were parsed.",
        started=started,
        data_quality_flags=[FIRECRAWL_PARSE_FAILED, *flags],
        parsed_at=parsed_at,
        content_text=content,
    )


def _snapshot(
    *,
    url: str,
    started: datetime,
    request_url: str | None = None,
    final_url: str | None = None,
    response_status: int | None = None,
    response_content_type: str | None = None,
    payload: Any | None = None,
    body_text: str | None = None,
    fetched_at: datetime | None = None,
    latency_ms: int | None = None,
    data_quality_flags: list[str] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    parsed_at: datetime | None = None,
    content_text: str | None = None,
) -> CaptureSnapshotPayload:
    del started
    fetched = fetched_at or _now()
    persisted_json = _bounded_firecrawl_payload(payload) if payload is not None else None
    return CaptureSnapshotPayload(
        capture_strategy=CAPTURE_STRATEGY,
        page_url=url,
        final_url=final_url,
        request_url=request_url,
        request_method="POST" if request_url else None,
        response_status=response_status,
        response_content_type=response_content_type,
        response_body_json=persisted_json if isinstance(persisted_json, (dict, list)) else None,
        response_body_text=_bounded_text(body_text) if persisted_json is None else None,
        content_hash=content_hash(content_text or body_text),
        parser_version=PARSER_VERSION,
        fetch_status_code=response_status,
        fetch_latency_ms=latency_ms,
        data_quality_flags=list(dict.fromkeys(data_quality_flags or ([] if error_code is None else [error_code]))),
        error_code=error_code,
        error_message=error_message,
        captured_at=fetched,
        fetched_at=fetched,
        parsed_at=parsed_at or _now(),
    )


def _failed_result(
    *,
    url: str,
    error_code: str,
    error_message: str,
    started: datetime,
    request_url: str | None = None,
    final_url: str | None = None,
    response_status: int | None = None,
    response_content_type: str | None = None,
    payload: Any | None = None,
    body_text: str | None = None,
    fetched_at: datetime | None = None,
    latency_ms: int | None = None,
    data_quality_flags: list[str] | None = None,
    parsed_at: datetime | None = None,
    content_text: str | None = None,
) -> CaptureResult:
    flags = firecrawl_health_flags(
        vendor_slug="skroutz",
        capture_strategy=CAPTURE_STRATEGY,
        error_code=error_code,
        response_status=response_status,
        data_quality_flags=data_quality_flags or [error_code],
        error_message=error_message,
    )
    return CaptureResult(
        vendor_slug="skroutz",
        status="failed",
        snapshot=_snapshot(
            url=url,
            started=started,
            request_url=request_url,
            final_url=final_url,
            response_status=response_status,
            response_content_type=response_content_type,
            payload=payload,
            body_text=body_text,
            fetched_at=fetched_at,
            latency_ms=latency_ms,
            data_quality_flags=flags,
            error_code=error_code,
            error_message=error_message,
            parsed_at=parsed_at,
            content_text=content_text,
        ),
        error_code=error_code,
        error_message=error_message,
    )


def _firecrawl_scrape_endpoint() -> str:
    base_url = os.getenv("FIRECRAWL_API_BASE_URL", DEFAULT_FIRECRAWL_API_BASE_URL).strip().rstrip("/")
    return f"{base_url}/scrape"


def _effective_timeout(timeout_seconds: float) -> float:
    configured = _float_env("FIRECRAWL_TIMEOUT_SECONDS", DEFAULT_FIRECRAWL_TIMEOUT_SECONDS)
    requested = timeout_seconds if timeout_seconds > 0 else DEFAULT_FIRECRAWL_TIMEOUT_SECONDS
    return max(1.0, min(configured, requested, 120.0))


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def _api_error(payload: Any, status_code: int | None) -> tuple[str, str] | None:
    if status_code is not None and status_code >= 400:
        return FIRECRAWL_API_FAILED, f"Firecrawl returned HTTP {status_code}: {_payload_message(payload)}"
    if isinstance(payload, dict) and payload.get("success") is False:
        return FIRECRAWL_API_FAILED, _payload_message(payload)
    return None


def _payload_message(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("error", "message", "details"):
            value = payload.get(key)
            if value:
                return _short_message(str(value))
    return "Firecrawl request failed."


def _extract_content_text(payload: Any) -> str:
    parts: list[str] = []
    for value in _walk_json(payload):
        if not isinstance(value, dict):
            continue
        normalized = {str(key).casefold().replace("_", ""): item for key, item in value.items()}
        for key in ("markdown", "html", "rawhtml", "text", "content"):
            item = normalized.get(key)
            if isinstance(item, str) and item.strip():
                parts.append(item)
    return "\n\n".join(dict.fromkeys(parts))


def _extract_final_url(payload: Any) -> str | None:
    for node in _walk_json(payload):
        if not isinstance(node, dict):
            continue
        for key in URL_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return None


def _bounded_firecrawl_payload(payload: Any) -> Any:
    bounded = _bound_json(payload)
    return sanitize_json(bounded)


def _bound_json(value: Any) -> Any:
    if isinstance(value, dict):
        bounded: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold().replace("_", "")
            if normalized in CONTENT_KEYS and isinstance(item, str):
                bounded[str(key)] = {
                    "length": len(item),
                    "content_hash": content_hash(item),
                    "sample": _bounded_text(item, limit=MAX_CONTENT_SAMPLE_CHARS),
                }
                continue
            bounded[str(key)] = _bound_json(item)
        return bounded
    if isinstance(value, list):
        return [_bound_json(item) for item in value[:20]]
    if isinstance(value, str):
        return _bounded_text(value)
    return value


def _bounded_text(value: str | None, *, limit: int = MAX_PERSISTED_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    single_line = " ".join(value.split())
    if len(single_line) <= limit:
        return single_line
    return f"{single_line[: limit - 3]}..."


def _json_or_none(text: str) -> Any | None:
    if not text:
        return None
    try:
        return httpx.Response(200, text=text).json()
    except ValueError:
        return None


def _walk_json(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _short_message(message: str, *, limit: int = 240) -> str:
    single_line = " ".join(message.split())
    if len(single_line) <= limit:
        return single_line
    return f"{single_line[: limit - 3]}..."


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
