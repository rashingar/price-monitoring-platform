from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_euragora import EuragoraProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class EuragoraProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="euragora",
        source_name="euragora",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Euragora",
        description="Euragora WooCommerce vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: EuragoraProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or EuragoraProductParser())
