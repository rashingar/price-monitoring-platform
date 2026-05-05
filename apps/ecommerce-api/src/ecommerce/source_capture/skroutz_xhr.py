from __future__ import annotations

import importlib.metadata
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

from ecommerce.source_capture.parsing import (
    parse_skroutz_offers,
    parse_skroutz_price_summary,
    parse_skroutz_visible_html_offers,
)
from ecommerce.source_capture.sanitize import content_hash, sanitize_json
from ecommerce.source_capture.scoring import ranked_response_candidates
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload, ResponseCandidate


NO_SHOP_TRIGGER = "no_shop_trigger"
NO_CANDIDATE_XHR_FOUND = "no_candidate_xhr_found"
XHR_PARSE_FAILED = "xhr_parse_failed"
BLOCKED_OR_CAPTCHA = "blocked_or_captcha"
TIMEOUT = "timeout"

CAPTURE_STRATEGY = "skroutz_playwright_xhr"
DOM_FALLBACK_STRATEGY = "skroutz_playwright_dom_fallback"
PARSER_VERSION = "skroutz_offers_v1"
PRICE_SUMMARY_PARSER_VERSION = "skroutz_filter_products_v1"
FILTER_PRODUCTS_ACTION = "skroutz_filter_products_fetch"
SHOP_ENTRYPOINT_SELECTORS = (
    "#offerings button[data-controller*='shops-entrypoint']",
    "#offerings .js-shops-entrypoint-wrapper button",
    "button[data-controller='sku-page--offerings--shops-entrypoint']",
    "button[data-controller*='sku-page--offerings--shops-entrypoint']",
    "button[data-action*='stats#incrementCounterDeviceSuffix']",
    "button.alternative-option-wrapper.btn-reset:has-text('καταστήματα')",
)
PRODUCT_READY_SELECTORS = (
    SHOP_ENTRYPOINT_SELECTORS[0],
)


def capture_skroutz_xhr(
    url: str,
    *,
    timeout_seconds: float,
    sync_playwright_factory: Callable[[], Any] | None = None,
    timeout_error_cls: type[BaseException] | tuple[type[BaseException], ...] | None = None,
) -> CaptureResult:
    try:
        if sync_playwright_factory is None:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright

            sync_playwright_factory = sync_playwright
            timeout_error_cls = PlaywrightTimeoutError
    except Exception as exc:
        return _failed_result(
            url,
            "PLAYWRIGHT_UNAVAILABLE",
            str(exc) or exc.__class__.__name__,
        )

    timeout_errors = _timeout_errors(timeout_error_cls)
    captured: list[ResponseCandidate] = []
    trigger_action: str | None = None
    clicked = False
    started = _now()
    deadline = time.monotonic() + timeout_seconds
    final_url = url
    html = ""
    document_status: int | None = None

    try:
        with sync_playwright_factory() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    locale="el-GR",
                    viewport={"width": 1440, "height": 1000},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                )

                def _record_response(response: Any) -> None:
                    request = getattr(response, "request", None)
                    resource_type = str(getattr(request, "resource_type", "") or "")
                    if resource_type not in {"xhr", "fetch"}:
                        return
                    body_text = _response_text(response)
                    captured.append(
                        ResponseCandidate(
                            url=str(getattr(response, "url", "") or ""),
                            method=str(getattr(request, "method", "GET") or "GET"),
                            status=getattr(response, "status", None),
                            content_type=str(getattr(response, "headers", {}).get("content-type", "") or ""),
                            body_text=body_text,
                            body_json=_json_or_none(body_text),
                            network_event_type=resource_type,
                            trigger_action=trigger_action,
                            occurred_after_trigger=clicked,
                        )
                    )

                page.on("response", _record_response)
                response = page.goto(url, wait_until="domcontentloaded", timeout=_remaining_ms(deadline))
                document_status = getattr(response, "status", None) if response is not None else None
                final_url = str(getattr(page, "url", url) or url)
                _wait_for_network(page, timeout_errors, deadline=deadline, timeout_ms=5000)
                html = _page_content(page)
                if _looks_blocked_document(html, status=document_status, url=final_url):
                    html = _wait_for_document_challenge_to_clear(
                        page,
                        timeout_errors,
                        deadline=deadline,
                        status=document_status,
                    )
                    final_url = str(getattr(page, "url", final_url) or final_url)
                    if _looks_blocked_document(html, status=document_status, url=final_url):
                        raise _BlockedDocument()
                _wait_for_product_surface(page, timeout_errors, deadline=deadline)
                _dismiss_cookie_dialog(page)
                _wait_before_shop_click(page, timeout_errors, deadline=deadline)
                trigger_action, clicked = _click_shop_trigger(page, deadline=deadline)
                if clicked:
                    _wait_for_trigger_responses(page, timeout_errors, deadline=deadline)
                filter_candidate = _fetch_filter_products_candidate(
                    page,
                    source_url=final_url or url,
                    clicked=clicked,
                    deadline=deadline,
                )
                if filter_candidate is not None:
                    captured.append(filter_candidate)
                html = _page_content(page)
                if _looks_blocked_document(html, status=document_status, url=final_url):
                    html = _wait_for_document_challenge_to_clear(
                        page,
                        timeout_errors,
                        deadline=deadline,
                        status=document_status,
                    )
                    final_url = str(getattr(page, "url", final_url) or final_url)
            finally:
                browser.close()

        fetched_at = _now()
        if _looks_blocked_document(html, status=document_status, url=final_url):
            return _blocked_result(
                url=url,
                final_url=final_url,
                html=html,
                document_status=document_status,
                fetched_at=fetched_at,
                started=started,
                trigger_action=trigger_action,
                flags=[],
            )

        scored_candidates = ranked_response_candidates(captured)
        best = scored_candidates[0] if scored_candidates else None
        if best is not None and _is_blocked_candidate(best.candidate):
            return _blocked_result(
                url=url,
                final_url=final_url,
                html=html,
                document_status=document_status,
                fetched_at=fetched_at,
                started=started,
                trigger_action=trigger_action,
                flags=_base_flags(clicked),
                candidate=best.candidate,
                candidate_score=best.score,
                candidate_reason="; ".join(best.reasons),
            )

        if best is None or best.score <= 0:
            return _dom_fallback_or_failure(
                url=url,
                final_url=final_url,
                html=html,
                document_status=document_status,
                fetched_at=fetched_at,
                started=started,
                trigger_action=trigger_action,
                clicked=clicked,
                flags=_base_flags(clicked) + [NO_CANDIDATE_XHR_FOUND],
                error_code=NO_SHOP_TRIGGER if not clicked else NO_CANDIDATE_XHR_FOUND,
                error_message=(
                    "Skroutz shop-list trigger was not found."
                    if not clicked
                    else "No useful Skroutz XHR/fetch candidate was captured."
                ),
            )

        first_unparsed: tuple[Any, CaptureSnapshotPayload, list[str]] | None = None
        for scored in scored_candidates:
            if scored.score <= 0:
                continue
            body_payload = scored.candidate.body_json if scored.candidate.body_json is not None else scored.candidate.body_text
            offers, offer_flags = parse_skroutz_offers(body_payload)
            price_observation = None
            summary_flags: list[str] = []
            parser_version = PARSER_VERSION
            data_quality_flags = _base_flags(clicked) + offer_flags
            if not offers:
                price_observation, summary_flags = parse_skroutz_price_summary(body_payload, page_url=url)
                if price_observation is not None:
                    parser_version = PRICE_SUMMARY_PARSER_VERSION
                    data_quality_flags = _base_flags(clicked) + summary_flags
            parsed_at = _now()
            json_payload = sanitize_json(scored.candidate.body_json) if isinstance(scored.candidate.body_json, (dict, list)) else None
            candidate_trigger_action = scored.candidate.trigger_action or trigger_action
            snapshot = CaptureSnapshotPayload(
                capture_strategy=CAPTURE_STRATEGY,
                page_url=url,
                final_url=final_url,
                request_url=scored.candidate.url,
                request_method=scored.candidate.method,
                response_status=scored.candidate.status,
                response_content_type=scored.candidate.content_type,
                response_body_json=json_payload,
                response_body_text=scored.candidate.body_text if json_payload is None else None,
                raw_html=html,
                content_hash=content_hash(scored.candidate.body_text or html),
                parser_version=parser_version,
                playwright_version=_playwright_version(),
                fetch_status_code=document_status,
                fetch_latency_ms=int((fetched_at - started).total_seconds() * 1000),
                candidate_score=scored.score,
                candidate_reason="; ".join(scored.reasons),
                network_event_type=scored.candidate.network_event_type,
                trigger_action=candidate_trigger_action,
                data_quality_flags=data_quality_flags,
                captured_at=fetched_at,
                fetched_at=fetched_at,
                parsed_at=parsed_at,
            )
            if offers:
                return CaptureResult(
                    vendor_slug="skroutz",
                    status="success",
                    snapshot=snapshot,
                    offer_observations=tuple(offers),
                )
            if price_observation is not None:
                return CaptureResult(
                    vendor_slug="skroutz",
                    status="success",
                    snapshot=snapshot,
                    price_observations=(price_observation,),
                )
            if first_unparsed is None:
                first_unparsed = (scored, snapshot, [*offer_flags, *summary_flags])

        if first_unparsed is None:
            return _dom_fallback_or_failure(
                url=url,
                final_url=final_url,
                html=html,
                document_status=document_status,
                fetched_at=fetched_at,
                started=started,
                trigger_action=trigger_action,
                clicked=clicked,
                flags=_base_flags(clicked) + [NO_CANDIDATE_XHR_FOUND],
                error_code=NO_CANDIDATE_XHR_FOUND,
                error_message="No useful Skroutz XHR/fetch candidate was captured.",
            )

        scored, snapshot, parse_flags = first_unparsed

        fallback = _dom_fallback_result(
            url=url,
            final_url=final_url,
            html=html,
            document_status=document_status,
            fetched_at=fetched_at,
            started=started,
            trigger_action=trigger_action,
            flags=_base_flags(clicked) + [XHR_PARSE_FAILED, *parse_flags],
            candidate=scored.candidate,
            candidate_score=scored.score,
            candidate_reason="; ".join(scored.reasons),
        )
        if fallback is not None:
            return fallback
        return CaptureResult(
            vendor_slug="skroutz",
            status="failed",
            snapshot=CaptureSnapshotPayload(
                **{
                    **snapshot.__dict__,
                    "data_quality_flags": snapshot.data_quality_flags + [XHR_PARSE_FAILED],
                    "error_code": XHR_PARSE_FAILED,
                    "error_message": "Skroutz candidate was captured but no offers or aggregate price were parsed.",
                }
            ),
            error_code=XHR_PARSE_FAILED,
            error_message="Skroutz candidate was captured but no offers or aggregate price were parsed.",
        )
    except _BlockedDocument:
        fetched_at = _now()
        return _blocked_result(
            url=url,
            final_url=final_url,
            html=html,
            document_status=document_status,
            fetched_at=fetched_at,
            started=started,
            trigger_action=trigger_action,
            flags=[],
        )
    except timeout_errors as exc:
        return _failed_result(
            url,
            TIMEOUT,
            str(exc) or exc.__class__.__name__,
            response_status=document_status,
            raw_html=html,
            final_url=final_url,
            trigger_action=trigger_action,
        )
    except Exception as exc:
        return _failed_result(
            url,
            "FETCH_FAILED",
            str(exc) or exc.__class__.__name__,
            response_status=document_status,
            raw_html=html,
            final_url=final_url,
            trigger_action=trigger_action,
        )


def _click_shop_trigger(page: Any, *, deadline: float) -> tuple[str | None, bool]:
    selectors = [
        *SHOP_ENTRYPOINT_SELECTORS,
        "text=Δες τα καταστήματα",
        "text=Δείτε τα καταστήματα",
        "text=Δες καταστήματα",
        "text=Αγόρασε από",
        "text=καταστήματα",
        "button:has-text('Δες')",
        "button:has-text('καταστήματα')",
        "a:has-text('καταστήματα')",
        "[href*='shop']",
        "[href*='offer']",
        "[data-testid*='shop']",
        "[data-e2e*='shop']",
    ]
    for selector in selectors:
        try:
            timeout_ms = min(1000, _remaining_ms(deadline))
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=timeout_ms):
                try:
                    locator.scroll_into_view_if_needed(timeout=min(1000, _remaining_ms(deadline)))
                except Exception:
                    pass
                locator.click(timeout=min(3000, _remaining_ms(deadline)))
                return selector, True
        except Exception:
            continue
    return None, False


def _dismiss_cookie_dialog(page: Any) -> None:
    selectors = [
        "button:has-text('Αποδοχή')",
        "button:has-text('Συμφωνώ')",
        "button:has-text('Accept')",
        "button:has-text('OK')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=500):
                locator.click(timeout=1000)
                return
        except Exception:
            continue


def _fetch_filter_products_candidate(
    page: Any,
    *,
    source_url: str,
    clicked: bool,
    deadline: float,
) -> ResponseCandidate | None:
    endpoint = _filter_products_url(source_url)
    if endpoint is None:
        return None
    try:
        timeout_ms = min(5000, _remaining_ms(deadline))
        result = page.evaluate(
            """
            async ({ url, timeoutMs }) => {
              const controller = new AbortController();
              const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
              try {
                const response = await fetch(url, {
                  method: "GET",
                  credentials: "same-origin",
                  headers: {
                    "accept": "application/json, text/plain, */*",
                    "x-requested-with": "XMLHttpRequest"
                  },
                  signal: controller.signal
                });
                return {
                  url: response.url,
                  status: response.status,
                  contentType: response.headers.get("content-type") || "",
                  text: await response.text()
                };
              } finally {
                clearTimeout(timeoutId);
              }
            }
            """,
            {"url": endpoint, "timeoutMs": timeout_ms},
        )
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    body_text = str(result.get("text") or "")
    if not body_text:
        return None
    return ResponseCandidate(
        url=str(result.get("url") or endpoint),
        method="GET",
        status=_int_or_none(result.get("status")),
        content_type=str(result.get("contentType") or ""),
        body_text=body_text,
        body_json=_json_or_none(body_text),
        network_event_type="fetch",
        trigger_action=FILTER_PRODUCTS_ACTION,
        occurred_after_trigger=clicked,
    )


def _filter_products_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    match = re.search(r"/s/(\d+)(?:/|$)", parsed.path or "")
    if match is None or not parsed.scheme or not parsed.netloc:
        return None
    product_id = match.group(1)
    return urlunparse((parsed.scheme, parsed.netloc, f"/s/{product_id}/filter_products.json", "", "", ""))


def _dom_fallback_or_failure(
    *,
    url: str,
    final_url: str,
    html: str,
    document_status: int | None,
    fetched_at: datetime,
    started: datetime,
    trigger_action: str | None,
    clicked: bool,
    flags: list[str],
    error_code: str,
    error_message: str,
) -> CaptureResult:
    fallback = _dom_fallback_result(
        url=url,
        final_url=final_url,
        html=html,
        document_status=document_status,
        fetched_at=fetched_at,
        started=started,
        trigger_action=trigger_action,
        flags=flags,
    )
    if fallback is not None:
        return fallback
    parsed_at = _now()
    snapshot = CaptureSnapshotPayload(
        capture_strategy=CAPTURE_STRATEGY,
        page_url=url,
        final_url=final_url,
        response_status=document_status,
        raw_html=html,
        content_hash=content_hash(html),
        playwright_version=_playwright_version(),
        fetch_status_code=document_status,
        fetch_latency_ms=int((fetched_at - started).total_seconds() * 1000),
        trigger_action=trigger_action,
        data_quality_flags=flags,
        error_code=error_code,
        error_message=error_message,
        captured_at=fetched_at,
        fetched_at=fetched_at,
        parsed_at=parsed_at,
    )
    return CaptureResult(
        vendor_slug="skroutz",
        status="failed",
        snapshot=snapshot,
        error_code=error_code,
        error_message=error_message,
    )


def _dom_fallback_result(
    *,
    url: str,
    final_url: str,
    html: str,
    document_status: int | None,
    fetched_at: datetime,
    started: datetime,
    trigger_action: str | None,
    flags: list[str],
    candidate: ResponseCandidate | None = None,
    candidate_score: int | None = None,
    candidate_reason: str | None = None,
) -> CaptureResult | None:
    offers, dom_flags = parse_skroutz_visible_html_offers(html)
    if not offers:
        return None
    parsed_at = _now()
    snapshot = CaptureSnapshotPayload(
        capture_strategy=DOM_FALLBACK_STRATEGY,
        page_url=url,
        final_url=final_url,
        request_url=candidate.url if candidate is not None else None,
        request_method=candidate.method if candidate is not None else None,
        response_status=candidate.status if candidate is not None else document_status,
        response_content_type=candidate.content_type if candidate is not None else None,
        response_body_text=candidate.body_text if candidate is not None and candidate.body_json is None else None,
        response_body_json=sanitize_json(candidate.body_json) if candidate is not None and isinstance(candidate.body_json, (dict, list)) else None,
        raw_html=html,
        content_hash=content_hash(candidate.body_text if candidate is not None and candidate.body_text else html),
        parser_version="skroutz_visible_html_v1",
        playwright_version=_playwright_version(),
        fetch_status_code=document_status,
        fetch_latency_ms=int((fetched_at - started).total_seconds() * 1000),
        candidate_score=candidate_score,
        candidate_reason=candidate_reason,
        network_event_type=candidate.network_event_type if candidate is not None else None,
        trigger_action=trigger_action,
        data_quality_flags=list(dict.fromkeys([*flags, "dom_fallback", *dom_flags])),
        captured_at=fetched_at,
        fetched_at=fetched_at,
        parsed_at=parsed_at,
    )
    return CaptureResult(
        vendor_slug="skroutz",
        status="success",
        snapshot=snapshot,
        offer_observations=tuple(offers),
    )


def _blocked_result(
    *,
    url: str,
    final_url: str,
    html: str,
    document_status: int | None,
    fetched_at: datetime,
    started: datetime,
    trigger_action: str | None,
    flags: list[str],
    candidate: ResponseCandidate | None = None,
    candidate_score: int | None = None,
    candidate_reason: str | None = None,
) -> CaptureResult:
    parsed_at = _now()
    snapshot = CaptureSnapshotPayload(
        capture_strategy=CAPTURE_STRATEGY,
        page_url=url,
        final_url=final_url,
        request_url=candidate.url if candidate is not None else None,
        request_method=candidate.method if candidate is not None else None,
        response_status=candidate.status if candidate is not None else document_status,
        response_content_type=candidate.content_type if candidate is not None else None,
        response_body_text=candidate.body_text if candidate is not None else None,
        raw_html=html,
        content_hash=content_hash(candidate.body_text if candidate is not None and candidate.body_text else html),
        parser_version=PARSER_VERSION if candidate is not None else None,
        playwright_version=_playwright_version(),
        fetch_status_code=document_status,
        fetch_latency_ms=int((fetched_at - started).total_seconds() * 1000),
        candidate_score=candidate_score,
        candidate_reason=candidate_reason,
        network_event_type=candidate.network_event_type if candidate is not None else None,
        trigger_action=trigger_action,
        data_quality_flags=list(dict.fromkeys([*flags, BLOCKED_OR_CAPTCHA])),
        error_code=BLOCKED_OR_CAPTCHA,
        error_message="Skroutz returned an anti-bot, captcha, or challenge response.",
        captured_at=fetched_at,
        fetched_at=fetched_at,
        parsed_at=parsed_at,
    )
    return CaptureResult(
        vendor_slug="skroutz",
        status="failed",
        snapshot=snapshot,
        error_code=BLOCKED_OR_CAPTCHA,
        error_message="Skroutz returned an anti-bot, captcha, or challenge response.",
    )


def _failed_result(
    url: str,
    error_code: str,
    error_message: str,
    *,
    response_status: int | None = None,
    raw_html: str | None = None,
    final_url: str | None = None,
    trigger_action: str | None = None,
) -> CaptureResult:
    now = _now()
    return CaptureResult(
        vendor_slug="skroutz",
        status="failed",
        snapshot=CaptureSnapshotPayload(
            capture_strategy=CAPTURE_STRATEGY,
            page_url=url,
            final_url=final_url,
            response_status=response_status,
            raw_html=raw_html,
            content_hash=content_hash(raw_html),
            playwright_version=_playwright_version(),
            data_quality_flags=[error_code],
            trigger_action=trigger_action,
            error_code=error_code,
            error_message=error_message,
            captured_at=now,
            fetched_at=now,
            parsed_at=now,
        ),
        error_code=error_code,
        error_message=error_message,
    )


def _response_text(response: Any) -> str:
    try:
        text = response.text()
    except Exception:
        return ""
    return str(text or "")


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


def _wait_for_trigger_responses(page: Any, timeout_errors: tuple[type[BaseException], ...], *, deadline: float) -> None:
    try:
        page.wait_for_timeout(min(1500, _remaining_ms(deadline)))
        _wait_for_network(page, timeout_errors, deadline=deadline, timeout_ms=5000)
    except timeout_errors:
        return


def _wait_before_shop_click(page: Any, timeout_errors: tuple[type[BaseException], ...], *, deadline: float) -> None:
    try:
        page.wait_for_timeout(min(3000, _remaining_ms(deadline)))
    except timeout_errors:
        return


def _wait_for_network(page: Any, timeout_errors: tuple[type[BaseException], ...], *, deadline: float, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, _remaining_ms(deadline)))
    except timeout_errors:
        return


def _wait_for_product_surface(page: Any, timeout_errors: tuple[type[BaseException], ...], *, deadline: float) -> None:
    for selector in PRODUCT_READY_SELECTORS:
        try:
            page.wait_for_selector(selector, state="visible", timeout=min(15000, _remaining_ms(deadline)))
            return
        except timeout_errors:
            continue
        except Exception:
            continue


def _wait_for_document_challenge_to_clear(
    page: Any,
    timeout_errors: tuple[type[BaseException], ...],
    *,
    deadline: float,
    status: int | None,
) -> str:
    settle_deadline = min(deadline, time.monotonic() + 10.0)
    html = _page_content(page)
    while time.monotonic() < settle_deadline and _looks_blocked_document(
        html,
        status=status,
        url=str(getattr(page, "url", "") or ""),
    ):
        try:
            page.wait_for_timeout(min(1000, _remaining_ms(settle_deadline)))
            _wait_for_network(page, timeout_errors, deadline=settle_deadline, timeout_ms=1000)
        except timeout_errors:
            pass
        html = _page_content(page)
    return html


def _page_content(page: Any) -> str:
    try:
        return str(page.content() or "")
    except Exception:
        return ""


def _base_flags(clicked: bool) -> list[str]:
    return [] if clicked else [NO_SHOP_TRIGGER]


def _is_blocked_candidate(candidate: ResponseCandidate) -> bool:
    body = (candidate.body_text or "").lower()
    url = candidate.url.lower()
    return _looks_blocked_candidate_payload(body, status=candidate.status, url=url)


def _looks_blocked_document(text: str, *, status: int | None, url: str) -> bool:
    lowered = (text or "").lower()
    return (
        status in {401, 403, 429}
        or "just a moment" in lowered
        or "cf-browser-verification" in lowered
        or "cf-chl-widget" in lowered
        or "challenges.cloudflare.com" in lowered
        or "enable javascript and cookies" in lowered
        or "<title>περιμένετε" in lowered
        or "g-recaptcha" in lowered
        or "captcha" in lowered
        or "challenge-platform" in (url or "").lower()
    )


def _looks_blocked_candidate_payload(text: str, *, status: int | None, url: str) -> bool:
    lowered = (text or "").lower()
    return (
        status in {401, 403, 429}
        or "just a moment" in lowered
        or "cloudflare" in lowered and ("challenge" in lowered or "captcha" in lowered)
        or "cf-chl" in lowered
        or "captcha" in lowered
        or "challenge-platform" in (url or "").lower()
    )


def _remaining_ms(deadline: float) -> int:
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise TimeoutError("Skroutz capture exceeded the overall timeout budget.")
    return remaining


def _timeout_errors(timeout_error_cls: type[BaseException] | tuple[type[BaseException], ...] | None) -> tuple[type[BaseException], ...]:
    if timeout_error_cls is None:
        return (TimeoutError,)
    if isinstance(timeout_error_cls, tuple):
        return tuple(dict.fromkeys([*timeout_error_cls, TimeoutError]))
    return tuple(dict.fromkeys([timeout_error_cls, TimeoutError]))


def _playwright_version() -> str | None:
    try:
        return importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class _BlockedDocument(Exception):
    pass
