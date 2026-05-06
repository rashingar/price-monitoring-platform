from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..fetcher import ElectronetFetcher, FetchError
from ..models import ParsedProduct
from ..parser_product_skroutz import SkroutzProductParser
from .base import ProductProvider, ProviderError
from .models import (
    ProviderCapability,
    ProviderDefinition,
    ProviderErrorCode,
    ProviderInputIdentity,
    ProviderKind,
    ProviderResult,
    ProviderSnapshot,
    ProviderSnapshotKind,
    ProviderStage,
)


class SkroutzProvider(ProductProvider):
    definition = ProviderDefinition(
        provider_id="skroutz",
        source_name="skroutz",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=frozenset(
            {
                ProviderCapability.URL_INPUT,
                ProviderCapability.LIVE_FETCH,
                ProviderCapability.FIXTURE_FETCH,
                ProviderCapability.HTML_SNAPSHOT,
                ProviderCapability.NORMALIZED_PRODUCT,
            }
        ),
        display_name="Skroutz",
        description="Skroutz provider adapter with live fetch support and optional fixture overrides.",
    )

    def __init__(
        self,
        *,
        fixture_html_by_url: Mapping[str, Path] | None = None,
        fetcher: ElectronetFetcher | None = None,
        parser: SkroutzProductParser | None = None,
    ) -> None:
        self._fixture_html_by_url = {url: Path(path) for url, path in (fixture_html_by_url or {}).items()}
        self._fetcher = fetcher or ElectronetFetcher()
        self._parser = parser or SkroutzProductParser()

    def supports_identity(self, identity: ProviderInputIdentity) -> bool:
        return bool(identity.url.strip())

    def fetch_snapshot(self, identity: ProviderInputIdentity) -> ProviderSnapshot:
        url = identity.url.strip()
        if not url:
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.UNSUPPORTED_IDENTITY,
                stage=ProviderStage.IDENTITY,
                message="Skroutz provider requires a URL identity",
            )

        fixture_path = self._fixture_html_by_url.get(url)
        if fixture_path is not None:
            return self._snapshot_from_fixture(identity, url, fixture_path)

        try:
            fetch = self._fetcher.fetch_playwright(url)
        except FetchError:
            try:
                fetch = self._fetcher.fetch_httpx(url)
            except FetchError as exc:
                raise ProviderError.build(
                    provider_id=self.provider_id,
                    code=ProviderErrorCode.FETCH_FAILED,
                    stage=ProviderStage.FETCH,
                    message=str(exc),
                    details={"url": url},
                    cause=exc,
                ) from exc

        return ProviderSnapshot(
            provider_id=self.provider_id,
            identity=identity,
            snapshot_kind=ProviderSnapshotKind.HTML,
            requested_url=fetch.url,
            final_url=fetch.final_url,
            content_type=str(fetch.response_headers.get("content-type", "")),
            status_code=fetch.status_code,
            body_text=fetch.html,
            headers=dict(fetch.response_headers),
            metadata={
                "fetch_method": fetch.method,
                "fallback_used": fetch.fallback_used,
            },
        )

    def _snapshot_from_fixture(self, identity: ProviderInputIdentity, url: str, fixture_path: Path) -> ProviderSnapshot:

        if not fixture_path.exists():
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.NOT_FOUND,
                stage=ProviderStage.FETCH,
                message=f"Skroutz fixture does not exist: {fixture_path}",
                details={"url": url, "fixture_path": str(fixture_path)},
            )

        try:
            html = fixture_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.FETCH_FAILED,
                stage=ProviderStage.FETCH,
                message=f"Failed to read Skroutz fixture: {fixture_path}",
                details={"url": url, "fixture_path": str(fixture_path)},
                cause=exc,
            ) from exc

        return ProviderSnapshot(
            provider_id=self.provider_id,
            identity=identity,
            snapshot_kind=ProviderSnapshotKind.HTML,
            requested_url=url,
            final_url=url,
            content_type="text/html; charset=utf-8",
            status_code=200,
            body_text=html,
            metadata={
                "fetch_method": "fixture",
                "fallback_used": False,
                "fixture_path": str(fixture_path),
            },
        )

    def normalize(self, snapshot: ProviderSnapshot, identity: ProviderInputIdentity) -> ProviderResult:
        try:
            parsed = self._parse_snapshot(snapshot)
        except Exception as exc:
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.NORMALIZATION_FAILED,
                stage=ProviderStage.NORMALIZE,
                message=str(exc),
                details={"url": identity.url},
                cause=exc,
            ) from exc

        return self._provider_result(parsed, snapshot, identity)

    def _parse_snapshot(self, snapshot: ProviderSnapshot) -> ParsedProduct:
        return self._parser.parse(
            snapshot.body_text,
            snapshot.final_url or snapshot.requested_url or snapshot.identity.url,
            fallback_used=bool(snapshot.metadata.get("fallback_used", False)),
        )

    def _provider_result(
        self,
        parsed: ParsedProduct,
        snapshot: ProviderSnapshot,
        identity: ProviderInputIdentity,
    ) -> ProviderResult:
        return ProviderResult(
            provider=self.definition,
            identity=identity,
            snapshot=snapshot,
            product=parsed.source,
            provenance=dict(parsed.provenance),
            field_diagnostics=dict(parsed.field_diagnostics),
            warnings=list(parsed.warnings),
            missing_fields=list(parsed.missing_fields),
            critical_missing=list(parsed.critical_missing),
            metadata={
                "fetch_method": str(snapshot.metadata.get("fetch_method", "")),
                "fallback_used": bool(snapshot.metadata.get("fallback_used", False)),
                "fixture_path": str(snapshot.metadata.get("fixture_path", "")),
            },
        )
