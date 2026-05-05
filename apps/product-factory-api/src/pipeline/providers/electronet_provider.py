from __future__ import annotations

from ..fetcher import ElectronetFetcher, FetchError
from ..models import ParsedProduct
from ..parser_product_electronet import ElectronetProductParser
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


class ElectronetProvider(ProductProvider):
    definition = ProviderDefinition(
        provider_id="electronet",
        source_name="electronet",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=frozenset(
            {
                ProviderCapability.URL_INPUT,
                ProviderCapability.LIVE_FETCH,
                ProviderCapability.HTML_SNAPSHOT,
                ProviderCapability.NORMALIZED_PRODUCT,
            }
        ),
        display_name="Electronet",
        description="Compatibility fallback Electronet vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: ElectronetProductParser | None = None,
    ) -> None:
        self._fetcher = fetcher or ElectronetFetcher()
        self._parser = parser or ElectronetProductParser()

    def supports_identity(self, identity: ProviderInputIdentity) -> bool:
        return bool(identity.url.strip())

    def fetch_snapshot(self, identity: ProviderInputIdentity) -> ProviderSnapshot:
        url = identity.url.strip()
        if not url:
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.UNSUPPORTED_IDENTITY,
                stage=ProviderStage.IDENTITY,
                message="Electronet provider requires a URL identity",
            )

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

        return self._snapshot_from_fetch(identity, fetch)

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

        effective_snapshot = snapshot
        if parsed.critical_missing:
            try:
                fallback_fetch = self._fetcher.fetch_playwright(identity.url)
                fallback_snapshot = self._snapshot_from_fetch(identity, fallback_fetch)
                reparsed = self._parse_snapshot(fallback_snapshot)
                if len(reparsed.critical_missing) < len(parsed.critical_missing):
                    effective_snapshot = fallback_snapshot
                    parsed = reparsed
            except FetchError:
                pass
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
            snapshot=effective_snapshot,
            product=parsed.source,
            provenance=dict(parsed.provenance),
            field_diagnostics=dict(parsed.field_diagnostics),
            warnings=list(parsed.warnings),
            missing_fields=list(parsed.missing_fields),
            critical_missing=list(parsed.critical_missing),
            metadata={
                "fetch_method": str(effective_snapshot.metadata.get("fetch_method", "")),
                "fallback_used": bool(effective_snapshot.metadata.get("fallback_used", False)),
            },
        )

    def _snapshot_from_fetch(self, identity: ProviderInputIdentity, fetch) -> ProviderSnapshot:
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

    def _parse_snapshot(self, snapshot: ProviderSnapshot) -> ParsedProduct:
        return self._parser.parse(
            snapshot.body_text,
            snapshot.final_url or snapshot.requested_url or snapshot.identity.url,
            fallback_used=bool(snapshot.metadata.get("fallback_used", False)),
        )
