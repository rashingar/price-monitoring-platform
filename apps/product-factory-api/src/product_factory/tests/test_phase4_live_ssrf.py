from __future__ import annotations

import socket
from typing import Any

import httpcore
import pytest

from product_factory.seo_migration import live_validation


PUBLIC_URL = "https://public.example.test/product"


@pytest.mark.parametrize(
    "target_url",
    [
        "http://localhost/product",
        "http://service.localhost/product",
        "http://service.local/product",
        "http://127.0.0.1/product",
        "http://10.0.0.8/product",
        "http://169.254.169.254/latest/meta-data",
        "http://192.0.2.1/product",
        "http://100.64.0.1/product",
        "http://0.0.0.0/product",
        "http://[::1]/product",
        "http://[fe80::1]/product",
        "http://[::]/product",
        "http://[::ffff:127.0.0.1]/product",
    ],
)
def test_live_validation_rejects_non_public_literal_before_fetch(
    target_url: str,
) -> None:
    called = False

    def fetcher(_url: str, _timeout: float) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("a blocked destination must never reach the fetcher")

    report = live_validation.validate_live_product(
        {"product_url": target_url}, fetcher=fetcher
    )

    assert called is False
    assert report["status"] == "not_run"
    assert report["access"]["error_code"] == (
        "live_url_blocked_non_public_destination"
    )
    assert report["access"]["status"] == "blocked"
    assert report["access"]["configured"] is True
    assert {check["status"] for check in report["checks"]} == {"not_run"}


def test_dns_answer_set_is_rejected_when_any_address_is_non_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            ),
        ]

    monkeypatch.setattr(live_validation.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(live_validation._BlockedLiveDestination):
        live_validation._resolve_public_addresses("public.example.test", 443)


def test_network_backend_connects_to_vetted_literal_not_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connected: list[tuple[str, int]] = []
    sentinel = object()

    monkeypatch.setattr(
        live_validation,
        "_resolve_public_addresses",
        lambda _host, _port: ("93.184.216.34",),
    )

    def fake_connect(
        _self: httpcore.SyncBackend,
        host: str,
        port: int,
        **_kwargs: Any,
    ) -> Any:
        connected.append((host, port))
        return sentinel

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect)

    result = live_validation._PublicNetworkBackend().connect_tcp(
        "public.example.test", 443
    )

    assert result is sentinel
    assert connected == [("93.184.216.34", 443)]


def test_private_dns_answer_is_blocked_before_socket_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connected = False

    monkeypatch.setattr(
        live_validation.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("10.10.10.10", 443),
            )
        ],
    )

    def forbidden_connect(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal connected
        connected = True
        raise AssertionError("socket connection must not be attempted")

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", forbidden_connect)

    with pytest.raises(live_validation._BlockedLiveDestination):
        live_validation._PublicNetworkBackend().connect_tcp(
            "rebound.example.test", 443
        )

    assert connected is False


def test_default_fetch_path_reports_private_dns_as_blocked_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live_validation.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("169.254.169.254", 80),
            )
        ],
    )

    def forbidden_connect(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("socket connection must not be attempted")

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", forbidden_connect)

    report = live_validation.validate_live_product(
        {"product_url": "http://rebound.example.test/product"}
    )

    assert report["status"] == "not_run"
    assert report["access"]["status"] == "blocked"
    assert report["access"]["error_code"] == (
        "live_url_blocked_non_public_destination"
    )
    assert report["access"]["error_type"] == "_BlockedLiveDestination"


def test_injected_fetcher_private_final_url_is_fail_closed() -> None:
    report = live_validation.validate_live_product(
        {"product_url": PUBLIC_URL},
        fetcher=lambda url, _timeout: {
            "status_code": 200,
            "requested_url": url,
            "final_url": "http://127.0.0.1/admin",
            "text": "<html></html>",
        },
    )

    assert report["status"] == "not_run"
    assert report["access"]["error_code"] == (
        "live_response_blocked_non_public_destination"
    )
    assert report["access"]["status"] == "blocked"


def test_injected_fetcher_private_redirect_hop_is_fail_closed() -> None:
    report = live_validation.validate_live_product(
        {"product_url": PUBLIC_URL},
        fetcher=lambda url, _timeout: {
            "status_code": 200,
            "requested_url": url,
            "final_url": url,
            "redirect_chain": [
                "https://public.example.test/first",
                "http://169.254.169.254/latest/meta-data",
                url,
            ],
            "text": "<html></html>",
        },
    )

    assert report["status"] == "not_run"
    assert report["access"]["error_code"] == (
        "live_response_blocked_non_public_destination"
    )
    assert report["access"]["status"] == "blocked"


def test_manual_redirect_rejects_private_target_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class PublicPeer:
        def get_extra_info(self, name: str) -> tuple[str, int] | None:
            return ("93.184.216.34", 443) if name == "server_addr" else None

    class RedirectResponse:
        status_code = 302
        headers = {"location": "http://127.0.0.1/admin"}
        url = PUBLIC_URL
        extensions = {"network_stream": PublicPeer()}
        encoding = "utf-8"

        def __enter__(self) -> RedirectResponse:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def iter_bytes(self) -> list[bytes]:
            return []

    class FakeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def stream(self, _method: str, url: str) -> RedirectResponse:
            calls.append(url)
            return RedirectResponse()

    monkeypatch.setattr(live_validation, "_PublicHTTPTransport", object)
    monkeypatch.setattr(live_validation.httpx, "Client", FakeClient)

    with pytest.raises(live_validation._BlockedLiveDestination):
        live_validation._bounded_http_get(PUBLIC_URL, 1.0)

    assert calls == [PUBLIC_URL]
