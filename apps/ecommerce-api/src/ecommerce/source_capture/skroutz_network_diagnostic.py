"""Browser-assisted Skroutz network diagnostics.

This module is an explicit operator diagnostic path. It captures sanitized
network response summaries from a browser session; it does not create price
observations or change normal capture strategy.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ecommerce.source_capture.sanitize import sanitize_json

PRIMARY_CANDIDATE_PRODUCT_OFFERS = "PRIMARY_CANDIDATE_PRODUCT_OFFERS"
SECONDARY_CANDIDATE_SHOP_DETAILS = "SECONDARY_CANDIDATE_SHOP_DETAILS"
POSSIBLE_PRODUCT_OR_OFFER_DATA = "POSSIBLE_PRODUCT_OR_OFFER_DATA"
POSSIBLE_REVIEWS_OR_RATING_DATA = "POSSIBLE_REVIEWS_OR_RATING_DATA"
POSSIBLE_RECOMMENDATIONS = "POSSIBLE_RECOMMENDATIONS"
OTHER_JSON = "OTHER_JSON"
BLOCKED_OR_CHALLENGE = "BLOCKED_OR_CHALLENGE"
NON_JSON_XHR = "NON_JSON_XHR"

CAPTURE_STRATEGY = "skroutz_browser_network_diagnostic"
MAX_BODY_SAMPLE_CHARS = 1000
MAX_SUMMARY_KEYS = 40
MAX_PARSE_BYTES = 2_000_000
SENSITIVE_QUERY_PARAMS = {"token", "csrf", "session", "sig", "signature", "key", "auth", "authorization"}

OFFER_KEY_MARKERS = ("price", "offer", "shop", "seller", "availability", "stock", "shipping", "merchant")
REVIEW_KEY_MARKERS = ("review", "rating", "ratings", "stars", "score")
RECOMMENDATION_KEY_MARKERS = ("recommend", "recommendation", "similar", "related")
BLOCKED_MARKERS = (
    "captcha",
    "cloudflare",
    "cf-chl",
    "just a moment",
    "challenge",
    "blocked",
    "access denied",
    "are you human",
)


class PlaywrightUnavailableError(RuntimeError):
    """Raised when the optional Playwright dependency/browser is unavailable."""


@dataclass(frozen=True)
class SkroutzNetworkCapturedResponse:
    method: str
    url: str
    status: int | None
    resource_type: str
    content_type: str
    body_size: int
    parsed_json_valid: bool
    json_summary: dict[str, Any]
    classification: str
    matched_derived_endpoint: str | None
    body_sample: str
    json_parse_error: str | None = None


@dataclass(frozen=True)
class SkroutzNetworkDiagnosticReport:
    source_url: str
    status: str
    started_at: str
    completed_at: str
    timeout_seconds: int
    headed: bool
    derived_endpoints: dict[str, str]
    captured_responses: list[SkroutzNetworkCapturedResponse] = field(default_factory=list)
    observed_filter_products_url: bool = False
    observed_shops_details_url: bool = False
    exact_match_count: int = 0
    product_data_candidate_url: str | None = None
    product_data_candidate_reason: str | None = None
    classifications_summary: dict[str, int] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_skroutz_product_id(url: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    segments = [segment for segment in parsed.path.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment == "s" and index + 1 < len(segments) and segments[index + 1].isdigit():
            return segments[index + 1]
    return None


def derived_skroutz_endpoint_urls(url: str) -> dict[str, str]:
    product_id = extract_skroutz_product_id(url)
    if product_id is None:
        return {}
    return {
        "filter_products": f"https://www.skroutz.gr/s/{product_id}/filter_products.json",
        "shops_details": f"https://www.skroutz.gr/s/{product_id}/shops_details.json",
    }


def classify_skroutz_network_endpoint(url: str, payload: object | None, body_text: str) -> str:
    lowered_url = str(url or "").lower()
    lowered_body = str(body_text or "").lower()
    if _looks_blocked(lowered_body, lowered_url):
        return BLOCKED_OR_CHALLENGE
    if "filter_products" in lowered_url:
        return PRIMARY_CANDIDATE_PRODUCT_OFFERS
    if "shops_details" in lowered_url:
        return SECONDARY_CANDIDATE_SHOP_DETAILS
    if isinstance(payload, dict) and isinstance(payload.get("product_cards"), list):
        return PRIMARY_CANDIDATE_PRODUCT_OFFERS
    if _payload_has_key_marker(payload, OFFER_KEY_MARKERS):
        return POSSIBLE_PRODUCT_OR_OFFER_DATA
    if _payload_has_key_marker(payload, REVIEW_KEY_MARKERS):
        return POSSIBLE_REVIEWS_OR_RATING_DATA
    if _payload_has_key_marker(payload, RECOMMENDATION_KEY_MARKERS):
        return POSSIBLE_RECOMMENDATIONS
    if payload is None:
        return NON_JSON_XHR
    return OTHER_JSON


def sanitize_diagnostic_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.strip().lower() in SENSITIVE_QUERY_PARAMS:
            query_pairs.append((key, "[REDACTED]"))
        else:
            query_pairs.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(query_pairs, doseq=True)))


def run_skroutz_network_diagnostic(
    source_url: str,
    *,
    timeout_seconds: int = 60,
    headed: bool = False,
) -> SkroutzNetworkDiagnosticReport:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment dependent
        raise PlaywrightUnavailableError("Playwright is not installed for ecommerce-api.") from exc

    started = _now()
    safe_timeout_seconds = max(5, min(int(timeout_seconds), 180))
    derived = derived_skroutz_endpoint_urls(source_url)
    captured: list[SkroutzNetworkCapturedResponse] = []
    browser = None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not headed)
            context = browser.new_context(locale="el-GR")
            page = context.new_page()

            def on_response(response: Any) -> None:
                try:
                    request = response.request
                    resource_type = str(request.resource_type or "")
                    content_type = str(response.headers.get("content-type", ""))
                    response_url = str(response.url or "")
                    if not _should_capture_response(response_url, content_type, resource_type):
                        return
                    captured.append(_response_summary(response, derived))
                except Exception:
                    return

            page.on("response", on_response)
            timeout_ms = safe_timeout_seconds * 1000
            try:
                page.goto(source_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10_000))
            except PlaywrightTimeoutError:
                pass
            _trigger_lazy_requests(page, PlaywrightError)
            try:
                page.wait_for_timeout(1000)
            except PlaywrightError:
                pass
            context.close()
            browser.close()
            browser = None
        return _build_report(
            source_url=source_url,
            started_at=started,
            timeout_seconds=safe_timeout_seconds,
            headed=headed,
            derived=derived,
            captured=captured,
            status="success",
        )
    except PlaywrightError as exc:  # pragma: no cover - depends on local browser installation
        message = str(exc).strip() or exc.__class__.__name__
        if "Executable doesn't exist" in message or "playwright install" in message:
            raise PlaywrightUnavailableError("Playwright Chromium is not installed. Run: python -m playwright install chromium") from exc
        return _build_report(
            source_url=source_url,
            started_at=started,
            timeout_seconds=safe_timeout_seconds,
            headed=headed,
            derived=derived,
            captured=captured,
            status="failed",
            error_code="browser_diagnostic_failed",
            error_message=message,
        )
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def _response_summary(response: Any, derived: dict[str, str]) -> SkroutzNetworkCapturedResponse:
    request = response.request
    method = str(request.method or "")
    resource_type = str(request.resource_type or "")
    content_type = str(response.headers.get("content-type", ""))
    url = sanitize_diagnostic_url(str(response.url or ""))
    body_bytes = response.body()
    body_size = len(body_bytes)
    body_sample = body_bytes[: MAX_BODY_SAMPLE_CHARS * 4].decode("utf-8", errors="replace")[:MAX_BODY_SAMPLE_CHARS]
    payload: Any | None = None
    parse_error: str | None = None
    if body_size <= MAX_PARSE_BYTES:
        try:
            payload = json.loads(body_bytes.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            parse_error = f"{exc.__class__.__name__}: {exc.msg}"
    else:
        parse_error = "body_too_large_to_parse"
    classification = classify_skroutz_network_endpoint(url, payload, body_sample)
    return SkroutzNetworkCapturedResponse(
        method=method,
        url=url,
        status=_int_or_none(response.status),
        resource_type=resource_type,
        content_type=content_type,
        body_size=body_size,
        parsed_json_valid=payload is not None,
        json_summary=_json_summary(payload),
        classification=classification,
        matched_derived_endpoint=_matched_derived_endpoint(url, derived),
        body_sample=_sanitize_body_sample(body_sample),
        json_parse_error=parse_error,
    )


def _build_report(
    *,
    source_url: str,
    started_at: datetime,
    timeout_seconds: int,
    headed: bool,
    derived: dict[str, str],
    captured: list[SkroutzNetworkCapturedResponse],
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> SkroutzNetworkDiagnosticReport:
    summary: dict[str, int] = {}
    for item in captured:
        summary[item.classification] = summary.get(item.classification, 0) + 1
    observed_filter = any(item.matched_derived_endpoint == "filter_products" for item in captured)
    observed_shops = any(item.matched_derived_endpoint == "shops_details" for item in captured)
    candidate, reason = _best_product_candidate(captured, derived)
    return SkroutzNetworkDiagnosticReport(
        source_url=sanitize_diagnostic_url(source_url),
        status=status,
        started_at=started_at.isoformat(),
        completed_at=_now().isoformat(),
        timeout_seconds=timeout_seconds,
        headed=bool(headed),
        derived_endpoints=derived,
        captured_responses=captured,
        observed_filter_products_url=observed_filter,
        observed_shops_details_url=observed_shops,
        exact_match_count=sum(1 for item in captured if item.matched_derived_endpoint is not None),
        product_data_candidate_url=candidate,
        product_data_candidate_reason=reason,
        classifications_summary=dict(sorted(summary.items())),
        error_code=error_code,
        error_message=error_message,
    )


def _best_product_candidate(captured: list[SkroutzNetworkCapturedResponse], derived: dict[str, str]) -> tuple[str | None, str | None]:
    priority = {
        PRIMARY_CANDIDATE_PRODUCT_OFFERS: 0,
        POSSIBLE_PRODUCT_OR_OFFER_DATA: 1,
        SECONDARY_CANDIDATE_SHOP_DETAILS: 2,
    }
    candidates = [item for item in captured if item.classification in priority]
    if not candidates:
        return None, "No product, offer, or shop-detail endpoint was classified."
    candidates.sort(key=lambda item: (priority[item.classification], item.matched_derived_endpoint is None, -(item.body_size or 0)))
    item = candidates[0]
    reason = item.classification
    if item.matched_derived_endpoint:
        reason = f"{reason}: exact derived {item.matched_derived_endpoint} endpoint observed"
    elif item.classification == PRIMARY_CANDIDATE_PRODUCT_OFFERS and item.json_summary.get("has_product_cards"):
        reason = f"{reason}: browser-observed endpoint has product_cards and differs from derived endpoints"
    elif item.url not in set(derived.values()):
        reason = f"{reason}: browser-observed endpoint differs from currently derived endpoints"
    return item.url, reason


def _trigger_lazy_requests(page: Any, playwright_error: type[Exception]) -> None:
    for _ in range(4):
        try:
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(500)
        except playwright_error:
            break
    labels = ("καταστήματα", "τιμές", "προσφορές", "Δες", "αγορά")
    for label in labels:
        try:
            locator = page.get_by_text(re.compile(re.escape(label), re.IGNORECASE)).first
            if locator.count() > 0:
                locator.click(timeout=1500)
                page.wait_for_timeout(700)
        except playwright_error:
            continue


def _should_capture_response(url: str, content_type: str, resource_type: str) -> bool:
    lowered_url = url.lower()
    lowered_content_type = content_type.lower()
    lowered_resource_type = resource_type.lower()
    return "json" in lowered_content_type or ".json" in lowered_url or lowered_resource_type in {"xhr", "fetch"}


def _json_summary(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        keys = [str(key) for key in payload.keys()]
        product_cards = payload.get("product_cards")
        return {
            "top_level_type": "object",
            "top_level_keys": keys[:MAX_SUMMARY_KEYS],
            "top_level_key_count": len(keys),
            "has_product_cards": isinstance(product_cards, list),
            "product_cards_count": len(product_cards) if isinstance(product_cards, list) else 0,
        }
    if isinstance(payload, list):
        first_item = payload[0] if payload else None
        return {
            "top_level_type": "array",
            "top_level_keys": [],
            "top_level_key_count": 0,
            "has_product_cards": False,
            "product_cards_count": 0,
            "array_length": len(payload),
            "first_item_keys": list(first_item.keys())[:MAX_SUMMARY_KEYS] if isinstance(first_item, dict) else [],
        }
    return {
        "top_level_type": "none",
        "top_level_keys": [],
        "top_level_key_count": 0,
        "has_product_cards": False,
        "product_cards_count": 0,
    }


def _matched_derived_endpoint(url: str, derived: dict[str, str]) -> str | None:
    parsed_url = _url_without_query(url)
    for key, value in derived.items():
        if _url_without_query(value) == parsed_url:
            return key
    return None


def _url_without_query(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query="", fragment=""))


def _payload_has_key_marker(payload: object | None, markers: tuple[str, ...]) -> bool:
    if payload is None:
        return False
    stack: list[object] = [payload]
    seen = 0
    while stack and seen < 500:
        seen += 1
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                lowered = str(key).lower()
                if any(marker in lowered for marker in markers):
                    return True
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(item for item in current[:50] if isinstance(item, (dict, list)))
    return False


def _looks_blocked(lowered_body: str, lowered_url: str) -> bool:
    if "challenge-platform" in lowered_url:
        return True
    if "<html" not in lowered_body and not any(marker in lowered_body for marker in ("captcha", "cf-chl")):
        return False
    return any(marker in lowered_body for marker in BLOCKED_MARKERS)


def _sanitize_body_sample(value: str) -> str:
    sanitized = sanitize_json({"sample": value})
    sample = sanitized.get("sample") if isinstance(sanitized, dict) else value
    return str(sample or "")[:MAX_BODY_SAMPLE_CHARS]


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
