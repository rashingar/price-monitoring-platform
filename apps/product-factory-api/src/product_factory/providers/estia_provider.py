from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_estia import EstiaProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class EstiaProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="estia",
        source_name="estia",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Estia Home Art",
        description="Estia Home Art vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: EstiaProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or EstiaProductParser())
