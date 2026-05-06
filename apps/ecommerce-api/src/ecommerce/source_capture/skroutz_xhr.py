from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from ecommerce.source_capture.parsing import parse_skroutz_offers, parse_skroutz_price_summary
from ecommerce.source_capture.sanitize import content_hash, sanitize_json
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload


DIRECT_JSON_STRATEGY = "skroutz_direct_json_endpoints"
FILTER_PRODUCTS_ACTION = "skroutz_filter_products_fetch"
SHOPS_DETAILS_ACTION = "skroutz_shops_details_fetch"
DIRECT_ENDPOINT_UNAVAILABLE = "direct_endpoint_unavailable"
XHR_PARSE_FAILED = "xhr_parse_failed"
BLOCKED_OR_CAPTCHA = "blocked_or_captcha"
TIMEOUT = "timeout"
INVALID_SKROUTZ_PRODUCT_URL = "invalid_skroutz_product_url"

PARSER_VERSION = "skroutz_filter_products_v1"
SHOPS_DETAILS_UNAVAILABLE_FLAG = "shops_details_unavailable"

HTTP_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


@dataclass(frozen=True)
class _EndpointResponse:
    url: str
    method: str
    status: int | None
    content_type: str
    body_text: str
    body_json: Any | None
    fetched_at: datetime
    latency_ms: int
    trigger_action: str
    final_url: str | None = None


class _EndpointUnavailable(Exception):
    pass


def capture_skroutz_xhr(url: str, *, timeout_seconds: float) -> CaptureResult:
    started = _now()
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    endpoint_urls = _direct_endpoint_urls(url)
    if endpoint_urls is None:
        return _failed_result(
            url=url,
            error_code=INVALID_SKROUTZ_PRODUCT_URL,
            error_message="Skroutz product URL must contain path segment /s/{digits}.",
            started=started,
        )

    filter_url, shops_url = endpoint_urls

    try:
        filter_response = _fetch_with_budget(
            filter_url,
            action=FILTER_PRODUCTS_ACTION,
            deadline=deadline,
        )
    except TimeoutError as exc:
        return _failed_result(
            url=url,
            error_code=TIMEOUT,
            error_message=str(exc) or exc.__class__.__name__,
            started=started,
            request_url=filter_url,
            trigger_action=FILTER_PRODUCTS_ACTION,
        )
    except _EndpointUnavailable as exc:
        return _failed_result(
            url=url,
            error_code=DIRECT_ENDPOINT_UNAVAILABLE,
            error_message=str(exc) or exc.__class__.__name__,
            started=started,
            request_url=filter_url,
            trigger_action=FILTER_PRODUCTS_ACTION,
        )

    if _looks_blocked_response(filter_response):
        return _blocked_result(url=url, response=filter_response, started=started)
    if not _is_success_status(filter_response.status):
        return _failed_from_response(
            url=url,
            response=filter_response,
            error_code=DIRECT_ENDPOINT_UNAVAILABLE,
            error_message=f"Skroutz direct endpoint returned HTTP {filter_response.status}.",
            started=started,
        )

    shops_response: _EndpointResponse | None = None
    shops_unavailable = False
    if _should_fetch_shops_details(filter_response.body_json):
        try:
            shops_response = _fetch_with_budget(
                shops_url,
                action=SHOPS_DETAILS_ACTION,
                deadline=deadline,
            )
            if _looks_blocked_response(shops_response):
                return _blocked_result(url=url, response=shops_response, started=started)
            if not _is_success_status(shops_response.status):
                shops_unavailable = True
                shops_response = None
        except TimeoutError as exc:
            return _failed_result(
                url=url,
                error_code=TIMEOUT,
                error_message=str(exc) or exc.__class__.__name__,
                started=started,
                request_url=shops_url,
                trigger_action=SHOPS_DETAILS_ACTION,
            )
        except _EndpointUnavailable:
            shops_unavailable = True

    offers, offer_flags = parse_skroutz_offers(
        filter_response.body_json if filter_response.body_json is not None else filter_response.body_text,
        shops_payload=shops_response.body_json if shops_response is not None else None,
    )
    data_quality_flags = list(offer_flags)
    if shops_unavailable and offers:
        data_quality_flags.append(SHOPS_DETAILS_UNAVAILABLE_FLAG)
    parsed_at = _now()

    if offers:
        return CaptureResult(
            vendor_slug="skroutz",
            status="success",
            snapshot=_snapshot(
                url=url,
                response=filter_response,
                started=started,
                parser_version=PARSER_VERSION,
                data_quality_flags=data_quality_flags,
                parsed_at=parsed_at,
            ),
            offer_observations=tuple(offers),
        )

    price_observation, summary_flags = parse_skroutz_price_summary(
        filter_response.body_json if filter_response.body_json is not None else filter_response.body_text,
        page_url=url,
    )
    if price_observation is not None:
        return CaptureResult(
            vendor_slug="skroutz",
            status="success",
            snapshot=_snapshot(
                url=url,
                response=filter_response,
                started=started,
                parser_version=PARSER_VERSION,
                data_quality_flags=summary_flags,
                parsed_at=parsed_at,
            ),
            price_observations=(price_observation,),
        )

    return _failed_from_response(
        url=url,
        response=filter_response,
        error_code=XHR_PARSE_FAILED,
        error_message="Skroutz direct JSON was fetched but no offers or aggregate price were parsed.",
        started=started,
        data_quality_flags=[XHR_PARSE_FAILED, *offer_flags, *summary_flags],
        parsed_at=parsed_at,
    )


def _fetch_with_budget(url: str, *, action: str, deadline: float) -> _EndpointResponse:
    timeout_seconds = _remaining_seconds(deadline)
    response = _fetch_endpoint(url, timeout_seconds=timeout_seconds, action=action)
    if time.monotonic() > deadline:
        raise TimeoutError("Skroutz capture exceeded the overall timeout budget.")
    return response


def _fetch_endpoint(url: str, *, timeout_seconds: float, action: str) -> _EndpointResponse:
    started = time.monotonic()
    request = Request(url, headers=HTTP_HEADERS, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body_bytes = response.read()
            final_url = response.geturl()
            status = getattr(response, "status", None) or response.getcode()
            content_type = response.headers.get("content-type", "")
    except HTTPError as exc:
        body_bytes = exc.read()
        final_url = exc.geturl()
        status = exc.code
        content_type = exc.headers.get("content-type", "") if exc.headers is not None else ""
    except (TimeoutError, socket.timeout) as exc:
        raise TimeoutError(str(exc) or exc.__class__.__name__) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise TimeoutError(str(reason) or reason.__class__.__name__) from exc
        raise _EndpointUnavailable(str(reason) or exc.__class__.__name__) from exc
    except OSError as exc:
        raise _EndpointUnavailable(str(exc) or exc.__class__.__name__) from exc

    body_text = body_bytes.decode("utf-8", errors="replace")
    return _EndpointResponse(
        url=url,
        method="GET",
        status=_int_or_none(status),
        content_type=content_type,
        body_text=body_text,
        body_json=_json_or_none(body_text),
        fetched_at=_now(),
        latency_ms=int((time.monotonic() - started) * 1000),
        trigger_action=action,
        final_url=final_url,
    )


def _direct_endpoint_urls(source_url: str) -> tuple[str, str] | None:
    parsed = urlparse(source_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    product_id = _product_id_from_path(parsed.path)
    if product_id is None:
        return None
    base = (parsed.scheme, parsed.netloc, "", "", "", "")
    filter_url = urlunparse((*base[:2], f"/s/{product_id}/filter_products.json", "", "", ""))
    shops_url = urlunparse((*base[:2], f"/s/{product_id}/shops_details.json", "", "", ""))
    return filter_url, shops_url


def _product_id_from_path(path: str) -> str | None:
    segments = [segment for segment in (path or "").split("/") if segment]
    for index, segment in enumerate(segments):
        if segment == "s" and index + 1 < len(segments) and segments[index + 1].isdigit():
            return segments[index + 1]
    return None


def _should_fetch_shops_details(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("product_cards"), list) and bool(payload["product_cards"])


def _snapshot(
    *,
    url: str,
    response: _EndpointResponse,
    started: datetime,
    parser_version: str | None = None,
    data_quality_flags: list[str] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    parsed_at: datetime | None = None,
) -> CaptureSnapshotPayload:
    json_payload = sanitize_json(response.body_json) if isinstance(response.body_json, (dict, list)) else None
    return CaptureSnapshotPayload(
        capture_strategy=DIRECT_JSON_STRATEGY,
        page_url=url,
        final_url=response.final_url,
        request_url=response.url,
        request_method=response.method,
        response_status=response.status,
        response_content_type=response.content_type,
        response_body_json=json_payload,
        response_body_text=response.body_text if json_payload is None else None,
        content_hash=content_hash(response.body_text),
        parser_version=parser_version,
        fetch_latency_ms=int((response.fetched_at - started).total_seconds() * 1000) + response.latency_ms,
        trigger_action=response.trigger_action,
        data_quality_flags=list(dict.fromkeys(data_quality_flags or [])),
        error_code=error_code,
        error_message=error_message,
        captured_at=response.fetched_at,
        fetched_at=response.fetched_at,
        parsed_at=parsed_at or _now(),
    )


def _blocked_result(*, url: str, response: _EndpointResponse, started: datetime) -> CaptureResult:
    message = "Skroutz returned an anti-bot, captcha, or challenge response."
    snapshot = _snapshot(
        url=url,
        response=response,
        started=started,
        parser_version=PARSER_VERSION,
        data_quality_flags=[BLOCKED_OR_CAPTCHA],
        error_code=BLOCKED_OR_CAPTCHA,
        error_message=message,
    )
    return CaptureResult(
        vendor_slug="skroutz",
        status="failed",
        snapshot=snapshot,
        error_code=BLOCKED_OR_CAPTCHA,
        error_message=message,
    )


def _failed_from_response(
    *,
    url: str,
    response: _EndpointResponse,
    error_code: str,
    error_message: str,
    started: datetime,
    data_quality_flags: list[str] | None = None,
    parsed_at: datetime | None = None,
) -> CaptureResult:
    flags = data_quality_flags or [error_code]
    snapshot = _snapshot(
        url=url,
        response=response,
        started=started,
        parser_version=PARSER_VERSION,
        data_quality_flags=flags,
        error_code=error_code,
        error_message=error_message,
        parsed_at=parsed_at,
    )
    return CaptureResult(
        vendor_slug="skroutz",
        status="failed",
        snapshot=snapshot,
        error_code=error_code,
        error_message=error_message,
    )


def _failed_result(
    *,
    url: str,
    error_code: str,
    error_message: str,
    started: datetime,
    request_url: str | None = None,
    response_status: int | None = None,
    response_content_type: str | None = None,
    response_body_text: str | None = None,
    trigger_action: str | None = None,
) -> CaptureResult:
    now = _now()
    del started
    return CaptureResult(
        vendor_slug="skroutz",
        status="failed",
        snapshot=CaptureSnapshotPayload(
            capture_strategy=DIRECT_JSON_STRATEGY,
            page_url=url,
            request_url=request_url,
            request_method="GET" if request_url else None,
            response_status=response_status,
            response_content_type=response_content_type,
            response_body_text=response_body_text,
            content_hash=content_hash(response_body_text),
            trigger_action=trigger_action,
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


def _looks_blocked_response(response: _EndpointResponse) -> bool:
    body = (response.body_text or "").lower()
    final_url = (response.final_url or response.url or "").lower()
    return (
        response.status in {401, 403, 429}
        or "just a moment" in body
        or "cloudflare" in body and ("challenge" in body or "captcha" in body)
        or "cf-chl" in body
        or "g-recaptcha" in body
        or "captcha" in body
        or "challenge-platform" in final_url
    )


def _is_success_status(status: int | None) -> bool:
    return status is None or 200 <= status < 300


def _json_or_none(text: str) -> Any | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Skroutz capture exceeded the overall timeout budget.")
    return remaining


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
