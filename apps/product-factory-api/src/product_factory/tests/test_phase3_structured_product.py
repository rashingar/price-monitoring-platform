from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_factory.structured_product import (
    FORBIDDEN_IDENTIFIER_KEYS,
    build_product_structured_data,
    forbidden_identifier_keys,
    validate_product_structured_data,
)


ROW = {
    "model": "747100", "name": "Midea Solunar EF-12RD1H/MX1-12RD1H", "description": "<p>Verified product description.</p>",
    "manufacturer": "Midea", "category": "Air Conditioners", "image": "catalog/01_main/747100/main.jpg", "additional_image": "catalog/01_main/747100/second.jpg", "product_url": "https://www.etranoulis.gr/midea-solunar", "price": "0", "quantity": "0", "status": "0",
}
IDENTITY = {"internal_model": "747100", "brand": "Midea", "mpn": "EF-12RD1H/MX1-12RD1H", "mpn_status": "verified"}


def test_structured_product_contains_sku_brand_verified_mpn_and_public_images() -> None:
    payload = build_product_structured_data(row=ROW, identity=IDENTITY)

    assert payload["sku"] == "747100"
    assert payload["mpn"] == IDENTITY["mpn"]
    assert payload["brand"] == {"@type": "Brand", "name": "Midea"}
    assert all(str(url).startswith("https://") for url in payload["image"])
    assert validate_product_structured_data(payload, identity=IDENTITY) == []
    assert forbidden_identifier_keys(payload) == []


def test_structured_product_omits_unverified_mpn_and_never_emits_forbidden_keys() -> None:
    payload = build_product_structured_data(row=ROW, identity={**IDENTITY, "mpn_status": "inferred"})

    assert "mpn" not in payload
    assert not (set(payload) & FORBIDDEN_IDENTIFIER_KEYS)
    assert forbidden_identifier_keys(payload) == []


def test_product_structured_data_schema_validates() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    payload = build_product_structured_data(row=ROW, identity=IDENTITY)
    schema_path = Path(__file__).parents[3] / "docs" / "contracts" / "product_structured_data.schema.json"

    jsonschema.Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(payload)
