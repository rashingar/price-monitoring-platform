from __future__ import annotations

"""Bounded, optional validation of a published product page.

The validator deliberately accepts and returns plain mappings so the migration
orchestrator can persist the report without depending on a browser or API
model.  Network access is optional.  When it is not configured or a normal
HTTP request cannot be completed, all checks remain ``not_run`` and the report
contains an operator checklist instead of guessing about crawler access.
"""

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from ipaddress import IPv4Address, IPv6Address, ip_address
import json
import re
import socket
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
import httpcore
import httpx


DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 5
MAX_HTML_BYTES = 2 * 1024 * 1024

LiveFetcher = Callable[[str, float], Mapping[str, Any]]

LIVE_CHECKS: tuple[tuple[str, str], ...] = (
    ("live.http_success", "Confirm that the product URL returns an HTTP success status."),
    ("live.final_url", "Confirm the final URL after ordinary redirects."),
    ("live.canonical_url", "Confirm the page canonical URL."),
    ("live.title", "Confirm the document title."),
    ("live.meta_description", "Confirm the Meta Description."),
    ("live.visible_h1", "Confirm the visible product H1."),
    ("live.description_h2", "Confirm the visible description H2."),
    ("live.main_image", "Confirm the main product image."),
    ("live.gallery_order", "Confirm the published gallery order."),
    ("live.description_images", "Confirm image references rendered inside the product description."),
    ("live.product_structured_data", "Confirm Product JSON-LD is available."),
    ("live.offer_price", "Confirm the Product Offer price."),
    ("live.availability", "Confirm the Product Offer availability."),
    ("live.mpn_gtin", "Confirm the published MPN and any expected GTIN."),
    ("live.internal_links", "Confirm relevant internal links."),
)

_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "key",
    "password",
    "secret",
    "session",
    "sid",
    "token",
    "user_token",
}

_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain"}


class _BlockedLiveDestination(ValueError):
    """Raised before an outbound connection to a non-public destination."""


class _LiveDestinationResolutionError(OSError):
    """Raised when a destination cannot be resolved unambiguously and safely."""


class _PublicNetworkBackend(httpcore.SyncBackend):
    """Resolve once, validate every answer, and connect to a vetted literal IP.

    Connecting to the literal address prevents the HTTP stack from performing a
    second, potentially rebound DNS lookup.  httpcore still passes the original
    hostname to ``start_tls``, so certificate validation and SNI remain intact.
    """

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        addresses = _resolve_public_addresses(host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return super().connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise _LiveDestinationResolutionError(
            "Live destination did not resolve to a usable public address."
        )


class _PublicHTTPTransport(httpx.HTTPTransport):
    """HTTP transport whose connection backend cannot re-resolve a hostname."""

    def __init__(self) -> None:
        # Build the standard transport first so its request/response adaptation
        # remains owned by httpx, then replace only the httpcore connection pool.
        # Environment proxies are deliberately disabled for this validator.
        super().__init__(trust_env=False, retries=0)
        original_pool = self._pool
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=True, trust_env=False),
            network_backend=_PublicNetworkBackend(),
            retries=0,
        )
        original_pool.close()


def validate_live_product(
    expected: Mapping[str, Any],
    *,
    model: str | None = None,
    target_url: str | None = None,
    fetcher: LiveFetcher | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Validate one live page, or return an explicit ``not_run`` report.

    The default fetcher performs one bounded HTTP GET, follows normal redirects,
    and does not send credentials, cookies, browser automation, or anti-bot
    bypass material.  Tests and higher-level adapters can inject a mapping-based
    fetcher with the same ``(url, timeout_seconds)`` signature.
    """

    resolved_model = _text(model) or _first_expected_text(
        expected, "model", "internal_model", "internal_product_code"
    )
    requested_url = _text(target_url) or _expected_product_url(expected)
    safe_requested_url = _safe_url(requested_url)
    if not requested_url:
        return build_not_run_report(
            expected,
            model=resolved_model,
            target_url="",
            reason="live_url_not_configured",
            access_status="not_configured",
        )
    initial_url_error = _public_http_url_error(requested_url)
    if initial_url_error is not None:
        return build_not_run_report(
            expected,
            model=resolved_model,
            target_url=safe_requested_url,
            reason=(
                "live_url_blocked_non_public_destination"
                if initial_url_error == "blocked_non_public_destination"
                else "live_url_invalid_or_unsupported"
            ),
            access_status=(
                "blocked"
                if initial_url_error == "blocked_non_public_destination"
                else "not_configured"
            ),
        )

    bounded_timeout = _bounded_timeout(timeout_seconds)
    selected_fetcher = fetcher or _bounded_http_get
    try:
        response = selected_fetcher(requested_url, bounded_timeout)
    except _BlockedLiveDestination as exc:
        return build_not_run_report(
            expected,
            model=resolved_model,
            target_url=safe_requested_url,
            reason="live_url_blocked_non_public_destination",
            access_status="blocked",
            error_type=exc.__class__.__name__,
        )
    except Exception as exc:  # The report must not expose request/credential detail.
        return build_not_run_report(
            expected,
            model=resolved_model,
            target_url=safe_requested_url,
            reason="live_access_unavailable",
            access_status="unavailable",
            error_type=exc.__class__.__name__,
        )

    return evaluate_live_response(
        expected,
        response,
        model=resolved_model,
        target_url=safe_requested_url,
    )


def evaluate_live_response(
    expected: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    model: str | None = None,
    target_url: str | None = None,
) -> dict[str, Any]:
    """Evaluate a mapping produced by the bounded HTTP adapter."""

    status_code = _integer(response.get("status_code"))
    requested_url = _text(target_url) or _safe_url(
        _text(response.get("requested_url")) or _expected_product_url(expected)
    )
    raw_final_url = _text(response.get("final_url")) or requested_url
    final_url = _safe_url(raw_final_url)
    html = _text(response.get("text"))

    response_urls = [
        _text(response.get("requested_url")) or requested_url,
        raw_final_url,
        *_redirect_urls(response),
    ]
    if any(_public_http_url_error(url) is not None for url in response_urls):
        return build_not_run_report(
            expected,
            model=model,
            target_url=requested_url,
            reason="live_response_blocked_non_public_destination",
            access_status="blocked",
        )

    if status_code is None:
        return build_not_run_report(
            expected,
            model=model,
            target_url=requested_url,
            reason="live_response_status_unavailable",
            access_status="unavailable",
        )

    if status_code in {401, 403}:
        report = build_not_run_report(
            expected,
            model=model,
            target_url=requested_url,
            reason="live_authentication_or_access_unavailable",
            access_status="unavailable",
        )
        report["access"]["http_status"] = status_code
        report["access"]["final_url"] = final_url
        return report

    if status_code < 200 or status_code >= 300:
        checks = [
            _check(
                "live.http_success",
                "fail",
                observed=status_code,
                expected="HTTP 2xx",
                message="The product URL did not return an HTTP success status.",
            )
        ]
        checks.extend(
            _not_run_check(check_id, "http_success_required")
            for check_id, _ in LIVE_CHECKS[1:]
        )
        return _build_report(
            checks,
            model=model,
            target_url=requested_url,
            access={
                **_access_base("http_error"),
                "configured": True,
                "requested_url": requested_url,
                "final_url": final_url,
                "http_status": status_code,
                "error_code": "http_not_successful",
                "response_truncated": bool(response.get("truncated", False)),
            },
        )

    soup = BeautifulSoup(html, "lxml")
    products = _jsonld_products(soup)
    product = products[0] if products else {}
    observed = _observed_page(soup, product, base_url=final_url)
    checks = _evaluate_checks(
        expected,
        observed=observed,
        status_code=status_code,
        requested_url=requested_url,
        final_url=final_url,
    )
    return _build_report(
        checks,
        model=model,
        target_url=requested_url,
        access={
            **_access_base("completed"),
            "configured": True,
            "requested_url": requested_url,
            "final_url": final_url,
            "http_status": status_code,
            "error_code": None,
            "response_truncated": bool(response.get("truncated", False)),
        },
    )


def build_not_run_report(
    expected: Mapping[str, Any],
    *,
    model: str | None = None,
    target_url: str,
    reason: str,
    access_status: str,
    error_type: str | None = None,
) -> dict[str, Any]:
    """Return all required checks as ``not_run`` with a manual checklist."""

    resolved_model = _text(model) or _first_expected_text(
        expected, "model", "internal_model", "internal_product_code"
    )
    checks = [_not_run_check(check_id, reason) for check_id, _ in LIVE_CHECKS]
    return _build_report(
        checks,
        model=resolved_model,
        target_url=target_url,
        access={
            **_access_base(access_status),
            "configured": access_status != "not_configured",
            "requested_url": target_url,
            "final_url": None,
            "http_status": None,
            "error_code": reason,
            "error_type": error_type,
            "response_truncated": False,
        },
    )


def _bounded_http_get(url: str, timeout_seconds: float) -> Mapping[str, Any]:
    timeout = httpx.Timeout(timeout_seconds)
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "identity",
        "User-Agent": "ProductFactory-SEO-Live-Validator/1.0",
    }
    current_url = url
    redirect_chain: list[str] = []
    with httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        max_redirects=MAX_REDIRECTS,
        headers=headers,
        transport=_PublicHTTPTransport(),
        trust_env=False,
    ) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            _assert_public_http_url(current_url)
            with client.stream("GET", current_url) as response:
                _assert_public_peer(response)
                response_url = str(response.url)
                _assert_public_http_url(response_url)
                location = response.headers.get("location")
                if response.status_code in _REDIRECT_STATUS_CODES and location:
                    if redirect_count >= MAX_REDIRECTS:
                        raise _BlockedLiveDestination(
                            "Live URL exceeded the permitted redirect limit."
                        )
                    next_url = urljoin(response_url, location)
                    _assert_public_http_url(next_url)
                    redirect_chain.append(_safe_url(next_url))
                    current_url = next_url
                    continue

                chunks: list[bytes] = []
                byte_count = 0
                truncated = False
                for chunk in response.iter_bytes():
                    remaining = MAX_HTML_BYTES - byte_count
                    if remaining <= 0:
                        truncated = True
                        break
                    if len(chunk) > remaining:
                        chunks.append(chunk[:remaining])
                        byte_count += remaining
                        truncated = True
                        break
                    chunks.append(chunk)
                    byte_count += len(chunk)
                encoding = response.encoding or "utf-8"
                text = b"".join(chunks).decode(encoding, errors="replace")
                return {
                    "status_code": response.status_code,
                    "requested_url": url,
                    "final_url": response_url,
                    "redirect_chain": redirect_chain,
                    "headers": dict(response.headers),
                    "text": text,
                    "truncated": truncated,
                }
    raise _BlockedLiveDestination(
        "Live URL redirect handling did not terminate safely."
    )


def _evaluate_checks(
    expected: Mapping[str, Any],
    *,
    observed: Mapping[str, Any],
    status_code: int,
    requested_url: str,
    final_url: str,
) -> list[dict[str, Any]]:
    expected_url = _expected_product_url(expected) or requested_url
    expected_canonical = _first_expected_text(
        expected, "canonical_url", "product_url", "url"
    )
    expected_title = _first_expected_text(expected, "meta_title", "title")
    expected_description = _first_expected_text(expected, "meta_description")
    expected_h1 = _first_expected_text(expected, "h1", "name", "product_name")
    expected_h2 = _expected_strings(expected, "description_h2", "description_heading")
    if not expected_h2:
        expected_h2 = _expected_description_h2(expected)
    expected_main_image = _first_expected_text(expected, "image", "main_image")
    expected_gallery = _expected_gallery(expected)
    expected_description_images = _expected_description_images(expected, final_url)
    expected_price = _first_expected_value(expected, "price", "offer_price")
    expected_availability = _expected_availability(expected)
    expected_mpn = _first_expected_text(expected, "mpn")
    expected_gtin = _expected_gtin(expected)
    expected_links = _expected_internal_links(expected)

    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "live.http_success",
            "pass",
            observed=status_code,
            expected="HTTP 2xx",
            message="The product URL returned an HTTP success status.",
        )
    )
    final_matches = bool(final_url) and _urls_equal(final_url, expected_url, final_url)
    checks.append(
        _presence_or_match_check(
            "live.final_url",
            observed=final_url,
            expected=expected_url,
            matches=final_matches,
        )
    )

    actual_canonical = _text(observed.get("canonical_url"))
    canonical_matches = bool(actual_canonical) and _urls_equal(
        actual_canonical, expected_canonical or expected_url, final_url
    )
    checks.append(
        _presence_or_match_check(
            "live.canonical_url",
            observed=actual_canonical,
            expected=expected_canonical or expected_url,
            matches=canonical_matches,
        )
    )
    checks.append(
        _text_check("live.title", observed.get("title"), expected_title)
    )
    checks.append(
        _text_check(
            "live.meta_description",
            observed.get("meta_description"),
            expected_description,
        )
    )
    checks.append(
        _text_check("live.visible_h1", observed.get("h1"), expected_h1)
    )

    actual_h2s = _string_list(observed.get("h2"))
    if expected_h2:
        h2_ok = all(
            any(_same_text(expected_item, actual) for actual in actual_h2s)
            for expected_item in expected_h2
        )
        h2_expected: Any = expected_h2
    else:
        h2_ok = False
        h2_expected = "reviewed description H2"
    checks.append(
        _check(
            "live.description_h2",
            "pass" if h2_ok else "not_run" if not expected_h2 else "fail",
            observed=actual_h2s,
            expected=h2_expected,
            message=(
                "No reviewed description heading was available for deterministic live comparison."
                if not expected_h2
                else None
            ),
        )
    )

    actual_main_image = _text(observed.get("main_image"))
    main_ok = bool(actual_main_image) and (
        not expected_main_image
        or _urls_equal(actual_main_image, expected_main_image, final_url)
    )
    checks.append(
        _presence_or_match_check(
            "live.main_image",
            observed=actual_main_image,
            expected=expected_main_image or "a main product image",
            matches=main_ok,
        )
    )

    actual_gallery = _string_list(observed.get("gallery"))
    if not expected_gallery:
        checks.append(
            _check(
                "live.gallery_order",
                "not_applicable",
                observed=actual_gallery,
                expected=[],
                message="No additional gallery order was supplied for validation.",
            )
        )
    else:
        gallery_ok = len(actual_gallery) >= len(expected_gallery) and all(
            _urls_equal(actual, wanted, final_url)
            for actual, wanted in zip(
                actual_gallery[: len(expected_gallery)], expected_gallery, strict=True
            )
        )
        checks.append(
            _check(
                "live.gallery_order",
                "pass" if gallery_ok else "fail",
                observed=actual_gallery,
                expected=expected_gallery,
            )
        )

    actual_description_images = _string_list(observed.get("description_images"))
    if expected_description_images:
        missing_description_images = [
            wanted
            for wanted in expected_description_images
            if not any(
                _urls_equal(actual, wanted, final_url)
                for actual in actual_description_images
            )
        ]
        checks.append(
            _check(
                "live.description_images",
                "fail" if missing_description_images else "pass",
                observed=actual_description_images,
                expected=expected_description_images,
                evidence=[f"missing:{item}" for item in missing_description_images],
            )
        )
    else:
        checks.append(
            _check(
                "live.description_images",
                "not_applicable",
                observed=actual_description_images,
                expected=[],
                message="No description image references were supplied for validation.",
            )
        )

    product_data = observed.get("product_structured_data")
    checks.append(
        _check(
            "live.product_structured_data",
            "pass" if isinstance(product_data, Mapping) and product_data else "fail",
            observed=bool(isinstance(product_data, Mapping) and product_data),
            expected=True,
        )
    )

    actual_price = observed.get("offer_price")
    if expected_price in {None, ""}:
        checks.append(
            _check(
                "live.offer_price",
                "not_applicable",
                observed=actual_price,
                expected=None,
                message="No expected price was supplied for live comparison.",
            )
        )
    else:
        price_ok = _decimal_text(actual_price) == _decimal_text(expected_price)
        checks.append(
            _check(
                "live.offer_price",
                "pass" if price_ok else "fail",
                observed=actual_price,
                expected=expected_price,
            )
        )

    actual_availability = _normalize_availability(observed.get("availability"))
    if not expected_availability:
        checks.append(
            _check(
                "live.availability",
                "not_applicable",
                observed=actual_availability,
                expected=None,
                message="No expected availability was supplied for live comparison.",
            )
        )
    else:
        checks.append(
            _check(
                "live.availability",
                "pass" if actual_availability == expected_availability else "fail",
                observed=actual_availability,
                expected=expected_availability,
            )
        )

    actual_mpn = _text(observed.get("mpn"))
    actual_gtin = _text(observed.get("gtin"))
    identifier_errors: list[str] = []
    if expected_mpn and not _same_identifier(actual_mpn, expected_mpn):
        identifier_errors.append("mpn_mismatch")
    if expected_gtin and _digits(actual_gtin) != _digits(expected_gtin):
        identifier_errors.append("gtin_mismatch")
    if not expected_mpn and not expected_gtin and not actual_mpn and not actual_gtin:
        identifier_errors.append("identifier_missing")
    checks.append(
        _check(
            "live.mpn_gtin",
            "fail" if identifier_errors else "pass",
            observed={"mpn": actual_mpn, "gtin": actual_gtin},
            expected={"mpn": expected_mpn, "gtin": expected_gtin},
            evidence=identifier_errors,
        )
    )

    actual_links = _string_list(observed.get("internal_links"))
    if expected_links:
        missing_links = [
            link
            for link in expected_links
            if not any(_urls_equal(actual, link, final_url) for actual in actual_links)
        ]
        links_ok = not missing_links
        evidence = [f"missing:{link}" for link in missing_links]
        expected_link_value: Any = expected_links
    else:
        links_ok = False
        evidence = ["reviewed_related_or_category_links_unavailable"]
        expected_link_value = "reviewed related/category internal links"
    checks.append(
        _check(
            "live.internal_links",
            "pass" if links_ok else "not_run" if not expected_links else "fail",
            observed=actual_links[:50],
            expected=expected_link_value,
            evidence=evidence,
        )
    )
    return checks


def _observed_page(
    soup: BeautifulSoup, product: Mapping[str, Any], *, base_url: str
) -> dict[str, Any]:
    canonical = soup.find("link", rel=lambda value: _rel_contains(value, "canonical"))
    meta_description = soup.find(
        "meta",
        attrs={"name": lambda value: _casefold(value) == "description"},
    )
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1s = _visible_texts(soup.find_all("h1"))
    h2s = _visible_texts(soup.find_all("h2"))
    product_images = _jsonld_images(product, base_url=base_url)
    main_image = _main_image(soup, base_url=base_url) or (
        product_images[0] if product_images else ""
    )
    gallery = _gallery_images(soup, product_images, base_url=base_url)
    offer = _first_offer(product)
    gtin = _first_product_value(
        product, "gtin14", "gtin13", "gtin12", "gtin8", "gtin", "ean", "upc"
    )
    return {
        "canonical_url": (
            urljoin(base_url, _text(canonical.get("href")))
            if isinstance(canonical, Tag)
            else ""
        ),
        "title": title,
        "meta_description": (
            _text(meta_description.get("content"))
            if isinstance(meta_description, Tag)
            else ""
        ),
        "h1": h1s[0] if h1s else "",
        "h2": h2s,
        "main_image": main_image,
        "gallery": gallery,
        "description_images": _description_images(soup, base_url=base_url),
        "product_structured_data": dict(product),
        "offer_price": _first_product_value(offer, "price", "lowPrice"),
        "availability": _first_product_value(offer, "availability"),
        "mpn": _first_product_value(product, "mpn"),
        "gtin": gtin,
        "internal_links": _internal_links(soup, base_url=base_url),
    }


def _jsonld_products(soup: BeautifulSoup) -> list[Mapping[str, Any]]:
    products: list[Mapping[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for item in _walk_jsonld(payload):
            raw_type = item.get("@type")
            types = raw_type if isinstance(raw_type, list) else [raw_type]
            if any(_casefold(value) == "product" for value in types):
                products.append(item)
    return products


def _walk_jsonld(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for key, nested in value.items():
            if key in {"@context"}:
                continue
            yield from _walk_jsonld(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_jsonld(item)


def _jsonld_images(product: Mapping[str, Any], *, base_url: str) -> list[str]:
    value = product.get("image")
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            raw = _first_product_value(item, "contentUrl", "url")
        else:
            raw = item
        text = _text(raw)
        if text:
            result.append(urljoin(base_url, text))
    return _dedupe(result)


def _first_offer(product: Mapping[str, Any]) -> Mapping[str, Any]:
    offers = product.get("offers")
    if isinstance(offers, Mapping):
        return offers
    if isinstance(offers, list):
        return next((item for item in offers if isinstance(item, Mapping)), {})
    return {}


def _main_image(soup: BeautifulSoup, *, base_url: str) -> str:
    selectors = (
        '[itemprop="image"]',
        'meta[property="og:image"]',
        ".product-image img",
        ".product-info img",
        "main img",
    )
    for selector in selectors:
        node = soup.select_one(selector)
        if not isinstance(node, Tag):
            continue
        raw = _first_attribute(node, "content", "src", "href", "data-src")
        if raw:
            return urljoin(base_url, raw)
    return ""


def _gallery_images(
    soup: BeautifulSoup,
    product_images: list[str],
    *,
    base_url: str,
) -> list[str]:
    selectors = (
        "[data-gallery] img",
        ".product-gallery img",
        ".image-additional img",
        ".thumbnails img",
        ".swiper-wrapper img",
    )
    for selector in selectors:
        paths = [
            urljoin(base_url, raw)
            for node in soup.select(selector)
            if isinstance(node, Tag)
            for raw in [_first_attribute(node, "src", "data-src", "href")]
            if raw
        ]
        if paths:
            return _dedupe(paths)
    return product_images


def _description_images(soup: BeautifulSoup, *, base_url: str) -> list[str]:
    selectors = (
        "#tab-description img",
        ".product-description img",
        '[itemprop="description"] img',
        ".description img",
    )
    values = [
        urljoin(base_url, raw)
        for selector in selectors
        for node in soup.select(selector)
        if isinstance(node, Tag)
        for raw in [_first_attribute(node, "src", "data-src", "href")]
        if raw
    ]
    return _dedupe(values)


def _internal_links(soup: BeautifulSoup, *, base_url: str) -> list[str]:
    base = urlsplit(base_url)
    links: list[str] = []
    for node in soup.find_all("a", href=True):
        raw = _text(node.get("href"))
        if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, raw)
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.casefold() != base.netloc.casefold():
            continue
        links.append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")))
    return _dedupe(links)


def _visible_texts(nodes: Iterable[Tag]) -> list[str]:
    return [
        text
        for node in nodes
        if _is_visible(node)
        for text in [_normalize_text(node.get_text(" ", strip=True))]
        if text
    ]


def _is_visible(node: Tag) -> bool:
    current: Tag | None = node
    while current is not None:
        if current.has_attr("hidden") or _casefold(current.get("aria-hidden")) == "true":
            return False
        style = _casefold(current.get("style"))
        if re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", style):
            return False
        classes = {_casefold(value) for value in current.get("class", [])}
        if classes & {"hidden", "sr-only", "visually-hidden"}:
            return False
        parent = current.parent
        current = parent if isinstance(parent, Tag) else None
    return True


def _text_check(check_id: str, observed: Any, expected: str) -> dict[str, Any]:
    actual = _normalize_text(observed)
    matches = bool(actual) and (not expected or _same_text(actual, expected))
    return _presence_or_match_check(
        check_id,
        observed=actual,
        expected=expected or "non-empty",
        matches=matches,
    )


def _presence_or_match_check(
    check_id: str, *, observed: Any, expected: Any, matches: bool
) -> dict[str, Any]:
    return _check(
        check_id,
        "pass" if matches else "fail",
        observed=observed,
        expected=expected,
    )


def _check(
    check_id: str,
    status: str,
    *,
    observed: Any = None,
    expected: Any = None,
    message: str | None = None,
    evidence: Iterable[Any] = (),
) -> dict[str, Any]:
    default_message = {
        "pass": "Live validation passed.",
        "warn": "Live validation completed with a warning.",
        "fail": "Live validation failed.",
        "not_applicable": "Live validation is not applicable.",
        "not_run": "Live validation was not run.",
    }.get(status, status)
    severity = "error" if status == "fail" else ("warning" if status == "warn" else "info")
    return {
        "id": check_id,
        "status": status,
        "blocks_apply": status == "fail",
        "severity": severity,
        "message": message or default_message,
        "observed": observed,
        "expected": expected,
        "evidence": list(evidence),
    }


def _not_run_check(check_id: str, reason: str) -> dict[str, Any]:
    return _check(
        check_id,
        "not_run",
        message="Live validation was not run because access was unavailable.",
        evidence=[reason],
    )


def _build_report(
    checks: Iterable[Mapping[str, Any]],
    *,
    model: str | None,
    target_url: str,
    access: Mapping[str, Any],
) -> dict[str, Any]:
    materialized = [dict(check) for check in checks]
    total = len(materialized)
    evaluated = sum(1 for check in materialized if check.get("status") != "not_run")
    percentage = _round_half_up(Decimal("100") * evaluated / total) if total else 0
    counts = {
        status: sum(1 for check in materialized if check.get("status") == status)
        for status in ("pass", "warn", "fail", "not_applicable", "not_run")
    }
    checklist = [
        {"check_id": check_id, "action": action} for check_id, action in LIVE_CHECKS
    ]
    if counts["fail"]:
        status = "fail"
    elif counts["warn"] or (counts["not_run"] and evaluated):
        status = "warn"
    elif counts["not_run"]:
        status = "not_run"
    else:
        status = "pass"
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": _text(model),
        "status": status,
        "reason": access.get("error_code") if status == "not_run" else None,
        "target_url": target_url,
        "access": dict(access),
        "coverage": {
            "total_checks": total,
            "evaluated_checks": evaluated,
            "percentage": percentage,
        },
        "summary": {
            "passed": counts["pass"],
            "warnings": counts["warn"],
            "failed": counts["fail"],
            "not_applicable": counts["not_applicable"],
            "not_run": counts["not_run"],
        },
        "checks": materialized,
        "manual_validation_checklist": checklist,
    }


def _access_base(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "authentication_attempted": False,
        "anti_bot_bypass_attempted": False,
        "googlebot_blocking_inferred": False,
    }


def _expected_product_url(expected: Mapping[str, Any]) -> str:
    return _first_expected_text(expected, "product_url", "canonical_url", "url")


def _first_expected_text(expected: Mapping[str, Any], *keys: str) -> str:
    return _text(_first_expected_value(expected, *keys))


def _first_expected_value(expected: Mapping[str, Any], *keys: str) -> Any:
    mappings = [expected]
    for container_key in ("product", "row", "current", "after"):
        value = expected.get(container_key)
        if isinstance(value, Mapping):
            mappings.append(value)
    for mapping in mappings:
        for key in keys:
            value = mapping.get(key)
            if _present(value):
                return value
    return None


def _expected_strings(expected: Mapping[str, Any], *keys: str) -> list[str]:
    value = _first_expected_value(expected, *keys)
    if isinstance(value, list):
        return [_normalize_text(item) for item in value if _normalize_text(item)]
    text = _normalize_text(value)
    return [text] if text else []


def _expected_gallery(expected: Mapping[str, Any]) -> list[str]:
    explicit = _first_expected_value(expected, "gallery_order", "gallery_images")
    values: list[Any]
    if isinstance(explicit, list):
        values = explicit
    elif explicit:
        values = str(explicit).split(":::")
    else:
        additional = _first_expected_value(
            expected, "additional_image", "additional_images"
        )
        if isinstance(additional, list):
            values = list(additional)
        else:
            values = str(additional or "").split(":::") if additional else []
        main_image = _first_expected_text(expected, "image", "main_image")
        if values and main_image:
            values.insert(0, main_image)
    result = []
    for value in values:
        if isinstance(value, Mapping):
            text = _text(value.get("public_path") or value.get("path") or value.get("url"))
        else:
            text = _text(value)
        if text:
            result.append(text)
    return result


def _expected_description_h2(expected: Mapping[str, Any]) -> list[str]:
    html = _first_expected_text(expected, "description", "product_description")
    if html:
        soup = BeautifulSoup(html, "lxml")
        headings = [
            _normalize_text(node.get_text(" ", strip=True))
            for node in soup.find_all("h2")
            if _normalize_text(node.get_text(" ", strip=True))
        ]
        if headings:
            return headings
    explicit = _first_expected_value(
        expected, "description_h2", "description_heading"
    )
    values = explicit if isinstance(explicit, list) else [explicit]
    return [
        normalized
        for value in values
        for normalized in [_normalize_text(_text(value))]
        if normalized
    ]


def _expected_description_images(
    expected: Mapping[str, Any], base_url: str
) -> list[str]:
    html = _first_expected_text(expected, "description", "product_description")
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    return _dedupe(
        urljoin(base_url, raw)
        for node in soup.find_all("img")
        if isinstance(node, Tag)
        for raw in [_first_attribute(node, "src", "data-src", "href")]
        if raw
    )


def _expected_internal_links(expected: Mapping[str, Any]) -> list[str]:
    value = _first_expected_value(expected, "internal_links")
    return _dedupe(
        [
            text
            for item in _flatten_expected_values(value)
            for text in [_text(item)]
            if text.startswith(("/", "http://", "https://"))
        ]
    )


def _flatten_expected_values(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _flatten_expected_values(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _flatten_expected_values(nested)
    else:
        yield value


def _expected_gtin(expected: Mapping[str, Any]) -> str:
    return _first_expected_text(
        expected, "gtin14", "gtin13", "gtin12", "gtin8", "gtin", "ean", "upc"
    )


def _expected_availability(expected: Mapping[str, Any]) -> str:
    explicit = _normalize_availability(
        _first_expected_value(expected, "availability", "offer_availability")
    )
    if explicit:
        return explicit
    quantity = _integer(_first_expected_value(expected, "quantity"))
    status = _integer(_first_expected_value(expected, "status"))
    if status == 0 or quantity == 0:
        return "outofstock"
    if status == 1 and quantity is not None and quantity > 0:
        return "instock"
    return ""


def _normalize_availability(value: Any) -> str:
    text = _casefold(value).rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]+", "", text)


def _first_product_value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if _present(value):
            return value
    return None


def _decimal_text(value: Any) -> str:
    text = _text(value).replace("\u00a0", "").replace(" ", "")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return ""
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        value_decimal = Decimal(text)
    except InvalidOperation:
        return ""
    return format(value_decimal.normalize(), "f")


def _urls_equal(actual: str, expected: str, base_url: str) -> bool:
    if not actual or not expected:
        return False
    return _normalized_url(actual, base_url) == _normalized_url(expected, base_url)


def _normalized_url(value: str, base_url: str) -> tuple[str, str, str, str]:
    parsed = urlsplit(urljoin(base_url, value))
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    port = parsed.port
    netloc = hostname
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return scheme, netloc, path, parsed.query


def _redirect_urls(response: Mapping[str, Any]) -> list[str]:
    raw = response.get("redirect_chain")
    if raw is None:
        raw = response.get("redirect_urls")
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        return [""]
    result: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            value = _text(
                item.get("url") or item.get("final_url") or item.get("location")
            )
        else:
            value = _text(item)
        result.append(value)
    return result


def _safe_url(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    try:
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return ""
    formatted_hostname = f"[{hostname}]" if ":" in hostname else hostname
    netloc = formatted_hostname
    if port is not None:
        netloc = f"{formatted_hostname}:{port}"
    safe_query = urlencode(
        [
            (key, "[redacted]" if key.casefold() in _SENSITIVE_QUERY_KEYS else item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parsed.scheme, netloc, parsed.path, safe_query, ""))


def _valid_public_http_url(value: str) -> bool:
    return _public_http_url_error(value) is None


def _public_http_url_error(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return "invalid_url"
    hostname = (parsed.hostname or "").strip().casefold().rstrip(".")
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and port == 0)
    ):
        return "invalid_url"
    if _is_local_hostname(hostname):
        return "blocked_non_public_destination"
    literal = _parse_ip_address(hostname)
    if literal is not None and not _is_public_address(literal):
        return "blocked_non_public_destination"
    return None


def _assert_public_http_url(value: str) -> None:
    error = _public_http_url_error(value)
    if error is not None:
        raise _BlockedLiveDestination(
            "Live URL is invalid or resolves to a non-public destination."
        )


def _resolve_public_addresses(host: str, port: int) -> tuple[str, ...]:
    hostname = _text(host).casefold().rstrip(".")
    if not hostname or _is_local_hostname(hostname):
        raise _BlockedLiveDestination(
            "Live hostname is not eligible for outbound validation."
        )

    literal = _parse_ip_address(hostname)
    if literal is not None:
        if not _is_public_address(literal):
            raise _BlockedLiveDestination(
                "Live hostname resolves to a non-public destination."
            )
        return (str(literal),)

    try:
        resolved = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (OSError, UnicodeError) as exc:
        raise _LiveDestinationResolutionError(
            "Live hostname could not be resolved safely."
        ) from exc

    addresses: list[str] = []
    seen: set[str] = set()
    for family, _socket_type, _protocol, _canonical_name, socket_address in resolved:
        if family not in {socket.AF_INET, socket.AF_INET6} or not socket_address:
            continue
        parsed_address = _parse_ip_address(_text(socket_address[0]))
        if parsed_address is None or not _is_public_address(parsed_address):
            raise _BlockedLiveDestination(
                "Live hostname resolves to a non-public destination."
            )
        normalized = str(parsed_address)
        if normalized not in seen:
            seen.add(normalized)
            addresses.append(normalized)
    if not addresses:
        raise _LiveDestinationResolutionError(
            "Live hostname did not resolve to a usable public destination."
        )
    return tuple(addresses)


def _assert_public_peer(response: httpx.Response) -> None:
    stream = response.extensions.get("network_stream")
    get_extra_info = getattr(stream, "get_extra_info", None)
    peer = get_extra_info("server_addr") if callable(get_extra_info) else None
    peer_host = peer[0] if isinstance(peer, tuple) and peer else None
    address = _parse_ip_address(_text(peer_host))
    if address is None or not _is_public_address(address):
        raise _BlockedLiveDestination(
            "Live connection peer could not be verified as public."
        )


def _is_local_hostname(hostname: str) -> bool:
    normalized = hostname.casefold().rstrip(".")
    return (
        normalized in _LOCAL_HOSTNAMES
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
    )


def _parse_ip_address(value: str) -> IPv4Address | IPv6Address | None:
    candidate = value.split("%", 1)[0]
    try:
        return ip_address(candidate)
    except ValueError:
        return None


def _is_public_address(address: IPv4Address | IPv6Address) -> bool:
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_reserved
    )


def _bounded_timeout(value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return min(MAX_TIMEOUT_SECONDS, max(0.1, parsed))


def _same_identifier(left: str, right: str) -> bool:
    normalize = lambda value: re.sub(r"[^a-z0-9]+", "", _casefold(value))
    return bool(normalize(left)) and normalize(left) == normalize(right)


def _same_text(left: Any, right: Any) -> bool:
    return _casefold(_normalize_text(left)) == _casefold(_normalize_text(right))


def _normalize_text(value: Any) -> str:
    return " ".join(_text(value).split())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _casefold(value: Any) -> str:
    return _text(value).casefold()


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", _text(value))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _first_attribute(node: Tag, *names: str) -> str:
    return next((_text(node.get(name)) for name in names if _text(node.get(name))), "")


def _rel_contains(value: Any, token: str) -> bool:
    values = value if isinstance(value, list) else _text(value).split()
    return token.casefold() in {_casefold(item) for item in values}


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
