from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Any, Iterable
from urllib.parse import urljoin

from ecommerce.source_capture.types import ParsedOfferObservation, ParsedPriceObservation


SKROUTZ_BASE_URL = "https://www.skroutz.gr"

PRICE_KEYS = ("price", "final_price", "finalprice", "current_price", "currentprice", "sale_price", "saleprice", "amount", "price_with_vat")
PRICE_SUMMARY_KEYS = ("price_min", "min_price", "minimum_price", "lowest_price", "best_price")
ORIGINAL_PRICE_KEYS = ("original_price", "originalprice", "old_price", "oldprice", "initial_price", "list_price", "retail_price")
SELLER_KEYS = ("seller", "seller_name", "sellername", "shop", "shop_name", "shopname", "store", "store_name", "storename", "merchant")
AVAILABILITY_KEYS = (
    "availability",
    "availability_label",
    "availability_text",
    "availabilitytext",
    "stock",
    "stock_status",
    "stockstatus",
)
SHIPPING_KEYS = ("shipping", "shipping_cost", "shippingcost", "delivery_cost", "deliverycost", "shipping_price", "shippingprice")
DELIVERY_KEYS = (
    "delivery",
    "delivery_text",
    "deliverytext",
    "delivery_time",
    "deliverytime",
    "shipping_text",
    "shippingtext",
    "dispatch_time",
)
SELLER_URL_KEYS = ("seller_url", "shop_url", "url", "path", "web_uri", "relative_url")


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


def parse_skroutz_offers(payload: Any, *, shops_payload: Any = None) -> tuple[list[ParsedOfferObservation], list[str]]:
    data = _json_payload(payload)
    shops = _skroutz_shop_details_by_id(_json_payload(shops_payload))
    offers = _parse_skroutz_product_cards(data, shops)
    if offers:
        return offers, []

    offers = []
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
                seller_url=_absolute_skroutz_url(_first_text_from_keys(node, SELLER_URL_KEYS)),
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


def _parse_skroutz_product_cards(data: Any, shops: dict[str, dict[str, Any]]) -> list[ParsedOfferObservation]:
    if not isinstance(data, dict) or not isinstance(data.get("product_cards"), list):
        return []
    offers: list[ParsedOfferObservation] = []
    for card in data["product_cards"]:
        if not isinstance(card, dict):
            continue
        price = _first_decimal_from_keys(card, PRICE_KEYS) or _first_decimal_from_keys(_nested_dict(card, ("pricing", "price")), PRICE_KEYS)
        if price is None:
            continue
        shop_id = _shop_id(card)
        shop = shops.get(shop_id or "", {})
        seller = (
            _first_text_from_keys(card, SELLER_KEYS)
            or _first_text_from_keys(_nested_dict(card, ("seller", "shop", "store")), ("name", "title"))
            or _first_text_from_keys(shop, ("name", "title", "shop_name", "display_name"))
        )
        seller_url = _absolute_skroutz_url(
            _first_text_from_keys(card, SELLER_URL_KEYS)
            or _first_text_from_keys(_nested_dict(card, ("seller", "shop", "store")), SELLER_URL_KEYS)
            or _first_text_from_keys(shop, SELLER_URL_KEYS)
        )
        availability = _first_text_from_keys(card, AVAILABILITY_KEYS) or _first_text_from_keys(
            _nested_dict(card, ("availability", "stock")),
            AVAILABILITY_KEYS + ("text", "title", "label"),
        )
        pricing_node = _nested_dict(card, ("pricing", "price"))
        shipping_node = _nested_dict(card, ("shipping", "delivery"))
        offers.append(
            ParsedOfferObservation(
                seller_name=seller,
                seller_url=seller_url,
                price=price,
                original_price=_first_decimal_from_keys(card, ORIGINAL_PRICE_KEYS) or _first_decimal_from_keys(pricing_node, ORIGINAL_PRICE_KEYS),
                currency=_first_text_from_keys(card, ("currency",)) or "EUR",
                availability=availability,
                stock_status=availability,
                shipping_cost=_first_decimal_from_keys(card, SHIPPING_KEYS)
                or _first_decimal_from_keys(shipping_node, SHIPPING_KEYS + PRICE_KEYS),
                delivery_text=_first_text_from_keys(card, DELIVERY_KEYS)
                or _first_text_from_keys(shipping_node, DELIVERY_KEYS + ("text", "title", "description", "label")),
                raw_observation={
                    "parser": "skroutz_filter_products_v1",
                    "shop_id": shop_id,
                    "card": card,
                    "shop": shop or None,
                },
            )
        )
    return offers


def _skroutz_shop_details_by_id(payload: Any) -> dict[str, dict[str, Any]]:
    shops: dict[str, dict[str, Any]] = {}
    for node in _walk_json(payload):
        if not isinstance(node, dict):
            continue
        shop_id = _shop_id(node)
        if not shop_id:
            continue
        if not (
            _first_text_from_keys(node, ("name", "title", "shop_name", "display_name"))
            or _first_text_from_keys(node, SELLER_URL_KEYS)
        ):
            continue
        shops[shop_id] = node
    return shops


def _shop_id(node: dict[str, Any]) -> str | None:
    normalized = {_normalize_key(key): value for key, value in node.items()}
    for key in ("shop_id", "shopid", "id"):
        value = normalized.get(_normalize_key(key))
        if value is not None:
            text = _clean_html_text(value)
            if text:
                return text
    shop = _nested_dict(node, ("shop", "seller", "store"))
    if shop:
        return _shop_id(shop)
    return None


def _absolute_skroutz_url(value: str | None) -> str | None:
    if not value:
        return None
    return urljoin(SKROUTZ_BASE_URL, value)


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
