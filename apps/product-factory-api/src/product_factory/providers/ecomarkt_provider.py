from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_ecomarkt import EcomarktProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class EcomarktProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="ecomarkt",
        source_name="ecomarkt",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Ecomarkt",
        description="Ecomarkt vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: EcomarktProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or EcomarktProductParser())
