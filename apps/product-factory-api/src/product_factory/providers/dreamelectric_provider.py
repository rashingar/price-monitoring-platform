from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_dreamelectric import DreamelectricProductParser
from .electronet_provider import ElectronetProvider
from .models import ProviderDefinition, ProviderKind


class DreamelectricProvider(ElectronetProvider):
    definition = ProviderDefinition(
        provider_id="dreamelectric",
        source_name="dreamelectric",
        kind=ProviderKind.VENDOR_SITE,
        capabilities=ElectronetProvider.definition.capabilities,
        display_name="Dream Electric",
        description="Dream Electric vendor-site provider adapter.",
    )

    def __init__(
        self,
        *,
        fetcher: ElectronetFetcher | None = None,
        parser: DreamelectricProductParser | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher, parser=parser or DreamelectricProductParser())
