from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_kountisae import KountisAEProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class KountisAEProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="kountisae",
        source_name="kountisae",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Kountis AE",
        description="Kountis AE vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: KountisAEProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or KountisAEProductParser())
