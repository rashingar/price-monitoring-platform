import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce import source_urls  # noqa: E402
from ecommerce.source_capture import runner  # noqa: E402
from ecommerce.source_capture.egress_policy import (
    EgressPolicyError,
    SafeFetchResponse,
)  # noqa: E402


def _safe_response(
    url: str, *, status_code: int = 200, text: str = "<html></html>"
) -> SafeFetchResponse:
    return SafeFetchResponse(
        url=url,
        final_url=url,
        status_code=status_code,
        headers={"content-type": "text/html; charset=utf-8"},
        text=text,
        content=text.encode("utf-8"),
        vendor_slug=None,
    )


def test_source_url_reachability_uses_safe_fetch(monkeypatch) -> None:
    calls: list[str] = []

    def fake_safe_get(url: str, **_kwargs) -> SafeFetchResponse:
        calls.append(url)
        return _safe_response(url, status_code=200)

    monkeypatch.setattr(source_urls, "safe_get", fake_safe_get)

    result = source_urls.validate_source_url_reachability(
        "https://www.skroutz.gr/s/1/product.html"
    )

    assert result.status == "success"
    assert result.http_status_code == 200
    assert calls == ["https://www.skroutz.gr/s/1/product.html"]


def test_source_url_reachability_reports_blocked_private_host(monkeypatch) -> None:
    def fake_safe_get(_url: str, **_kwargs) -> SafeFetchResponse:
        raise EgressPolicyError("blocked_private_host", "blocked")

    monkeypatch.setattr(source_urls, "safe_get", fake_safe_get)

    result = source_urls.validate_source_url_reachability(
        "https://www.skroutz.gr/s/1/product.html"
    )

    assert result.status == "inconclusive"
    assert result.message == "URL host is not eligible for reachability validation."


def test_electronet_capture_uses_safe_fetch(monkeypatch) -> None:
    calls: list[tuple[str, str | None, bool]] = []
    html = '<html><meta property="product:price:amount" content="499.90"></html>'

    def fake_safe_get(url: str, **kwargs) -> SafeFetchResponse:
        calls.append(
            (
                url,
                kwargs.get("expected_vendor_slug"),
                bool(kwargs.get("require_known_vendor")),
            )
        )
        return _safe_response(url, text=html)

    monkeypatch.setattr(runner, "safe_get", fake_safe_get)

    result = runner.capture_source_url("https://www.electronet.gr/product/1")

    assert result.status == "success"
    assert result.vendor_slug == "electronet"
    assert result.snapshot.capture_strategy == "electronet_httpx_html"
    assert calls == [("https://www.electronet.gr/product/1", "electronet", True)]


def test_bestprice_capture_reports_egress_policy_error(monkeypatch) -> None:
    def fake_safe_get(_url: str, **_kwargs) -> SafeFetchResponse:
        raise EgressPolicyError(
            "redirect_blocked", "Redirect target changed to a different vendor domain."
        )

    monkeypatch.setattr(runner, "safe_get", fake_safe_get)

    result = runner.capture_source_url("https://www.bestprice.gr/item/1/product.html")

    assert result.status == "failed"
    assert result.error_code == "redirect_blocked"
    assert result.snapshot.error_code == "redirect_blocked"
    assert "different vendor" in str(result.error_message)
