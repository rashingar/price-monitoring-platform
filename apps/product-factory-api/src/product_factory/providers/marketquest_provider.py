from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_marketquest import MarketQuestProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class MarketQuestProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="marketquest",
        source_name="marketquest",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="MarketQuest",
        description="MarketQuest vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: MarketQuestProductParser | None = None,
    ) -> None:
        super().__init__(
            fetcher=fetcher, parser=parser or MarketQuestProductParser()
        )
