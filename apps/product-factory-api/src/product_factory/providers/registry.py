from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_bestprice import BestPriceProductParser
from ..parser_product_dreamelectric import DreamelectricProductParser
from ..parser_product_electronet import ElectronetProductParser
from ..parser_product_kotsovolos import KotsovolosProductParser
from ..parser_product_manufacturer import ManufacturerProductParser
from ..parser_product_skroutz import SkroutzProductParser
from .base import ProductProvider, ProviderError
from .bestprice_provider import BestPriceProvider
from .dreamelectric_provider import DreamelectricProvider
from .electronet_provider import ElectronetProvider
from .kotsovolos_provider import KotsovolosProvider
from .models import ProviderDefinition, ProviderErrorCode, ProviderKind, ProviderStage
from .skroutz_provider import SkroutzProvider

RUNTIME_SOURCE_PROVIDER_IDS = {
    "bestprice": "bestprice",
    "dreamelectric": "dreamelectric",
    "electronet": "electronet",
    "kotsovolos": "kotsovolos",
    "skroutz": "skroutz",
}


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProductProvider] = {}

    def register(self, provider: ProductProvider) -> None:
        provider_id = provider.provider_id.strip()
        if not provider_id:
            raise ProviderError.build(
                provider_id="",
                code=ProviderErrorCode.REGISTRATION_FAILED,
                stage=ProviderStage.REGISTRY,
                message="Provider id must be non-empty",
            )
        if provider_id in self._providers:
            raise ProviderError.build(
                provider_id=provider_id,
                code=ProviderErrorCode.REGISTRATION_FAILED,
                stage=ProviderStage.REGISTRY,
                message=f"Provider '{provider_id}' is already registered",
            )
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> ProductProvider | None:
        return self._providers.get(provider_id.strip())

    def require(self, provider_id: str) -> ProductProvider:
        provider = self.get(provider_id)
        if provider is None:
            raise ProviderError.build(
                provider_id=provider_id.strip(),
                code=ProviderErrorCode.NOT_FOUND,
                stage=ProviderStage.REGISTRY,
                message=f"Provider '{provider_id}' is not registered",
            )
        return provider

    def definitions(
        self, *, kind: ProviderKind | None = None
    ) -> list[ProviderDefinition]:
        definitions = [provider.definition for provider in self._providers.values()]
        if kind is not None:
            definitions = [
                definition for definition in definitions if definition.kind == kind
            ]
        return sorted(definitions, key=lambda definition: definition.provider_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


def source_to_provider_id(source: str) -> str | None:
    return RUNTIME_SOURCE_PROVIDER_IDS.get(source.strip())


def bootstrap_runtime_provider_registry(
    *,
    fetcher: ElectronetFetcher,
    electronet_parser: ElectronetProductParser,
    skroutz_parser: SkroutzProductParser,
    manufacturer_parser: ManufacturerProductParser,
    bestprice_parser: BestPriceProductParser | None = None,
    dreamelectric_parser: DreamelectricProductParser | None = None,
    kotsovolos_parser: KotsovolosProductParser | None = None,
) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        BestPriceProvider(
            fetcher=fetcher, parser=bestprice_parser or BestPriceProductParser()
        )
    )
    registry.register(
        DreamelectricProvider(
            fetcher=fetcher,
            parser=dreamelectric_parser or DreamelectricProductParser(),
        )
    )
    registry.register(ElectronetProvider(fetcher=fetcher, parser=electronet_parser))
    registry.register(
        KotsovolosProvider(
            fetcher=fetcher, parser=kotsovolos_parser or KotsovolosProductParser()
        )
    )
    registry.register(SkroutzProvider(parser=skroutz_parser))
    return registry
