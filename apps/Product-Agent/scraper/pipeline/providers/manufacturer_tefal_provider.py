from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ..fetcher import ElectronetFetcher, FetchError
from ..parser_product_manufacturer import ManufacturerProductParser
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


class ManufacturerTefalProvider(ProductProvider):
    definition = ProviderDefinition(
        provider_id="manufacturer_tefal",
        source_name="manufacturer_tefal",
        kind=ProviderKind.MANUFACTURER_SITE,
        capabilities=frozenset(
            {
                ProviderCapability.URL_INPUT,
                ProviderCapability.LIVE_FETCH,
                ProviderCapability.FIXTURE_FETCH,
                ProviderCapability.HTML_SNAPSHOT,
                ProviderCapability.NORMALIZED_PRODUCT,
            }
        ),
        display_name="Tefal Shop",
        description="Manufacturer-site provider adapter for supported Tefal product pages with optional fixture overrides.",
    )

    def __init__(
        self,
        *,
        fixture_html_by_url: Mapping[str, Path] | None = None,
        fetcher: ElectronetFetcher | None = None,
        parser: ManufacturerProductParser | None = None,
    ) -> None:
        self._fixture_html_by_url = {url: Path(path) for url, path in (fixture_html_by_url or {}).items()}
        self._fetcher = fetcher or ElectronetFetcher()
        self._parser = parser or ManufacturerProductParser()

    def supports_identity(self, identity: ProviderInputIdentity) -> bool:
        return bool(identity.url.strip())

    def fetch_snapshot(self, identity: ProviderInputIdentity) -> ProviderSnapshot:
        url = identity.url.strip()
        if not url:
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.UNSUPPORTED_IDENTITY,
                stage=ProviderStage.IDENTITY,
                message="Manufacturer Tefal provider requires a URL identity",
            )

        fixture_path = self._fixture_html_by_url.get(url)
        if fixture_path is not None:
            return self._snapshot_from_fixture(identity, url, fixture_path)

        try:
            fetch = self._fetcher.fetch_httpx(url)
        except FetchError:
            try:
                fetch = self._fetcher.fetch_playwright(url)
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
                message=f"Manufacturer Tefal fixture does not exist: {fixture_path}",
                details={"url": url, "fixture_path": str(fixture_path)},
            )

        try:
            html = fixture_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.FETCH_FAILED,
                stage=ProviderStage.FETCH,
                message=f"Failed to read manufacturer Tefal fixture: {fixture_path}",
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

    def _parse_snapshot(self, snapshot: ProviderSnapshot):
        return self._parser.parse(
            snapshot.body_text,
            snapshot.final_url or snapshot.requested_url or snapshot.identity.url,
            source_name=self.source_name,
            fallback_used=bool(snapshot.metadata.get("fallback_used", False)),
        )


class ManufacturerBoschProvider(ManufacturerTefalProvider):
    definition = ProviderDefinition(
        provider_id="manufacturer_bosch",
        source_name="manufacturer_bosch",
        kind=ProviderKind.MANUFACTURER_SITE,
        capabilities=frozenset(
            {
                ProviderCapability.URL_INPUT,
                ProviderCapability.LIVE_FETCH,
                ProviderCapability.FIXTURE_FETCH,
                ProviderCapability.HTML_SNAPSHOT,
                ProviderCapability.NORMALIZED_PRODUCT,
            }
        ),
        display_name="Bosch Home",
        description="Manufacturer-site provider adapter for supported Bosch product pages.",
    )
