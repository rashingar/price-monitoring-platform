from __future__ import annotations

import json
import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Any, Iterable
from urllib.parse import urljoin

from ecommerce.source_capture.types import ParsedOfferObservation, ParsedPriceObservation


BESTPRICE_BASE_URL = "https://www.bestprice.gr"
SKROUTZ_BASE_URL = "https://www.skroutz.gr"

PRICE_KEYS = ("price", "final_price", "finalprice", "current_price", "currentprice", "sale_price", "saleprice", "amount", "price_with_vat")
LANDED_PRICE_KEYS = (
    "landed_price",
    "landedprice",
    "total_price",
    "totalprice",
    "final_total",
    "finaltotal",
    "final_price_with_shipping",
    "price_with_shipping",
    "total_with_shipping",
)
PRICE_SUMMARY_KEYS = ("price_min", "min_price", "minimum_price", "lowest_price", "lowestprice", "low_price", "lowprice", "best_price")
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


def parse_bestprice_html(html: str, *, page_url: str) -> tuple[ParsedPriceObservation, list[str]]:
    flags: list[str] = []
    structured = _extract_product_structured_data(html)
    page_data = _extract_bestprice_page_data(html)
    page_payload = page_data.get("PAGE") if isinstance(page_data.get("PAGE"), dict) else {}
    best_price_data = page_payload.get("bestPrice") if isinstance(page_payload.get("bestPrice"), dict) else {}
    offers = _nested_dict(structured, ("offers",))
    title = _first_text_from_keys(structured, ("name", "title")) or _first_match(
        html,
        (
            r"<meta(?=[^>]+(?:property|name)=[\"']og:title[\"'])(?=[^>]+content=[\"']([^\"']+)[\"'])[^>]*>",
            r"<title[^>]*>(.*?)</title>",
            r"<h1[^>]*>(.*?)</h1>",
        ),
    )
    price = (
        _bestprice_cents_to_decimal(best_price_data.get("price"))
        or _first_decimal_from_keys(offers, PRICE_SUMMARY_KEYS + PRICE_KEYS)
        or _first_decimal_from_keys(structured, tuple(f"offers_{key}" for key in PRICE_SUMMARY_KEYS + PRICE_KEYS))
        or _first_decimal(
            _first_match(
                html,
                (
                    r"class=[\"'][^\"']*item-price-button__label[^\"']*[\"'][^>]*>.*?<strong[^>]*>([^<]+)",
                    r"class=[\"'][^\"']*price[^\"']*[\"'][^>]*>\s*(?:Από\s*)?<strong[^>]*>([^<]+)",
                    r"\"lowPrice\"\s*:\s*\"?([0-9]+(?:[.,][0-9]+)?)",
                    r"\"low_price\"\s*:\s*\"?([0-9]+(?:[.,][0-9]+)?)",
                ),
            )
        )
    )
    merchant = _clean_html_text(best_price_data.get("merchant"))
    merchant_link = _absolute_bestprice_url(_clean_html_text(best_price_data.get("link")))
    if price is None:
        flags.append("PRICE_MISSING")
    if not merchant:
        flags.append("MERCHANT_MISSING")
    availability = _normalize_availability(
        _first_text_from_keys(offers, AVAILABILITY_KEYS) or _first_text_from_keys(structured, ("offers_availability", "availability"))
    )
    offer_count = _first_text_from_keys(offers, ("offer_count", "offercount")) or _first_text_from_keys(
        structured,
        ("offers_offercount", "offercount"),
    )
    observation = ParsedPriceObservation(
        price=price,
        currency=_first_text_from_keys(offers, ("price_currency", "pricecurrency", "currency"))
        or _first_text_from_keys(structured, ("offers_pricecurrency", "currency"))
        or "EUR",
        availability=availability,
        stock_status=availability,
        seller_name=merchant,
        product_name=_clean_html_text(title),
        raw_observation={
            "page_url": page_url,
            "parser": "bestprice_html_v1",
            "title": _clean_html_text(title),
            "availability": availability,
            "offer_count": offer_count,
            "bestprice_best_store": merchant,
            "bestprice_best_store_price": str(price) if price is not None else None,
            "bestprice_best_store_url": merchant_link,
            "structured_data_found": bool(structured),
            "bp_data_found": bool(page_data),
        },
    )
    return observation, flags


def parse_bestprice_offers(html: str, *, page_url: str) -> tuple[list[ParsedOfferObservation], list[str]]:
    del page_url
    offers: list[ParsedOfferObservation] = []
    for group_index, (group_start, group_tag) in enumerate(_tag_spans_with_class(html, "prices__group")):
        group_attrs = _html_attrs(group_tag)
        group_end = _next_tag_with_class_start(html, "prices__group", group_start + len(group_tag))
        group_html = html[group_start : group_end if group_end is not None else len(html)]
        group_rank = _int_text(group_attrs.get("data-id")) or group_index + 1
        group_price = _bestprice_cents_to_decimal(group_attrs.get("data-price"))
        seller_name = _bestprice_group_seller_name(group_html)
        seller_url = _absolute_bestprice_url(_first_match(group_html, (r"href=[\"']([^\"']*/to/[^\"']+)[\"']",)))

        product_tag_spans = list(_tag_spans_with_class(group_html, "prices__product"))
        if not product_tag_spans:
            offer = _bestprice_offer_from_values(
                seller_name=seller_name,
                seller_url=seller_url,
                price=group_price,
                rank=group_rank,
                raw={"parser": "bestprice_html_v1", "rank": group_rank, "group": _bestprice_raw_attrs(group_attrs)},
            )
            if offer is not None:
                offers.append(offer)
            continue

        for product_index, (product_start, product_tag) in enumerate(product_tag_spans, start=1):
            product_attrs = _html_attrs(product_tag)
            product_end = _next_tag_with_class_start(group_html, "prices__product", product_start + len(product_tag))
            product_html = group_html[product_start : product_end if product_end is not None else len(group_html)]
            product_link_attrs = _bestprice_product_link_attrs(product_html)
            product_url = _absolute_bestprice_url(product_link_attrs.get("href")) or seller_url
            product_price = _bestprice_cents_to_decimal(product_attrs.get("data-price")) or _bestprice_cents_to_decimal(
                product_link_attrs.get("data-price")
            ) or group_price
            original_price = _bestprice_cents_to_decimal(product_attrs.get("data-original-price")) or _bestprice_cents_to_decimal(
                product_link_attrs.get("data-original-price")
            )
            product_title = _clean_html_text(product_link_attrs.get("title")) or _clean_html_text(
                _first_match(product_html, (r"<h3[^>]*>(.*?)</h3>",))
            )
            availability = _bestprice_availability(product_html, product_attrs)
            shipping_cost = _bestprice_cents_to_decimal_allow_zero(product_attrs.get("data-shipping-cost"))
            landed_price, landed_price_source, landed_field = _bestprice_landed_price(product_price, shipping_cost, product_attrs, product_link_attrs)
            raw = {
                "parser": "bestprice_html_v1",
                "rank": group_rank,
                "product_index": product_index,
                "product_title": product_title,
                "item_price": str(product_price) if product_price is not None else None,
                "original_price": str(original_price) if original_price is not None else None,
                "shipping_cost": str(shipping_cost) if shipping_cost is not None else None,
                "landed_price": str(landed_price) if landed_price is not None else None,
                "landed_price_source": landed_price_source,
                "landed_price_field": landed_field,
                "group": _bestprice_raw_attrs(group_attrs),
                "product": _bestprice_raw_attrs(product_attrs),
            }
            offer = _bestprice_offer_from_values(
                seller_name=seller_name,
                seller_url=product_url,
                price=product_price,
                original_price=original_price,
                rank=group_rank,
                availability=availability,
                shipping_cost=shipping_cost,
                raw=raw,
            )
            if offer is not None:
                offers.append(offer)

    flags = [] if offers else ["NO_OFFER_OBSERVATIONS_PARSED"]
    return offers, flags


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
                    "parser": "skroutz_json_summary_v1",
                    "source": "json_summary",
                    "payload": node,
                },
            ),
            [],
        )
    return None, ["PRICE_MISSING"]


def parse_skroutz_firecrawl_content(
    content: str,
    *,
    page_url: str,
    data: Any = None,
) -> tuple[list[ParsedOfferObservation], ParsedPriceObservation | None, list[str]]:
    flags: list[str] = []

    offers, offer_flags = parse_skroutz_offers(data)
    if offers:
        return _firecrawl_offers(offers, source="firecrawl_data"), None, []
    flags.extend(flag for flag in offer_flags if flag not in flags)

    for payload in _json_ld_payloads(content):
        offers, offer_flags = parse_skroutz_offers(payload)
        if offers:
            return _firecrawl_offers(offers, source="firecrawl_json_ld"), None, [flag for flag in offer_flags if flag not in flags]
        flags.extend(flag for flag in offer_flags if flag not in flags)

    table_offers = _parse_skroutz_firecrawl_tables(content, page_url=page_url)
    if table_offers:
        return table_offers, None, []

    line_offers = _parse_skroutz_firecrawl_lines(content, page_url=page_url)
    if line_offers:
        return line_offers, None, []

    price_observation, price_flags = parse_skroutz_price_summary(data, page_url=page_url)
    if price_observation is None:
        for payload in _json_ld_payloads(content):
            price_observation, price_flags = parse_skroutz_price_summary(payload, page_url=page_url)
            if price_observation is not None:
                break
    if price_observation is None:
        price_observation = _parse_skroutz_firecrawl_price_summary(content, page_url=page_url)
        price_flags = [] if price_observation is not None else price_flags
    if price_observation is not None:
        price_observation = replace(
            price_observation,
            raw_observation={
                **price_observation.raw_observation,
                "parser": "skroutz_firecrawl_v1",
                "source": "firecrawl_summary",
            },
        )
        flags.extend(flag for flag in price_flags if flag not in flags)
        flags.append("NO_OFFER_OBSERVATIONS_PARSED")
        return [], price_observation, list(dict.fromkeys(flags))

    flags.extend(flag for flag in price_flags if flag not in flags)
    return [], None, list(dict.fromkeys(flags or ["NO_OFFER_OBSERVATIONS_PARSED", "PRICE_MISSING"]))


def _parse_skroutz_firecrawl_tables(content: str, *, page_url: str) -> list[ParsedOfferObservation]:
    offers: list[ParsedOfferObservation] = []
    headers: list[str] = []
    for line in (content or "").splitlines():
        if "|" not in line:
            if line.strip():
                headers = []
            continue
        cells = [_clean_html_text(cell) or "" for cell in line.strip().strip("|").split("|")]
        if not cells or all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if not any(_first_decimal(cell) for cell in cells):
            headers = [_normalize_key(cell) for cell in cells]
            continue
        if "€" not in line and not headers:
            continue

        seller_index = _first_header_index(headers, ("store", "shop", "seller", "merchant", "καταστημα", "πωλητης")) or 0
        price_index = _first_header_index(headers, ("item_price", "price", "τιμη")) or _first_price_cell_index(cells)
        shipping_index = _first_header_index(headers, ("shipping", "shipping_cost", "μεταφορικα", "αποστολη"))
        landed_index = _first_header_index(headers, ("landed", "total", "final", "συνολο", "τελικη"))
        if price_index is None:
            continue

        seller_cell = cells[seller_index] if seller_index < len(cells) else ""
        price = _first_decimal(cells[price_index])
        if price is None:
            continue
        shipping = _first_decimal(cells[shipping_index]) if shipping_index is not None and shipping_index < len(cells) else None
        landed = _first_decimal(cells[landed_index]) if landed_index is not None and landed_index < len(cells) else None
        landed_source = "explicit" if landed is not None else "computed" if price is not None and shipping is not None else "missing"
        if landed is None and shipping is not None:
            landed = (price + shipping).quantize(Decimal("0.01"))

        seller_name = _markdown_link_text(seller_cell) or seller_cell
        seller_url = _absolute_skroutz_url(_markdown_link_url(seller_cell) or _first_match(seller_cell, (r"href=[\"']([^\"']+)[\"']",)))
        offers.append(
            ParsedOfferObservation(
                seller_name=_clean_html_text(seller_name),
                seller_url=seller_url,
                price=price,
                currency="EUR",
                shipping_cost=shipping,
                raw_observation={
                    "parser": "skroutz_firecrawl_v1",
                    "rank": len(offers) + 1,
                    "page_url": page_url,
                    "source": "firecrawl_table",
                    "row": cells,
                    "landed_price": str(landed) if landed is not None else None,
                    "landed_price_source": landed_source,
                },
            )
        )
    return offers


def _firecrawl_offers(offers: list[ParsedOfferObservation], *, source: str) -> list[ParsedOfferObservation]:
    return [
        replace(
            offer,
            raw_observation={
                **offer.raw_observation,
                "parser": "skroutz_firecrawl_v1",
                "source": source,
            },
        )
        for offer in offers
    ]


def _parse_skroutz_firecrawl_lines(content: str, *, page_url: str) -> list[ParsedOfferObservation]:
    offers: list[ParsedOfferObservation] = []
    for line in (content or "").splitlines():
        text = _clean_html_text(line)
        if not text or "€" not in text:
            continue
        match = re.search(
            r"^(?:\d+[\).]\s*)?(?P<seller>[A-Za-zΑ-Ωα-ω0-9][^€|]{1,80}?)\s+(?P<price>[0-9]+(?:[.,][0-9]{1,2})?)\s*€",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        seller = _clean_html_text(match.group("seller"))
        price = _first_decimal(match.group("price"))
        if not seller or price is None:
            continue
        after_price = text[match.end() :]
        shipping = _first_decimal(_first_match(after_price, (r"(?:shipping|μεταφορικά|μεταφορικα|αποστολή|αποστολη)[^\d]{0,20}([0-9]+(?:[.,][0-9]{1,2})?)",)))
        landed = (price + shipping).quantize(Decimal("0.01")) if shipping is not None else None
        offers.append(
            ParsedOfferObservation(
                seller_name=seller,
                seller_url=_absolute_skroutz_url(_markdown_link_url(line)),
                price=price,
                currency="EUR",
                shipping_cost=shipping,
                raw_observation={
                    "parser": "skroutz_firecrawl_v1",
                    "rank": len(offers) + 1,
                    "page_url": page_url,
                    "source": "firecrawl_line",
                    "line": text,
                    "landed_price": str(landed) if landed is not None else None,
                    "landed_price_source": "computed" if landed is not None else "missing",
                },
            )
        )
    return offers


def _parse_skroutz_firecrawl_price_summary(content: str, *, page_url: str) -> ParsedPriceObservation | None:
    text = _clean_html_text(content)
    if not text:
        return None
    price = _first_decimal(_first_match(text, (r"(?:από|from|lowest|τιμή)[^\d]{0,40}([0-9]+(?:[.,][0-9]{1,2})?)\s*€",)))
    if price is None:
        return None
    return ParsedPriceObservation(
        price=price,
        currency="EUR",
        raw_observation={
            "page_url": page_url,
            "parser": "skroutz_firecrawl_v1",
            "source": "firecrawl_price_summary",
        },
    )


def _first_header_index(headers: list[str], tokens: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        if any(token in header for token in tokens):
            return index
    return None


def _first_price_cell_index(cells: list[str]) -> int | None:
    for index, cell in enumerate(cells):
        if _first_decimal(cell) is not None:
            return index
    return None


def _markdown_link_text(value: str) -> str | None:
    return _first_match(value, (r"\[([^\]]+)\]\([^)]+\)",))


def _markdown_link_url(value: str) -> str | None:
    return _first_match(value, (r"\[[^\]]+\]\(([^)]+)\)",))


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
                    "parser": "skroutz_json_offer_v1",
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


def _absolute_bestprice_url(value: str | None) -> str | None:
    if not value:
        return None
    return urljoin(BESTPRICE_BASE_URL, value)


def _bestprice_offer_from_values(
    *,
    seller_name: str | None,
    seller_url: str | None,
    price: Decimal | None,
    rank: int,
    original_price: Decimal | None = None,
    availability: str | None = None,
    shipping_cost: Decimal | None = None,
    raw: dict[str, Any] | None = None,
) -> ParsedOfferObservation | None:
    if price is None or price <= 0:
        return None
    return ParsedOfferObservation(
        seller_name=seller_name,
        seller_url=seller_url,
        price=price,
        original_price=original_price,
        currency="EUR",
        availability=availability,
        stock_status=availability,
        shipping_cost=shipping_cost,
        raw_observation=raw or {"parser": "bestprice_html_v1", "rank": rank},
    )


def _bestprice_group_seller_name(group_html: str) -> str | None:
    for class_name in ("prices__merchant-logo", "prices__merchant-link"):
        attrs = _first_attrs_with_class(group_html, class_name)
        seller = _clean_html_text(attrs.get("aria-label") or attrs.get("title") or attrs.get("alt"))
        if seller:
            return seller
    seller = _first_match(group_html, (r"<em[^>]*>(.*?)</em>", r"<img[^>]+(?:alt|title)=[\"']([^\"']+)[\"'][^>]*>"))
    return _clean_html_text(seller)


def _bestprice_product_link_attrs(product_html: str) -> dict[str, str]:
    to_link_match = re.search(r"<a\b(?=[^>]+href=[\"'][^\"']*/to/[^\"']+[\"'])[^>]*>", product_html or "", flags=re.IGNORECASE | re.DOTALL)
    if to_link_match:
        return _html_attrs(to_link_match.group(0))
    price_link_match = re.search(r"<a\b(?=[^>]+data-price=)[^>]*>", product_html or "", flags=re.IGNORECASE | re.DOTALL)
    if price_link_match:
        return _html_attrs(price_link_match.group(0))
    return {}


def _bestprice_availability(product_html: str, product_attrs: dict[str, str]) -> str | None:
    if "data-in-stock" in product_attrs:
        return "in_stock"
    status = _first_match(product_html, (r"data-status=[\"']([^\"']+)[\"']",))
    if status:
        return _normalize_availability(status)
    return _clean_html_text(_first_match(product_html, (r"class=[\"'][^\"']*\bav\b[^\"']*[\"'][^>]*>.*?<small[^>]*>(.*?)</small>",)))


def _bestprice_raw_attrs(attrs: dict[str, str]) -> dict[str, str]:
    allowed = {
        "data-id",
        "data-price",
        "data-original-price",
        "data-total-price",
        "data-landed-price",
        "data-price-with-shipping",
        "data-mid",
        "data-domain",
        "data-mrating",
        "data-index",
        "data-shipping-cost",
        "data-product-id",
        "data-av",
    }
    return {key: value for key, value in attrs.items() if key in allowed and value != ""}


def _bestprice_landed_price(
    item_price: Decimal | None,
    shipping_cost: Decimal | None,
    *nodes: dict[str, str],
) -> tuple[Decimal | None, str, str | None]:
    for node in nodes:
        for key in LANDED_PRICE_KEYS:
            attr_key = f"data-{key.replace('_', '-')}"
            if attr_key not in node:
                continue
            landed_price = _bestprice_cents_to_decimal(node.get(attr_key))
            if landed_price is not None:
                return landed_price, "explicit", attr_key
    if item_price is not None and shipping_cost is not None:
        return (item_price + shipping_cost).quantize(Decimal("0.01")), "computed", None
    return None, "missing", None


def _bestprice_cents_to_decimal(value: object) -> Decimal | None:
    text = _clean_html_text(value)
    if not text:
        return None
    try:
        if "." in text or "," in text:
            amount = Decimal(text.replace(",", "."))
        else:
            amount = Decimal(text) / Decimal("100")
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _bestprice_cents_to_decimal_allow_zero(value: object) -> Decimal | None:
    parsed = _bestprice_cents_to_decimal(value)
    if parsed is not None:
        return parsed
    text = _clean_html_text(value)
    if text == "0":
        return Decimal("0.00")
    return None


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


def _extract_bestprice_page_data(html: str) -> dict[str, Any]:
    match = re.search(
        r"<script[^>]+id=[\"']bp-data[\"'][^>]*>(.*?)</script>",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return {}
    text = unescape(match.group(1)).strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _tags_with_class(html: str, class_name: str) -> Iterable[str]:
    for _, tag in _tag_spans_with_class(html, class_name):
        yield tag


def _tag_spans_with_class(html: str, class_name: str) -> Iterable[tuple[int, str]]:
    for match in re.finditer(r"<[a-z0-9]+\b[^>]*>", html or "", flags=re.IGNORECASE | re.DOTALL):
        tag = match.group(0)
        attrs = _html_attrs(tag)
        classes = set((attrs.get("class") or "").split())
        if class_name in classes:
            yield match.start(), tag


def _next_tag_with_class_start(html: str, class_name: str, start: int) -> int | None:
    for match in re.finditer(r"<[a-z0-9]+\b[^>]*>", html[start:] or "", flags=re.IGNORECASE | re.DOTALL):
        tag = match.group(0)
        attrs = _html_attrs(tag)
        if class_name in set((attrs.get("class") or "").split()):
            return start + match.start()
    return None


def _first_attrs_with_class(html: str, class_name: str) -> dict[str, str]:
    for tag in _tags_with_class(html, class_name):
        return _html_attrs(tag)
    return {}


def _html_attrs(tag: str) -> dict[str, str]:
    match = re.match(r"<\s*[a-z0-9]+\b(?P<attrs>.*?)/?\s*>$", tag or "", flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    attrs: dict[str, str] = {}
    for attr_match in re.finditer(
        r"([:\w-]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+)))?",
        match.group("attrs"),
        flags=re.IGNORECASE | re.DOTALL,
    ):
        name = attr_match.group(1).casefold()
        value = next((part for part in attr_match.groups()[1:] if part is not None), "")
        attrs[name] = unescape(value)
    return attrs


def _int_text(value: object) -> int | None:
    text = _clean_html_text(value)
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


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


def _normalize_availability(value: object) -> str | None:
    text = _clean_html_text(value)
    if not text:
        return None
    token = text.rstrip("/").rsplit("/", 1)[-1]
    mapping = {
        "InStock": "in_stock",
        "OutOfStock": "out_of_stock",
        "PreOrder": "pre_order",
        "BackOrder": "back_order",
        "LimitedAvailability": "limited_availability",
        "Discontinued": "discontinued",
    }
    return mapping.get(token, text)
