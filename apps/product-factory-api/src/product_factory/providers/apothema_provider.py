from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from ..fetcher import ElectronetFetcher, FetchError
from ..parser_product_apothema import ApothemaProductParser
from .electronet_provider import ElectronetProvider
from .models import (
    ProviderDefinition,
    ProviderErrorCode,
    ProviderInputIdentity,
    ProviderKind,
    ProviderSnapshot,
    ProviderSnapshotKind,
    ProviderStage,
)
from .base import ProviderError


class ApothemaProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="apothema",
        source_name="apothema",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Apothema",
        description="Apothema vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: ApothemaProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or ApothemaProductParser())

    def fetch_snapshot(self, identity: ProviderInputIdentity) -> ProviderSnapshot:
        url = identity.url.strip()
        if not url:
            raise ProviderError.build(
                provider_id=self.provider_id,
                code=ProviderErrorCode.UNSUPPORTED_IDENTITY,
                stage=ProviderStage.IDENTITY,
                message="Apothema provider requires a URL identity",
            )

        fetch_url = self._fetchable_url(url)
        try:
            fetch = self._fetcher.fetch_httpx(fetch_url)
            if not fetch.html.strip():
                fetch = self._fetcher.fetch_playwright(fetch_url)
        except FetchError:
            try:
                fetch = self._fetcher.fetch_playwright(fetch_url)
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
            requested_url=url,
            final_url=fetch.final_url,
            content_type=str(fetch.response_headers.get("content-type", "")),
            status_code=fetch.status_code,
            body_text=fetch.html,
            headers=dict(fetch.response_headers),
            metadata={
                "fetch_method": fetch.method,
                "fallback_used": fetch.fallback_used or fetch_url != url,
                "fetch_url": fetch_url,
            },
        )

    def _fetchable_url(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
