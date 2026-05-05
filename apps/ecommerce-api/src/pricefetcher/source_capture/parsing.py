from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Any, Iterable

from pricefetcher.source_capture.types import ParsedOfferObservation, ParsedPriceObservation


PRICE_KEYS = ("price", "final_price", "finalprice", "current_price", "currentprice", "sale_price", "saleprice", "amount", "price_with_vat")
PRICE_SUMMARY_KEYS = ("price_min", "min_price", "minimum_price", "lowest_price", "best_price")
ORIGINAL_PRICE_KEYS = ("original_price", "originalprice", "old_price", "oldprice", "initial_price", "list_price", "retail_price")
SELLER_KEYS = ("seller", "seller_name", "sellername", "shop", "shop_name", "shopname", "store", "store_name", "storename", "merchant")
AVAILABILITY_KEYS = ("availability", "stock", "stock_status", "stockstatus", "availability_text", "availabilitytext")
SHIPPING_KEYS = ("shipping", "shipping_cost", "shippingcost", "delivery_cost", "deliverycost", "shipping_price", "shippingprice")
DELIVERY_KEYS = ("delivery", "delivery_text", "deliverytext", "delivery_time", "deliverytime", "shipping_text", "shippingtext")


def parse_electronet_html(html: str, *, page_url: str) -> tuple[ParsedPriceObservation, list[str]]:
    flags: list[str] = []
    structured = _extract_product_structured_data(html)
    title = _first_text_from_keys(structured, ("name", "title")) or _first_match(
        html,
        (
            r"<meta(?=[^>]+(?:property|name)=[\"']og:title[\"'])(?=[^>]+content=[\"']([^\"']+)[\"'])[^>]*>",
            r"<title[^>]*>(.*?)</title>",
            r"<h1[^>]*>(.*?)</h1>",
        ),
    )
    price = _first_decimal_from_keys(structured, PRICE_KEYS) or _first_decimal(
        _first_match(
            html,
            (
                r"<meta(?=[^>]+property=[\"']product:price:amount[\"'])(?=[^>]+content=[\"']([^\"']+)[\"'])[^>]*>",
                r"<meta(?=[^>]+itemprop=[\"']price[\"'])(?=[^>]+content=[\"']([^\"']+)[\"'])[^>]*>",
                r"data-price=[\"']([^\"']+)[\"']",
                r"([0-9]+(?:[.,][0-9]{2})?)\s*€",
            ),
        )
    )
    if price is None:
        flags.append("PRICE_MISSING")
    availability = _first_text_from_keys(structured, AVAILABILITY_KEYS) or _first_match(
        html,
        (
            r"<meta(?=[^>]+property=[\"']product:availability[\"'])(?=[^>]+content=[\"']([^\"']+)[\"'])[^>]*>",
            r"(?:Διαθεσιμότητα|Availability)[^<]{0,80}<[^>]+>([^<]+)",
        ),
    )
    if not availability:
        flags.append("AVAILABILITY_MISSING")
    observation = ParsedPriceObservation(
        price=price,
        currency="EUR",
        availability=_clean_html_text(availability),
        stock_status=_clean_html_text(availability),
        product_name=_clean_html_text(title),
        raw_observation={
            "page_url": page_url,
            "parser": "electronet_html_v1",
            "title": _clean_html_text(title),
            "availability": _clean_html_text(availability),
            "structured_data_found": bool(structured),
        },
    )
    return observation, flags


def parse_skroutz_offers(payload: Any) -> tuple[list[ParsedOfferObservation], list[str]]:
    data = _json_payload(payload)
    offers: list[ParsedOfferObservation] = []
    for node in _walk_json(data):
        if not isinstance(node, dict):
            continue
        price = _first_decimal_from_keys(node, PRICE_KEYS) or _first_decimal_from_keys(_nested_dict(node, ("price", "pricing")), PRICE_KEYS)
        seller = _first_text_from_keys(node, SELLER_KEYS) or _first_text_from_keys(_nested_dict(node, ("seller", "shop", "store")), ("name", "title"))
        if price is None or not seller:
            continue
        offers.append(
            ParsedOfferObservation(
                seller_name=seller,
                price=price,
                original_price=_first_decimal_from_keys(node, ORIGINAL_PRICE_KEYS),
                currency=_first_text_from_keys(node, ("currency",)) or "EUR",
                availability=_first_text_from_keys(node, AVAILABILITY_KEYS),
                stock_status=_first_text_from_keys(node, AVAILABILITY_KEYS),
                shipping_cost=_first_decimal_from_keys(node, SHIPPING_KEYS)
                or _first_decimal_from_keys(_nested_dict(node, ("shipping", "delivery")), SHIPPING_KEYS + PRICE_KEYS),
                delivery_text=_first_text_from_keys(node, DELIVERY_KEYS)
                or _first_text_from_keys(_nested_dict(node, ("shipping", "delivery")), DELIVERY_KEYS + ("text", "title", "description")),
                seller_url=_first_text_from_keys(node, ("seller_url", "shop_url", "url", "path")),
                raw_observation=node,
            )
        )
    flags = [] if offers else ["NO_OFFER_OBSERVATIONS_PARSED"]
    return offers, flags


def parse_skroutz_price_summary(payload: Any, *, page_url: str) -> tuple[ParsedPriceObservation | None, list[str]]:
    data = _json_payload(payload)
    for node in _walk_json(data):
        if not isinstance(node, dict):
            continue
        price = _first_decimal_from_keys(node, PRICE_SUMMARY_KEYS)
        if price is None:
            continue
        availability = _first_text_from_keys(node, AVAILABILITY_KEYS)
        return (
            ParsedPriceObservation(
                price=price,
                currency=_first_text_from_keys(node, ("currency",)) or "EUR",
                availability=availability,
                stock_status=availability,
                product_name=_first_text_from_keys(node, ("name", "title", "product_name", "productname")),
                raw_observation={
                    "page_url": page_url,
                    "parser": "skroutz_filter_products_v1",
                    "source": "filter_products",
                    "payload": node,
                },
            ),
            [],
        )
    return None, ["PRICE_MISSING"]


def parse_skroutz_visible_html_offers(html: str) -> tuple[list[ParsedOfferObservation], list[str]]:
    text = _clean_visible_text(html)
    if not text:
        return [], ["NO_OFFER_OBSERVATIONS_PARSED"]
    lines = [line for line in text.splitlines() if line.strip()]
    offers: list[ParsedOfferObservation] = []
    for index, line in enumerate(lines):
        if _looks_like_shipping_only_line(line):
            continue
        price = _first_decimal(line)
        if price is None or "€" not in line:
            continue
        seller = _nearest_seller_line(lines, index)
        if not seller:
            continue
        availability = _nearest_matching_line(lines, index, ("διαθε", "stock", "available", "παραδοση", "παράδοση"))
        shipping_line = _nearest_matching_line(lines, index, ("μεταφορ", "shipping", "courier", "delivery"))
        offers.append(
            ParsedOfferObservation(
                seller_name=seller,
                price=price,
                currency="EUR",
                availability=availability,
                stock_status=availability,
                shipping_cost=_first_decimal(shipping_line),
                delivery_text=shipping_line,
                raw_observation={
                    "parser": "skroutz_visible_html_v1",
                    "line": line,
                    "seller_line": seller,
                    "availability_line": availability,
                    "shipping_line": shipping_line,
                },
            )
        )
    flags = [] if offers else ["NO_OFFER_OBSERVATIONS_PARSED"]
    return offers, flags


def _json_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload


def _walk_json(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _extract_product_structured_data(html: str) -> dict[str, Any]:
    for payload in _json_ld_payloads(html):
        for node in _walk_json(payload):
            if not isinstance(node, dict):
                continue
            type_value = node.get("@type") or node.get("type")
            type_values = [str(item).lower() for item in type_value] if isinstance(type_value, list) else [str(type_value).lower()]
            if "product" in type_values or any(key in node for key in ("offers", "price", "sku", "mpn")):
                flattened = dict(node)
                offers = node.get("offers")
                if isinstance(offers, dict):
                    flattened.update({f"offers_{key}": value for key, value in offers.items()})
                    for key, value in offers.items():
                        flattened.setdefault(key, value)
                return flattened
    return {}


def _json_ld_payloads(html: str) -> Iterable[Any]:
    for match in re.finditer(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    ):
        text = unescape(match.group(1)).strip()
        if not text:
            continue
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            continue


def _nested_dict(node: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    normalized = {_normalize_key(key): value for key, value in node.items()}
    for key in keys:
        value = normalized.get(_normalize_key(key))
        if isinstance(value, dict):
            return value
    return {}


def _first_decimal_from_keys(node: dict[str, Any], keys: tuple[str, ...]) -> Decimal | None:
    normalized = {_normalize_key(key): value for key, value in node.items()}
    for key in keys:
        value = normalized.get(_normalize_key(key))
        parsed = _first_decimal(value)
        if parsed is not None:
            return parsed
    return None


def _first_text_from_keys(node: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    normalized = {_normalize_key(key): value for key, value in node.items()}
    for key in keys:
        value = normalized.get(_normalize_key(key))
        if isinstance(value, dict):
            nested = _first_text_from_keys(value, ("name", "title"))
            if nested:
                return nested
            continue
        text = _clean_html_text(value)
        if text:
            return text
    return None


def _normalize_key(value: object) -> str:
    return str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")


def _clean_visible_text(html: str) -> str:
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", "\n", html or "")
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def _nearest_seller_line(lines: list[str], price_index: int) -> str | None:
    for index in range(max(0, price_index - 10), price_index):
        candidate = _clean_html_text(lines[index])
        if candidate and _looks_like_seller_text(candidate):
            return candidate
    for index in range(price_index + 1, min(len(lines), price_index + 6)):
        candidate = _clean_html_text(lines[index])
        if candidate and _looks_like_seller_text(candidate):
            return candidate
    return None


def _nearest_matching_line(lines: list[str], price_index: int, markers: tuple[str, ...]) -> str | None:
    for index in range(price_index + 1, min(len(lines), price_index + 5)):
        candidate = _clean_html_text(lines[index])
        lowered = (candidate or "").casefold()
        if candidate and any(marker in lowered for marker in markers):
            return candidate
    return None


def _looks_like_seller_text(value: str) -> bool:
    lowered = value.casefold()
    if "€" in value or _first_decimal(value) is not None:
        return False
    noisy_markers = (
        "skroutz",
        "καταστήματα",
        "προσφορ",
        "διαθε",
        "δυνατότητα",
        "δυνατοτητα",
        "τηλεοράσεις",
        "αξεσουάρ",
        "σελίδα",
        "μεταφορ",
        "shipping",
        "delivery",
        "stock",
    )
    if any(marker in lowered for marker in noisy_markers):
        return False
    if lowered in {"από", "απο", "σε", "ή", "η"}:
        return False
    return 2 <= len(value) <= 80


def _looks_like_shipping_only_line(value: str) -> bool:
    lowered = value.casefold()
    shipping_markers = ("μεταφορ", "shipping", "courier", "delivery")
    seller_price_markers = ("τιμη", "τιμή", "price", "€")
    return any(marker in lowered for marker in shipping_markers) and not any(marker in lowered for marker in seller_price_markers[:-1])


def _first_match(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
    return None


def _first_decimal(value: object) -> Decimal | None:
    text = _clean_html_text(value)
    if not text:
        return None
    match = re.search(r"[0-9]+(?:[.,][0-9]{1,2})?", text.replace(" ", ""))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:
        return None


def _clean_html_text(value: object) -> str | None:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = " ".join(unescape(text).split())
    return text or None
