import sys
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.source_capture.egress_policy import (  # noqa: E402
    EgressPolicyError,
    safe_get,
    validate_outbound_url,
)


def test_policy_accepts_supported_vendor_urls() -> None:
    skroutz = validate_outbound_url(
        "https://www.skroutz.gr/s/123/product.html", require_known_vendor=True
    )
    bestprice = validate_outbound_url(
        "https://www.bestprice.gr/item/1/product.html", require_known_vendor=True
    )
    electronet = validate_outbound_url(
        "https://www.electronet.gr/product/1", require_known_vendor=True
    )

    assert skroutz.vendor_slug == "skroutz"
    assert bestprice.vendor_slug == "bestprice"
    assert electronet.vendor_slug == "electronet"


def test_policy_rejects_unsupported_scheme() -> None:
    with pytest.raises(EgressPolicyError) as exc_info:
        validate_outbound_url("file:///C:/Windows/win.ini")

    assert exc_info.value.code == "unsupported_scheme"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/product",
        "http://127.0.0.1/product",
        "http://10.0.0.5/product",
        "http://192.168.1.10/product",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_policy_rejects_localhost_and_private_hosts(url: str) -> None:
    with pytest.raises(EgressPolicyError) as exc_info:
        validate_outbound_url(url)

    assert exc_info.value.code == "blocked_private_host"


@pytest.mark.parametrize("url", ["", "not-a-url", "https://"])
def test_policy_rejects_malformed_urls(url: str) -> None:
    with pytest.raises(EgressPolicyError) as exc_info:
        validate_outbound_url(url)

    assert exc_info.value.code == "invalid_url"


def test_policy_can_require_known_vendor() -> None:
    with pytest.raises(EgressPolicyError) as exc_info:
        validate_outbound_url(
            "https://shop.example.test/product/1", require_known_vendor=True
        )

    assert exc_info.value.code == "unknown_vendor"


def test_safe_get_blocks_redirect_to_private_host_without_fetching_target() -> None:
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    with pytest.raises(EgressPolicyError) as exc_info:
        safe_get(
            "https://www.bestprice.gr/item/1/product.html",
            require_known_vendor=True,
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.code == "redirect_blocked"
    assert requested_hosts == ["www.bestprice.gr"]


def test_safe_get_blocks_redirect_to_different_vendor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.bestprice.gr":
            return httpx.Response(
                302, headers={"location": "https://www.skroutz.gr/s/1/product.html"}
            )
        return httpx.Response(200, text="should not fetch")

    with pytest.raises(EgressPolicyError) as exc_info:
        safe_get(
            "https://www.bestprice.gr/item/1/product.html",
            require_known_vendor=True,
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.code == "redirect_blocked"


def test_safe_get_rejects_large_response_by_content_length() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": "20"}, content=b"x" * 20)

    with pytest.raises(EgressPolicyError) as exc_info:
        safe_get(
            "https://www.electronet.gr/product/1",
            require_known_vendor=True,
            max_response_bytes=5,
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.code == "response_too_large"


def test_safe_get_rejects_large_streamed_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 20)

    with pytest.raises(EgressPolicyError) as exc_info:
        safe_get(
            "https://www.electronet.gr/product/1",
            require_known_vendor=True,
            max_response_bytes=5,
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.code == "response_too_large"


def test_safe_get_can_raise_normalized_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    with pytest.raises(EgressPolicyError) as exc_info:
        safe_get(
            "https://www.electronet.gr/product/missing",
            require_known_vendor=True,
            raise_for_status=True,
            transport=httpx.MockTransport(handler),
        )

    assert exc_info.value.code == "http_error"
    assert "HTTP 404" in exc_info.value.message
