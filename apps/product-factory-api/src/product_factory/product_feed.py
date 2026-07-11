from __future__ import annotations

"""Internal product-feed candidate artifacts for the MPN-only contract."""

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .normalize import normalize_whitespace
from .structured_product import forbidden_identifier_keys


def build_product_feed(*, row: Mapping[str, Any], identity: Mapping[str, Any]) -> dict[str, object]:
    image_links = _image_urls(row)
    payload: dict[str, object] = {
        "id": _text(row.get("model")),
        "title": _text(row.get("name")),
        "description": _text(row.get("meta_description")),
        "link": _text(row.get("product_url")),
        "image_link": image_links[0] if image_links else "",
        "additional_image_links": image_links[1:],
        "brand": _text(identity.get("brand") or row.get("manufacturer")),
        "identifier_mode": "mpn_only",
        "condition": "new",
        "product_type": _text(row.get("category")),
        "source_provenance": {
            "mpn": _text(identity.get("source")),
            "price": "operator_or_source",
            "availability": "csv_inventory",
        },
    }
    if identity.get("mpn_status") == "verified" and _text(identity.get("mpn")):
        payload["mpn"] = _text(identity.get("mpn"))
    price = _price(row.get("price"))
    if price is not None:
        payload["price"] = {"value": price, "currency": "EUR"}
    availability = _availability(row)
    if availability:
        payload["availability"] = availability
    return payload


def validate_product_feed(payload: Mapping[str, Any], *, identity: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("id", "title", "description", "link", "image_link", "brand", "identifier_mode", "condition", "product_type"):
        if not _text(payload.get(key)):
            errors.append(f"feed_required_missing:{key}")
    if payload.get("identifier_mode") != "mpn_only":
        errors.append("feed_identifier_mode_invalid")
    if identity.get("mpn_status") == "verified" and _text(payload.get("mpn")) != _text(identity.get("mpn")):
        errors.append("feed_mpn_identity_mismatch")
    if identity.get("mpn_status") != "verified" and "mpn" in payload:
        errors.append("feed_mpn_unverified")
    price = payload.get("price")
    if price is not None and (
        not isinstance(price, Mapping) or not _text(price.get("value")) or price.get("currency") != "EUR"
    ):
        errors.append("feed_price_invalid")
    errors.extend(forbidden_identifier_keys(payload))
    return errors


def _image_urls(row: Mapping[str, Any]) -> list[str]:
    values = [_text(row.get("image"))]
    values.extend(_text(value) for value in _text(row.get("additional_image")).split(":::") if _text(value))
    urls: list[str] = []
    for value in values:
        url = value if value.startswith(("http://", "https://")) else f"https://www.etranoulis.gr/image/{value.lstrip('/')}"
        if url and url not in urls:
            urls.append(url)
    return urls


def _price(value: object) -> str | None:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return format(decimal.normalize(), "f") if decimal > 0 else None


def _availability(row: Mapping[str, Any]) -> str:
    try:
        quantity = Decimal(str(row.get("quantity", "")))
    except (InvalidOperation, ValueError):
        return ""
    if _text(row.get("status")) not in {"0", "1"}:
        return ""
    return "in_stock" if quantity > 0 and _text(row.get("status")) == "1" else "out_of_stock"


def _text(value: object) -> str:
    return normalize_whitespace(str(value or ""))
