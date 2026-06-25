from __future__ import annotations

from ..fetcher import ElectronetFetcher
from ..parser_product_bestprice import BestPriceProductParser
from ..parser_product_apothema import ApothemaProductParser
from ..parser_product_dreamelectric import DreamelectricProductParser
from ..parser_product_electronet import ElectronetProductParser
from ..parser_product_euragora import EuragoraProductParser
from ..parser_product_estia import EstiaProductParser
from ..parser_product_guaranty import GuarantyProductParser
from ..parser_product_fgeurope import FGEuropeProductParser
from ..parser_product_kotsovolos import KotsovolosProductParser
from ..parser_product_marketquest import MarketQuestProductParser
from ..parser_product_manufacturer import ManufacturerProductParser
from ..parser_product_pampoukidis import PampoukidisProductParser
from ..parser_product_skroutz import SkroutzProductParser
from .base import ProductProvider, ProviderError
from .apothema_provider import ApothemaProvider
from .bestprice_provider import BestPriceProvider
from .dreamelectric_provider import DreamelectricProvider
from .electronet_provider import ElectronetProvider
from .euragora_provider import EuragoraProvider
from .estia_provider import EstiaProvider
from .guaranty_provider import GuarantyProvider
from .fgeurope_provider import FGEuropeProvider
from .kotsovolos_provider import KotsovolosProvider
from .marketquest_provider import MarketQuestProvider
from .pampoukidis_provider import PampoukidisProvider
from .models import ProviderDefinition, ProviderErrorCode, ProviderKind, ProviderStage
from .skroutz_provider import SkroutzProvider

RUNTIME_SOURCE_PROVIDER_IDS = {
    "apothema": "apothema",
    "bestprice": "bestprice",
    "dreamelectric": "dreamelectric",
    "electronet": "electronet",
    "estia": "estia",
    "euragora": "euragora",
    "guaranty": "guaranty",
    "fgeurope": "fgeurope",
    "kotsovolos": "kotsovolos",
    "marketquest": "marketquest",
    "pampoukidis": "pampoukidis",
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
    apothema_parser: ApothemaProductParser | None = None,
    bestprice_parser: BestPriceProductParser | None = None,
    dreamelectric_parser: DreamelectricProductParser | None = None,
    estia_parser: EstiaProductParser | None = None,
    euragora_parser: EuragoraProductParser | None = None,
    guaranty_parser: GuarantyProductParser | None = None,
    fgeurope_parser: FGEuropeProductParser | None = None,
    kotsovolos_parser: KotsovolosProductParser | None = None,
    marketquest_parser: MarketQuestProductParser | None = None,
    pampoukidis_parser: PampoukidisProductParser | None = None,
) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        ApothemaProvider(
            fetcher=fetcher, parser=apothema_parser or ApothemaProductParser()
        )
    )
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
        EstiaProvider(fetcher=fetcher, parser=estia_parser or EstiaProductParser())
    )
    registry.register(
        EuragoraProvider(
            fetcher=fetcher, parser=euragora_parser or EuragoraProductParser()
        )
    )
    registry.register(
        GuarantyProvider(
            fetcher=fetcher, parser=guaranty_parser or GuarantyProductParser()
        )
    )
    registry.register(
        FGEuropeProvider(
            fetcher=fetcher, parser=fgeurope_parser or FGEuropeProductParser()
        )
    )
    registry.register(
        KotsovolosProvider(
            fetcher=fetcher, parser=kotsovolos_parser or KotsovolosProductParser()
        )
    )
    registry.register(
        MarketQuestProvider(
            fetcher=fetcher,
            parser=marketquest_parser or MarketQuestProductParser(),
        )
    )
    registry.register(
        PampoukidisProvider(
            fetcher=fetcher,
            parser=pampoukidis_parser or PampoukidisProductParser(),
        )
    )
    registry.register(SkroutzProvider(parser=skroutz_parser))
    return registry
