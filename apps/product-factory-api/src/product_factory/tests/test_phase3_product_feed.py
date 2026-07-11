from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_factory.product_feed import build_product_feed, validate_product_feed
from product_factory.structured_product import FORBIDDEN_IDENTIFIER_KEYS, forbidden_identifier_keys


ROW = {
    "model": "747100", "name": "Midea Solunar EF-12RD1H/MX1-12RD1H", "meta_description": "Verified product description.",
    "manufacturer": "Midea", "category": "Air Conditioners", "image": "catalog/01_main/747100/main.jpg", "additional_image": "", "product_url": "https://www.etranoulis.gr/midea-solunar", "price": "1000", "quantity": "2", "status": "1",
}
IDENTITY = {"internal_model": "747100", "brand": "Midea", "mpn": "EF-12RD1H/MX1-12RD1H", "mpn_status": "verified", "source": "manufacturer"}


def test_feed_is_mpn_only_and_matches_verified_identity() -> None:
    payload = build_product_feed(row=ROW, identity=IDENTITY)

    assert payload["identifier_mode"] == "mpn_only"
    assert payload["mpn"] == IDENTITY["mpn"]
    assert payload["price"] == {"value": "1000", "currency": "EUR"}
    assert validate_product_feed(payload, identity=IDENTITY) == []
    assert not (set(payload) & FORBIDDEN_IDENTIFIER_KEYS)
    assert forbidden_identifier_keys(payload) == []


def test_feed_omits_unverified_mpn_and_schema_validates() -> None:
    payload = build_product_feed(row=ROW, identity={**IDENTITY, "mpn_status": "missing"})
    assert "mpn" not in payload
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parents[3] / "docs" / "contracts" / "product_feed.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(payload)
