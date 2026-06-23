from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_pampoukidis import PampoukidisProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class PampoukidisProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="pampoukidis",
        source_name="pampoukidis",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Pampoukidis",
        description="Pampoukidis vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: PampoukidisProductParser | None = None,
    ) -> None:
        super().__init__(
            fetcher=fetcher, parser=parser or PampoukidisProductParser()
        )
