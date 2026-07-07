from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_plus4u import Plus4UProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class Plus4UProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="plus4u",
        source_name="plus4u",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Plus4U",
        description="Plus4U vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: Plus4UProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or Plus4UProductParser())
