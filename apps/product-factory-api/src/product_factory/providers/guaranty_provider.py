from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_guaranty import GuarantyProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class GuarantyProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="guaranty",
        source_name="guaranty",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Guaranty",
        description="Guaranty vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: GuarantyProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or GuarantyProductParser())
