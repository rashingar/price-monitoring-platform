import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_capture import skroutz_xhr as skroutz_xhr_module  # noqa: E402
from ecommerce.source_capture.skroutz_xhr import (  # noqa: E402
    BLOCKED_OR_CAPTCHA,
    DIRECT_ENDPOINT_UNAVAILABLE,
    FILTER_PRODUCTS_ACTION,
    INVALID_SKROUTZ_PRODUCT_URL,
    SHOPS_DETAILS_ACTION,
    SHOPS_DETAILS_UNAVAILABLE_FLAG,
    TIMEOUT,
    XHR_PARSE_FAILED,
    capture_skroutz_xhr,
)


NOW = datetime(2026, 5, 5, 12, tzinfo=timezone.utc)


def _snapshot(fixtures_root: Path, *parts: str) -> dict:
    return json.loads((fixtures_root / "golden_snapshots" / Path(*parts)).read_text(encoding="utf-8"))


def _endpoint_response(url: str, payload, *, action: str, status: int = 200, content_type: str = "application/json"):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return skroutz_xhr_module._EndpointResponse(
        url=url,
        method="GET",
        status=status,
        content_type=content_type,
        body_text=body,
        body_json=json.loads(body) if content_type == "application/json" and body else None,
        fetched_at=NOW,
        latency_ms=1,
        trigger_action=action,
        final_url=url,
    )


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _normalized_result(result, calls: list[tuple[str, str]] | None = None) -> dict:
    return {
        "status": result.status,
        "error_code": result.error_code,
        "snapshot": {
            "capture_strategy": result.snapshot.capture_strategy,
            "request_url": result.snapshot.request_url,
            "request_method": result.snapshot.request_method,
            "response_status": result.snapshot.response_status,
            "response_content_type": result.snapshot.response_content_type,
            "trigger_action": result.snapshot.trigger_action,
            "parser_version": result.snapshot.parser_version,
            "data_quality_flags": result.snapshot.data_quality_flags,
            "error_code": result.snapshot.error_code,
        },
        "price_observations": [
            {
                "price": _decimal(observation.price),
                "availability": observation.availability,
                "source": observation.raw_observation.get("source"),
            }
            for observation in result.price_observations
        ],
        "offer_observations": [
            {
                "seller_name": observation.seller_name,
                "seller_url": observation.seller_url,
                "price": _decimal(observation.price),
                "original_price": _decimal(observation.original_price),
                "shipping_cost": _decimal(observation.shipping_cost),
            }
            for observation in result.offer_observations
        ],
        "calls": [{"url": url, "action": action} for url, action in (calls or [])],
    }


def test_skroutz_direct_capture_success_snapshots(monkeypatch, fixtures_root: Path) -> None:
    filter_payload = {
        "product_cards": [
            {
                "shop_id": 10,
                "pricing": {"final_price": "199,99", "original_price": "219,99"},
                "availability_label": "available",
                "shipping": {"shipping_cost": "3.00", "delivery_text": "1-3 days"},
            }
        ]
    }
    shops_payload = {"shops": [{"id": 10, "name": "Store A", "url": "/m/10/store-a"}]}
    calls: list[tuple[str, str]] = []

    def fake_fetch(url: str, *, timeout_seconds: float, action: str):
        del timeout_seconds
        calls.append((url, action))
        if action == FILTER_PRODUCTS_ACTION:
            return _endpoint_response(url, filter_payload, action=action)
        return _endpoint_response(url, shops_payload, action=action)

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", fake_fetch)

    result = capture_skroutz_xhr("https://www.skroutz.gr/s/60985330/product.html", timeout_seconds=5)

    assert _normalized_result(result, calls) == _snapshot(fixtures_root, "source_capture", "skroutz_direct_json", "capture_success.expected.json")


def test_skroutz_direct_capture_price_summary_snapshot(monkeypatch, fixtures_root: Path) -> None:
    def fake_fetch(url: str, *, timeout_seconds: float, action: str):
        del timeout_seconds
        assert action == FILTER_PRODUCTS_ACTION
        return _endpoint_response(url, {"price_min": "187,50", "availability": "available"}, action=action)

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", fake_fetch)

    result = capture_skroutz_xhr("https://www.skroutz.gr/s/8/product.html", timeout_seconds=5)

    assert _normalized_result(result) == _snapshot(fixtures_root, "source_capture", "skroutz_direct_json", "capture_price_summary.expected.json")


def test_skroutz_direct_capture_failure_snapshots(monkeypatch, fixtures_root: Path) -> None:
    cases = {}

    def parse_failed_fetch(url: str, *, timeout_seconds: float, action: str):
        del timeout_seconds
        return _endpoint_response(url, {"price": 199.99, "availability": "available", "shipping_cost": 3}, action=action)

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", parse_failed_fetch)
    cases["parse_failed"] = _normalized_result(capture_skroutz_xhr("https://www.skroutz.gr/s/4/product.html", timeout_seconds=5))

    def blocked_fetch(url: str, *, timeout_seconds: float, action: str):
        del timeout_seconds
        return _endpoint_response(
            url,
            "<html><title>Just a moment...</title><p>Cloudflare captcha challenge</p></html>",
            action=action,
            status=403,
            content_type="text/html",
        )

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", blocked_fetch)
    cases["blocked"] = _normalized_result(capture_skroutz_xhr("https://www.skroutz.gr/s/5/product.html", timeout_seconds=5))

    def timeout_fetch(url: str, *, timeout_seconds: float, action: str):
        del url, timeout_seconds, action
        raise TimeoutError("timed out")

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", timeout_fetch)
    cases["timeout"] = _normalized_result(capture_skroutz_xhr("https://www.skroutz.gr/s/6/product.html", timeout_seconds=5))

    def unavailable_fetch(url: str, *, timeout_seconds: float, action: str):
        del url, timeout_seconds, action
        raise skroutz_xhr_module._EndpointUnavailable("connection refused")

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", unavailable_fetch)
    cases["direct_endpoint_unavailable"] = _normalized_result(capture_skroutz_xhr("https://www.skroutz.gr/s/9/product.html", timeout_seconds=5))

    assert cases["parse_failed"]["error_code"] == XHR_PARSE_FAILED
    assert cases["blocked"]["error_code"] == BLOCKED_OR_CAPTCHA
    assert cases["timeout"]["error_code"] == TIMEOUT
    assert cases["direct_endpoint_unavailable"]["error_code"] == DIRECT_ENDPOINT_UNAVAILABLE
    assert cases == _snapshot(fixtures_root, "source_capture", "skroutz_direct_json", "capture_failures.expected.json")


def test_skroutz_direct_capture_edge_case_snapshots(monkeypatch, fixtures_root: Path) -> None:
    cases = {}

    def shops_unavailable_fetch(url: str, *, timeout_seconds: float, action: str):
        del timeout_seconds
        if action == SHOPS_DETAILS_ACTION:
            raise skroutz_xhr_module._EndpointUnavailable("shops unavailable")
        return _endpoint_response(url, {"product_cards": [{"shop_id": 11, "shop_name": "Card Store", "price": "201.00"}]}, action=action)

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", shops_unavailable_fetch)
    cases["shops_details_unavailable"] = _normalized_result(capture_skroutz_xhr("https://www.skroutz.gr/s/11/product.html", timeout_seconds=5))

    def empty_fetch(url: str, *, timeout_seconds: float, action: str):
        del timeout_seconds
        return _endpoint_response(url, {}, action=action)

    monkeypatch.setattr(skroutz_xhr_module, "_fetch_endpoint", empty_fetch)
    cases["empty_payload"] = _normalized_result(capture_skroutz_xhr("https://www.skroutz.gr/s/10/product.html", timeout_seconds=5))
    cases["invalid_product_url"] = _normalized_result(capture_skroutz_xhr("https://www.skroutz.gr/search?keyphrase=tv", timeout_seconds=5))

    assert SHOPS_DETAILS_UNAVAILABLE_FLAG in cases["shops_details_unavailable"]["snapshot"]["data_quality_flags"]
    assert cases["invalid_product_url"]["error_code"] == INVALID_SKROUTZ_PRODUCT_URL
    assert cases == _snapshot(fixtures_root, "source_capture", "skroutz_direct_json", "capture_edge_cases.expected.json")
