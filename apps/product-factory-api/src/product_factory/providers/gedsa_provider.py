from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_gedsa import GedsaProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class GedsaProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="gedsa",
        source_name="gedsa",
        kind=ProviderKind.MANUFACTURER_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="G.E. Dimitriou",
        description="GEDSA manufacturer-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: GedsaProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or GedsaProductParser())
