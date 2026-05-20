from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from product_factory.models import (
    CLIInput,
    FetchResult,
    ParsedProduct,
    SourceProductData,
)
from product_factory.prepare_provider_resolution import (
    PrepareProviderResolutionResult,
    validate_prepare_provider_resolution_result,
)
from product_factory.prepare_stage import execute_prepare_stage
from product_factory.providers.models import ProviderInputIdentity
from product_factory.providers.skroutz_fetcher import (
    SkroutzFetchResult,
    SkroutzFetchStatus,
    SkroutzSnapshotFetcher,
)
from product_factory.providers.skroutz_provider import (
    SKROUTZ_CHALLENGE_REASON,
    SkroutzProvider,
)
from product_factory.services.models import RunStatus
from product_factory.services.prepare_execution import execute_prepare_workflow
from product_factory.source_capture_client import SourceCaptureSyncResult

PRODUCT_URL = "https://www.skroutz.gr/s/61054853/lg-icheio-dxl7t-mayro.html"
CHALLENGE_HTML = """
<!doctype html>
<html>
  <head><title>Just a moment...</title></head>
  <body>
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
    Checking your browser before accessing Skroutz.
  </body>
</html>
"""


class DummyAssetFetcher:
    def download_gallery_images(self, **_kwargs):
        return [], [], []

    def download_besco_images(self, **_kwargs):
        return [], [], []


def _blocked_parsed(url: str = PRODUCT_URL) -> ParsedProduct:
    return ParsedProduct(
        source=SourceProductData(
            source_name="skroutz",
            page_type=SKROUTZ_CHALLENGE_REASON,
            url=url,
            canonical_url=url,
            taxonomy_escalation_reason=SKROUTZ_CHALLENGE_REASON,
        ),
        warnings=["skroutz_snapshot_blocked_by_challenge", "blocked_by_challenge"],
        missing_fields=["name", "brand", "mpn", "gallery_images", "spec_sections"],
    )


def _blocked_resolution(cli: CLIInput) -> PrepareProviderResolutionResult:
    return PrepareProviderResolutionResult(
        source="skroutz",
        provider_id="skroutz",
        fetch=FetchResult(
            url=cli.url,
            final_url=cli.url,
            html=CHALLENGE_HTML,
            status_code=403,
            method="httpx",
            response_headers={
                "content-type": "text/html",
                "x-product-factory-blocked-reason": SKROUTZ_CHALLENGE_REASON,
            },
        ),
        parsed=_blocked_parsed(cli.url),
    )


def test_skroutz_provider_valid_product_html_parses(
    skroutz_provider_fixtures_root: Path,
) -> None:
    fixture_path = skroutz_provider_fixtures_root / "taxonomy_cases" / "143109.html"
    provider = SkroutzProvider(fixture_html_by_url={PRODUCT_URL: fixture_path})
    identity = ProviderInputIdentity(model="143109", url=PRODUCT_URL)

    result = provider.normalize(provider.fetch_snapshot(identity), identity)

    assert result.product.page_type == "product"
    assert result.product.source_name == "skroutz"
    assert result.product.name
    assert result.product.spec_sections


def test_skroutz_http_403_just_a_moment_returns_blocked_by_challenge() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            403,
            headers={"content-type": "text/html", "cf-mitigated": "challenge"},
            text=CHALLENGE_HTML,
            request=request,
        )
    )
    fetcher = SkroutzSnapshotFetcher(transport=transport)

    result = fetcher.fetch(PRODUCT_URL)

    assert result.status == SkroutzFetchStatus.BLOCKED_BY_CHALLENGE
    assert result.blocked is True
    assert result.blocked_reason == "blocked_by_challenge"
    assert result.status_code == 403
    assert result.method == "httpx"


def test_skroutz_live_fetch_uses_playwright_before_httpx() -> None:
    class BrowserFetcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def fetch_playwright(self, url: str) -> FetchResult:
            self.calls.append("playwright")
            return FetchResult(
                url=url,
                final_url=url,
                html="<html><head><title>Product</title></head><body>POCO M8 5G</body></html>",
                status_code=200,
                method="playwright",
                fallback_used=True,
                response_headers={"content-type": "text/html"},
            )

        def fetch_httpx(self, url: str) -> FetchResult:
            self.calls.append("httpx")
            raise AssertionError(
                "httpx should not run when playwright returns a valid snapshot"
            )

    browser_fetcher = BrowserFetcher()
    fetcher = SkroutzSnapshotFetcher(browser_fetcher=browser_fetcher)

    result = fetcher.fetch(PRODUCT_URL)

    assert browser_fetcher.calls == ["playwright"]
    assert result.status == SkroutzFetchStatus.OK
    assert result.method == "playwright"
    assert result.fallback_used is True


def test_skroutz_live_fetch_falls_back_to_httpx_when_playwright_is_challenged() -> None:
    class BrowserFetcher:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def fetch_playwright(self, url: str) -> FetchResult:
            self.calls.append("playwright")
            return FetchResult(
                url=url,
                final_url=url,
                html=CHALLENGE_HTML,
                status_code=200,
                method="playwright",
                fallback_used=True,
                response_headers={"content-type": "text/html"},
            )

        def fetch_httpx(self, url: str) -> FetchResult:
            self.calls.append("httpx")
            return FetchResult(
                url=url,
                final_url=url,
                html="<html><head><title>Product</title></head><body>POCO M8 5G</body></html>",
                status_code=200,
                method="httpx",
                fallback_used=False,
                response_headers={"content-type": "text/html"},
            )

    browser_fetcher = BrowserFetcher()
    fetcher = SkroutzSnapshotFetcher(browser_fetcher=browser_fetcher)

    result = fetcher.fetch(PRODUCT_URL)

    assert browser_fetcher.calls == ["playwright", "httpx"]
    assert result.status == SkroutzFetchStatus.OK
    assert result.method == "httpx"


def test_skroutz_challenge_page_does_not_call_parser() -> None:
    class BlockedFetcher:
        def fetch(self, url: str) -> SkroutzFetchResult:
            return SkroutzFetchResult(
                url=url,
                final_url=url,
                html=CHALLENGE_HTML,
                status_code=403,
                status=SkroutzFetchStatus.BLOCKED_BY_CHALLENGE,
                headers={"content-type": "text/html"},
            )

    class ParserMustNotRun:
        def parse(self, *_args, **_kwargs):
            raise AssertionError("parser should not be called for challenge snapshots")

    identity = ProviderInputIdentity(model="580852", url=PRODUCT_URL)
    provider = SkroutzProvider(fetcher=BlockedFetcher(), parser=ParserMustNotRun())

    result = provider.normalize(provider.fetch_snapshot(identity), identity)

    assert result.product.page_type == "blocked_by_challenge"
    assert result.metadata["blocked_reason"] == "blocked_by_challenge"
    assert "skroutz_snapshot_blocked_by_challenge" in result.warnings


def test_prepare_workflow_succeeds_with_warning_when_skroutz_snapshot_is_blocked(
    tmp_path: Path,
) -> None:
    cli = CLIInput(
        model="580852",
        url=PRODUCT_URL,
        photos=0,
        sections=7,
        skroutz_status=0,
        boxnow=1,
        price="279.90",
        out=str(tmp_path),
    )

    def execute_stage(cli_arg: CLIInput, *, model_dir: Path):
        return execute_prepare_stage(
            cli_arg,
            model_dir=model_dir,
            validate_url_scope_fn=lambda _url: (
                "skroutz",
                True,
                "skroutz_product_path",
            ),
            fetcher_factory=DummyAssetFetcher,
            source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
                status="skipped", message="test"
            ),
            resolve_prepare_provider_input_fn=lambda blocked_cli, **_kwargs: _blocked_resolution(
                blocked_cli
            ),
        )

    result = execute_prepare_workflow(
        cli, work_root=tmp_path / "work", execute_prepare_stage_fn=execute_stage
    )

    assert result.run_status == RunStatus.COMPLETED
    assert result.task_manifest_path.exists()
    assert result.scrape_result.parsed is not None
    assert result.scrape_result.parsed.source.page_type == "blocked_by_challenge"
    assert "blocked_by_challenge" in result.scrape_result.report_warnings
    report = json.loads(
        (result.scrape_dir / "580852.report.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(result.task_manifest_path.read_text(encoding="utf-8"))
    assert report["blocked_snapshot"]["reason"] == "blocked_by_challenge"
    assert manifest["prepare_mode"] == "blocked_snapshot"


def test_invalid_skroutz_path_still_fails_as_invalid_or_unsupported() -> None:
    invalid_url = "https://www.skroutz.gr/c/40/smartphones.html"
    cli = CLIInput(model="580852", url=invalid_url)
    result = PrepareProviderResolutionResult(
        source="skroutz",
        provider_id="skroutz",
        fetch=FetchResult(
            url=invalid_url,
            final_url=invalid_url,
            html=CHALLENGE_HTML,
            status_code=403,
            method="httpx",
        ),
        parsed=_blocked_parsed(invalid_url),
    )

    with pytest.raises(
        RuntimeError, match="Resolved URL is not a supported product page"
    ):
        validate_prepare_provider_resolution_result(cli, result)
