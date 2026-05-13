import json
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_capture.parsing import (  # noqa: E402
    parse_bestprice_html,
    parse_bestprice_offers,
    parse_electronet_html,
    parse_skroutz_offers,
    parse_skroutz_price_summary,
)
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


def test_bestprice_parser_reads_aggregate_offer_low_price() -> None:
    observation, flags = parse_bestprice_html(
        """
        <html><head>
        <script id="bp-data" type="application/json">
        {
          "PAGE": {
            "bestPrice": {
              "price": 9490,
              "merchant": "eTranoulis",
              "link": "/to/160584639/product.html"
            }
          }
        }
        </script>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Product",
          "name": "Bella Cucina BC-8013",
          "offers": {
            "@type": "AggregateOffer",
            "availability": "https://schema.org/InStock",
            "lowPrice": "94.90",
            "offerCount": 12,
            "priceCurrency": "EUR",
            "highPrice": "116.00"
          }
        }
        </script>
        </head></html>
        """,
        page_url="https://www.bestprice.gr/item/2159389060/product.html",
    )

    assert flags == []
    assert observation.price == Decimal("94.90")
    assert observation.currency == "EUR"
    assert observation.availability == "in_stock"
    assert observation.seller_name == "eTranoulis"
    assert observation.product_name == "Bella Cucina BC-8013"
    assert observation.raw_observation["offer_count"] == "12"
    assert observation.raw_observation["bestprice_best_store"] == "eTranoulis"
    assert observation.raw_observation["bestprice_best_store_url"] == "https://www.bestprice.gr/to/160584639/product.html"


def test_bestprice_parser_reads_price_group_offers() -> None:
    offers, flags = parse_bestprice_offers(
        """
        <html><body>
        <div class="prices" data-merchants="3">
          <div class="prices__group" data-id='2' data-price='18100' data-mid='20' data-domain='b.example'>
            <div class="prices__merchant">
              <a aria-label="Store B" class="prices__merchant-logo" href="/to/200/product-b.html"></a>
            </div>
            <div class="prices__products">
              <div class="prices__product" data-index='1' data-price='18100' data-shipping-cost='0' data-in-stock>
                <div class="prices__title">
                  <a data-price="18100" title="Product B" rel="nofollow" href="/to/200/product-b.html?from=1&amp;seq=2"><h3>Product B</h3></a>
                </div>
                <span data-status="IN_STOCK" class="av"><small>Άμεσα διαθέσιμο</small></span>
              </div>
            </div>
          </div>
          <div class="prices__group" data-id='1' data-price='18090' data-mid='10' data-domain='a.example'>
            <div class="prices__merchant">
              <a aria-label="Store A" class="prices__merchant-logo" href="/to/100/product-a.html"></a>
            </div>
            <div class="prices__products">
              <div class="prices__product" data-index='1' data-price='18090' data-shipping-cost='290' data-in-stock>
                <div class="prices__title">
                  <a data-price="18090" title="Product A" rel="nofollow" href="/to/100/product-a.html?from=1&amp;seq=1"><h3>Product A</h3></a>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """,
        page_url="https://www.bestprice.gr/item/1/product.html",
    )

    assert flags == []
    assert [(offer.seller_name, offer.price, offer.seller_url, offer.shipping_cost) for offer in offers] == [
        ("Store B", Decimal("181.00"), "https://www.bestprice.gr/to/200/product-b.html?from=1&seq=2", Decimal("0.00")),
        ("Store A", Decimal("180.90"), "https://www.bestprice.gr/to/100/product-a.html?from=1&seq=1", Decimal("2.90")),
    ]
    assert offers[0].availability == "in_stock"
    assert offers[0].raw_observation["rank"] == 2


def test_bestprice_latest_run_fixture_parses_all_store_offers(fixtures_root: Path) -> None:
    fixture = _snapshot(fixtures_root, "source_capture", "bestprice_html", "latest_run_multi_store.json")

    offers, flags = parse_bestprice_offers(fixture["html"], page_url="https://www.bestprice.gr/item/2160534094/product.html")

    assert flags == []
    assert len(offers) == 5
    assert [(offer.seller_name, offer.price, offer.shipping_cost) for offer in offers] == [
        ("Store A", Decimal("194.80"), Decimal("2.90")),
        ("Store B", Decimal("194.90"), Decimal("0.00")),
        ("Store C", Decimal("195.00"), Decimal("0.00")),
        ("Store D", Decimal("198.00"), None),
        ("Store E", Decimal("198.00"), None),
    ]
    assert [offer.raw_observation["rank"] for offer in offers] == [1, 2, 3, 4, 5]
    assert offers[0].seller_url == "https://www.bestprice.gr/to/100001/product-a.html?from=2160534094&seq=1&bpref=itemPage"
    assert offers[0].raw_observation["landed_price"] == "197.70"
    assert offers[0].raw_observation["landed_price_source"] == "computed"
    assert offers[2].raw_observation["landed_price"] == "195.00"
    assert offers[2].raw_observation["landed_price_source"] == "explicit"
    assert offers[2].raw_observation["landed_price_field"] == "data-total-price"
    assert offers[3].raw_observation["shipping_cost"] is None
    assert offers[3].raw_observation["landed_price"] is None
    assert offers[3].raw_observation["landed_price_source"] == "missing"


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
