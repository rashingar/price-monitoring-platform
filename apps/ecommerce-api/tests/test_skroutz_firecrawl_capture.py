import inspect
import json
import sys
from decimal import Decimal
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_capture import runner  # noqa: E402
from ecommerce.source_capture.parsing import parse_skroutz_firecrawl_content  # noqa: E402
from ecommerce.source_capture.skroutz_firecrawl import (  # noqa: E402
    CAPTURE_STRATEGY,
    FIRECRAWL_API_FAILED,
    FIRECRAWL_API_KEY_MISSING,
    FIRECRAWL_PARSE_FAILED,
    PARSER_VERSION,
    capture_skroutz_firecrawl,
)
from ecommerce.source_capture.types import CaptureResult, CaptureSnapshotPayload  # noqa: E402


SKROUTZ_URL = "https://www.skroutz.gr/s/60985330/product.html"
FIRECRAWL_URL = "https://firecrawl.test/v2/scrape"


def _transport(handler):
    return httpx.MockTransport(handler)


def _firecrawl_response(payload: dict, *, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, headers={"content-type": "application/json"})


def test_missing_firecrawl_api_key_returns_failed_capture(monkeypatch) -> None:
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("FIRECRAWL_API_BASE_URL", "https://firecrawl.test/v2")

    result = capture_skroutz_firecrawl(SKROUTZ_URL, timeout_seconds=5, transport=_transport(lambda request: httpx.Response(500)))

    assert result.status == "failed"
    assert result.error_code == FIRECRAWL_API_KEY_MISSING
    assert result.snapshot.capture_strategy == CAPTURE_STRATEGY
    assert result.snapshot.parser_version == PARSER_VERSION
    assert result.snapshot.request_url == FIRECRAWL_URL


def test_skroutz_dispatch_calls_firecrawl_path(monkeypatch) -> None:
    calls: list[str] = []

    def fake_firecrawl(url: str, *, timeout_seconds: float) -> CaptureResult:
        calls.append(f"{url}|{timeout_seconds}")
        return CaptureResult(vendor_slug="skroutz", status="success", snapshot=CaptureSnapshotPayload(capture_strategy=CAPTURE_STRATEGY, page_url=url))

    monkeypatch.setattr(runner, "capture_skroutz_firecrawl", fake_firecrawl)

    result = runner.capture_source_url(SKROUTZ_URL, timeout_seconds=7)

    assert result.status == "success"
    assert calls == [f"{SKROUTZ_URL}|7"]


def test_direct_json_capture_is_not_reachable_from_dispatch() -> None:
    assert not hasattr(runner, "capture_skroutz_xhr")
    assert "skroutz_xhr" not in inspect.getsource(runner.capture_source_url)
    assert "filter_products.json" not in inspect.getsource(runner.capture_source_url)


def test_bestprice_dispatch_is_not_replaced_by_firecrawl(monkeypatch) -> None:
    def fail_firecrawl(url: str, *, timeout_seconds: float) -> CaptureResult:
        raise AssertionError(f"BestPrice should not use Firecrawl: {url} {timeout_seconds}")

    def fake_bestprice(url: str, *, timeout_seconds: float) -> CaptureResult:
        return CaptureResult(vendor_slug="bestprice", status="success", snapshot=CaptureSnapshotPayload(capture_strategy="bestprice_httpx_html", page_url=url))

    monkeypatch.setattr(runner, "capture_skroutz_firecrawl", fail_firecrawl)
    monkeypatch.setattr(runner, "_capture_bestprice", fake_bestprice)

    result = runner.capture_source_url("https://www.bestprice.gr/item/2160534094/product.html", timeout_seconds=5)

    assert result.vendor_slug == "bestprice"
    assert result.snapshot.capture_strategy == "bestprice_httpx_html"


def test_firecrawl_success_response_produces_offer_observations(monkeypatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-secret")
    monkeypatch.setenv("FIRECRAWL_API_BASE_URL", "https://firecrawl.test/v2")
    requests: list[httpx.Request] = []
    markdown = """
    | Store | Price | Shipping | Total |
    | --- | ---: | ---: | ---: |
    | [Store A](/m/10/store-a) | 199,99 € | 3,00 € | 202,99 € |
    | Store B | 201.50 € | 0,00 € | 201.50 € |
    """

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _firecrawl_response(
            {
                "success": True,
                "data": {
                    "markdown": markdown,
                    "metadata": {"sourceURL": SKROUTZ_URL},
                },
            }
        )

    result = capture_skroutz_firecrawl(SKROUTZ_URL, timeout_seconds=5, transport=_transport(handler))

    assert result.status == "success"
    assert result.snapshot.capture_strategy == CAPTURE_STRATEGY
    assert result.snapshot.parser_version == PARSER_VERSION
    assert result.snapshot.request_url == FIRECRAWL_URL
    assert requests[0].headers["authorization"] == "Bearer fc-test-secret"
    assert json.loads(requests[0].content)["url"] == SKROUTZ_URL
    assert [(offer.seller_name, offer.price, offer.shipping_cost) for offer in result.offer_observations] == [
        ("Store A", Decimal("199.99"), Decimal("3.00")),
        ("Store B", Decimal("201.50"), Decimal("0.00")),
    ]
    assert result.offer_observations[0].seller_url == "https://www.skroutz.gr/m/10/store-a"
    assert result.offer_observations[0].raw_observation["landed_price"] == "202.99"


def test_firecrawl_failure_response_persists_snapshot_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-secret")
    monkeypatch.setenv("FIRECRAWL_API_BASE_URL", "https://firecrawl.test/v2")

    result = capture_skroutz_firecrawl(
        SKROUTZ_URL,
        timeout_seconds=5,
        transport=_transport(lambda request: _firecrawl_response({"success": False, "error": "blocked"}, status=500)),
    )

    assert result.status == "failed"
    assert result.error_code == FIRECRAWL_API_FAILED
    assert result.snapshot.response_status == 500
    assert result.snapshot.response_content_type == "application/json"
    assert result.snapshot.error_code == FIRECRAWL_API_FAILED
    assert result.snapshot.response_body_json["error"] == "blocked"
    assert FIRECRAWL_API_FAILED in result.snapshot.data_quality_flags


def test_firecrawl_parse_failure_returns_diagnostic_result(monkeypatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-secret")
    monkeypatch.setenv("FIRECRAWL_API_BASE_URL", "https://firecrawl.test/v2")

    result = capture_skroutz_firecrawl(
        SKROUTZ_URL,
        timeout_seconds=5,
        transport=_transport(lambda request: _firecrawl_response({"success": True, "data": {"markdown": "no prices here"}})),
    )

    assert result.status == "failed"
    assert result.error_code == FIRECRAWL_PARSE_FAILED
    assert result.snapshot.error_code == FIRECRAWL_PARSE_FAILED
    assert FIRECRAWL_PARSE_FAILED in result.snapshot.data_quality_flags


def test_firecrawl_snapshot_sanitizes_secrets_and_bounds_content(monkeypatch) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-secret")
    monkeypatch.setenv("FIRECRAWL_API_BASE_URL", "https://firecrawl.test/v2")
    huge_markdown = "| Store | Price |\n| --- | ---: |\n| Store A | 199,99 € |\n" + ("x" * 10_000)

    result = capture_skroutz_firecrawl(
        SKROUTZ_URL,
        timeout_seconds=5,
        transport=_transport(
            lambda request: _firecrawl_response(
                {
                    "success": True,
                    "data": {
                        "markdown": huge_markdown,
                        "metadata": {
                            "sourceURL": SKROUTZ_URL,
                            "Authorization": "Bearer leaked",
                            "api_token": "secret-token",
                        },
                    },
                }
            )
        ),
    )

    persisted = json.dumps(result.snapshot.response_body_json, sort_keys=True)
    assert "fc-test-secret" not in persisted
    assert "Bearer leaked" not in persisted
    assert "secret-token" not in persisted
    assert "authorization" not in persisted.casefold()
    assert len(result.snapshot.response_body_json["data"]["markdown"]["sample"]) <= 500
    assert result.snapshot.response_body_json["data"]["markdown"]["length"] == len(huge_markdown)


def test_skroutz_firecrawl_parser_extracts_offers_from_markdown_table() -> None:
    offers, price_observation, flags = parse_skroutz_firecrawl_content(
        """
        | Seller | Item price | Shipping |
        | --- | ---: | ---: |
        | Store A | 88,80 € | 2,50 € |
        """,
        page_url=SKROUTZ_URL,
    )

    assert flags == []
    assert price_observation is None
    assert len(offers) == 1
    assert offers[0].seller_name == "Store A"
    assert offers[0].price == Decimal("88.80")
    assert offers[0].shipping_cost == Decimal("2.50")
