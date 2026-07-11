from __future__ import annotations

"""Candidate schema.org Product data for the MPN-only catalog contract."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .normalize import normalize_whitespace


FORBIDDEN_IDENTIFIER_KEYS = frozenset(
    {"gtin", "gtin8", "gtin12", "gtin13", "gtin14", "ean", "ean13", "upc", "barcode"}
)


def build_product_structured_data(
    *, row: Mapping[str, Any], identity: Mapping[str, Any]
) -> dict[str, object]:
    """Build a stable, storefront-neutral Product candidate artifact."""
    payload: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": _text(row.get("name")),
        "description": _plain_text(row.get("description")),
        "sku": _text(row.get("model")),
        "brand": {"@type": "Brand", "name": _text(identity.get("brand") or row.get("manufacturer"))},
        "image": _image_urls(row),
        "category": _text(row.get("category")),
        "url": _text(row.get("product_url")),
    }
    if identity.get("mpn_status") == "verified" and _text(identity.get("mpn")):
        payload["mpn"] = _text(identity.get("mpn"))
    offer = _offer(row)
    if offer:
        payload["offers"] = offer
    return payload


def validate_product_structured_data(
    payload: Mapping[str, Any], *, identity: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    if payload.get("@context") != "https://schema.org":
        errors.append("structured_context_invalid")
    if payload.get("@type") != "Product":
        errors.append("structured_type_invalid")
    for key in ("name", "description", "sku", "brand", "image", "category", "url"):
        if not payload.get(key):
            errors.append(f"structured_required_missing:{key}")
    brand = payload.get("brand")
    if not isinstance(brand, Mapping) or brand.get("@type") != "Brand" or not _text(brand.get("name")):
        errors.append("structured_brand_invalid")
    if not isinstance(payload.get("image"), list) or not all(_is_absolute_url(value) for value in payload.get("image", [])):
        errors.append("structured_images_invalid")
    status = identity.get("mpn_status")
    if status == "verified" and _text(payload.get("mpn")) != _text(identity.get("mpn")):
        errors.append("structured_mpn_identity_mismatch")
    if status != "verified" and "mpn" in payload:
        errors.append("structured_mpn_unverified")
    errors.extend(_forbidden_key_errors(payload))
    return errors


def forbidden_identifier_keys(payload: object) -> list[str]:
    """Return recursive paths for fields outside the current catalog contract."""
    return _forbidden_key_errors(payload)


def _offer(row: Mapping[str, Any]) -> dict[str, str] | None:
    price = _price(row.get("price"))
    in_stock = _trusted_availability(row)
    url = _text(row.get("product_url"))
    if price is None or in_stock is None or not url:
        return None
    return {
        "@type": "Offer",
        "priceCurrency": "EUR",
        "price": price,
        "availability": "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock",
        "url": url,
    }


def _image_urls(row: Mapping[str, Any]) -> list[str]:
    values = [_text(row.get("image"))]
    values.extend(_text(value) for value in _text(row.get("additional_image")).split(":::") if _text(value))
    result: list[str] = []
    for value in values:
        if not value:
            continue
        url = value if _is_absolute_url(value) else f"https://www.etranoulis.gr/image/{value.lstrip('/')}"
        if url not in result:
            result.append(url)
    return result


def _trusted_availability(row: Mapping[str, Any]) -> bool | None:
    try:
        quantity = Decimal(str(row.get("quantity", "")))
    except (InvalidOperation, ValueError):
        return None
    status = _text(row.get("status"))
    if status not in {"0", "1"}:
        return None
    return quantity > 0 and status == "1"


def _price(value: object) -> str | None:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if price <= 0:
        return None
    return format(price.normalize(), "f")


def _plain_text(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return normalize_whitespace(text)


def _forbidden_key_errors(value: object, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{path}.{key}"
            if str(key).casefold() in FORBIDDEN_IDENTIFIER_KEYS:
                errors.append(f"forbidden_identifier_key:{child}")
            errors.extend(_forbidden_key_errors(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            errors.extend(_forbidden_key_errors(nested, f"{path}[{index}]"))
    return errors


def _is_absolute_url(value: object) -> bool:
    return bool(re.match(r"^https?://[^\s]+$", _text(value)))


def _text(value: object) -> str:
    return normalize_whitespace(str(value or ""))
