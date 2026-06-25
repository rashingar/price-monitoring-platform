from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_fgeurope import FGEuropeProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class FGEuropeProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="fgeurope",
        source_name="fgeurope",
        kind=ProviderKind.MANUFACTURER_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="FG Europe",
        description="FG Europe manufacturer-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: FGEuropeProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or FGEuropeProductParser())
