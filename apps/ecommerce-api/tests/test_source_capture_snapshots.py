import json
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_capture.parsing import parse_electronet_html, parse_skroutz_offers, parse_skroutz_price_summary  # noqa: E402
from ecommerce.source_capture.sanitize import sanitize_headers, sanitize_json  # noqa: E402
from ecommerce.source_capture.scoring import score_response_candidate  # noqa: E402
from ecommerce.source_capture.types import ParsedOfferObservation, ParsedPriceObservation, ResponseCandidate  # noqa: E402


def _snapshot(fixtures_root: Path, *parts: str) -> dict:
    return json.loads((fixtures_root / "golden_snapshots" / Path(*parts)).read_text(encoding="utf-8"))


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _price_observation(observation: ParsedPriceObservation, flags: list[str]) -> dict:
    return {
        "price": _decimal(observation.price),
        "availability": observation.availability,
        "stock_status": observation.stock_status,
        "product_name": observation.product_name,
        "flags": flags,
        "raw_observation": observation.raw_observation,
    }


def _offer_observations(offers: list[ParsedOfferObservation], flags: list[str]) -> dict:
    return {
        "flags": flags,
        "offers": [
            {
                "seller_name": offer.seller_name,
                "seller_url": offer.seller_url,
                "price": _decimal(offer.price),
                "original_price": _decimal(offer.original_price),
                "shipping_cost": _decimal(offer.shipping_cost),
                "availability": offer.availability,
                "delivery_text": offer.delivery_text,
            }
            for offer in offers
        ],
    }


def test_electronet_parser_snapshots(fixtures_root: Path) -> None:
    json_ld, json_ld_flags = parse_electronet_html(
        """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"LG OLED","offers":{"price":"849.90","availability":"https://schema.org/InStock"}}
        </script>
        </head></html>
        """,
        page_url="https://www.electronet.gr/p/structured",
    )
    meta_price, meta_flags = parse_electronet_html(
        '<html><title>TV</title><meta property="product:price:amount" content="499.90">'
        "<span>Availability</span><b>In stock</b></html>",
        page_url="https://www.electronet.gr/p/1",
    )
    missing, missing_flags = parse_electronet_html(
        "<html><title>TV</title></html>",
        page_url="https://www.electronet.gr/p/1",
    )

    actual = {
        "json_ld_product_offer": _price_observation(json_ld, json_ld_flags),
        "meta_price": _price_observation(meta_price, meta_flags),
        "missing_price": _price_observation(missing, missing_flags),
    }

    assert actual == _snapshot(fixtures_root, "source_capture", "electronet_parser", "parser.expected.json")


def test_skroutz_parser_snapshots(fixtures_root: Path) -> None:
    product_cards, product_card_flags = parse_skroutz_offers(
        {
            "product_cards": [
                {
                    "shop_id": 10,
                    "pricing": {"final_price": "199,99", "original_price": "219,99"},
                    "availability_label": "available",
                    "shipping": {"shipping_cost": "3.00", "delivery_text": "1-3 days"},
                }
            ]
        },
        shops_payload={"shops": [{"id": 10, "name": "Store A", "url": "/m/10/store-a"}]},
    )
    nested, nested_flags = parse_skroutz_offers(
        {
            "cards": [
                {
                    "shop": {"name": "Nested Store", "url": "https://seller.example.test"},
                    "pricing": {"final_price": "321.50"},
                    "delivery": {"shipping_cost": "4.90", "text": "1-3 days"},
                    "availability_text": "in stock",
                }
            ]
        }
    )
    summary, summary_flags = parse_skroutz_price_summary(
        {"price_min": "187,50", "availability": "available"},
        page_url="https://www.skroutz.gr/s/8/product.html",
    )

    actual = {
        "product_cards_with_shops_details": _offer_observations(product_cards, product_card_flags),
        "nested_shop_pricing": _offer_observations(nested, nested_flags),
        "price_min_summary": _price_observation(summary, summary_flags) if summary else None,
    }

    assert actual == _snapshot(fixtures_root, "source_capture", "skroutz_direct_json", "parser.expected.json")


def test_source_capture_scoring_snapshot(fixtures_root: Path) -> None:
    candidates = {
        "analytics": ResponseCandidate(url="https://analytics.example/collect", body_text="ok", content_type="text/plain"),
        "offers": ResponseCandidate(
            url="https://www.skroutz.gr/products/1/offers",
            content_type="application/json",
            body_text='{"shop_name":"Store A","price":199.99,"availability":"available","shipping_cost":3}',
            occurred_after_trigger=True,
        ),
        "widget": ResponseCandidate(
            url="https://ekr.zdassets.com/compose/support-widget",
            content_type="application/json",
            body_text='{"products":[{"name":"web_widget"}]}',
        ),
        "promotion": ResponseCandidate(
            url="https://www.skroutz.gr/s/1/placements?type=featured_cross_sell",
            body_text="<html><title>Just a moment...</title></html>",
            status=403,
            occurred_after_trigger=True,
        ),
        "filter_products": ResponseCandidate(
            url="https://www.skroutz.gr/s/1/filter_products.json",
            content_type="application/json",
            body_text='{"price_min":"199.99"}',
        ),
    }

    actual = {
        key: {
            "score": scored.score,
            "reasons": list(scored.reasons),
        }
        for key, scored in ((key, score_response_candidate(candidate)) for key, candidate in candidates.items())
    }

    assert actual == _snapshot(fixtures_root, "source_capture", "scoring", "scoring.expected.json")


def test_source_capture_sanitize_snapshot(fixtures_root: Path) -> None:
    actual = {
        "headers": sanitize_headers(
            {
                "Cookie": "secret",
                "Authorization": "Bearer x",
                "Content-Type": "application/json",
                "X-Trace": "trace-1",
            }
        ),
        "json": sanitize_json(
            {
                "token": "secret",
                "payload": {
                    "csrf": "secret",
                    "price": 10,
                    "nested": [{"session_id": "secret"}, {"availability": "available"}],
                },
            }
        ),
    }

    assert actual == _snapshot(fixtures_root, "source_capture", "sanitize", "sanitize.expected.json")
