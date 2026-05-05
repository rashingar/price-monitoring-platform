from __future__ import annotations

import pytest

from pipeline.models import CLIInput, SourceProductData, SpecItem, SpecSection
from pipeline.prepare_provider_resolution import PrepareProviderResolutionResult, resolve_prepare_provider_resolution
from pipeline.providers import (
    ProductProvider,
    ProviderDefinition,
    ProviderError,
    ProviderErrorCode,
    ProviderInputIdentity,
    ProviderKind,
    ProviderRegistry,
    ProviderResult,
    ProviderSnapshot,
    ProviderSnapshotKind,
    ProviderStage,
)


class DummySchemaMatcher:
    known_section_titles = set()

    def __init__(self, *_args, **_kwargs) -> None:
        pass


def _build_cli(url: str, *, model: str = "123456") -> CLIInput:
    return CLIInput(
        model=model,
        url=url,
        photos=2,
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price="19",
        out="out",
    )


def _build_source(
    *,
    source_name: str,
    url: str,
    page_type: str = "product",
    product_code: str = "",
    name: str = "Example Product",
    taxonomy_escalation_reason: str = "",
    mpn: str = "",
) -> SourceProductData:
    return SourceProductData(
        source_name=source_name,
        page_type=page_type,
        url=url,
        canonical_url=url,
        product_code=product_code,
        brand="Example",
        name=name,
        mpn=mpn,
        taxonomy_escalation_reason=taxonomy_escalation_reason,
        spec_sections=[SpecSection(section="Χαρακτηριστικά", items=[SpecItem(label="Ισχύς", value="2200 W")])],
    )


class StaticProvider(ProductProvider):
    def __init__(
        self,
        *,
        provider_id: str,
        source_name: str,
        product: SourceProductData,
        final_url: str = "",
        fetch_method: str = "fixture",
        fetch_error: ProviderError | None = None,
        normalize_error: ProviderError | None = None,
    ) -> None:
        kind = ProviderKind.MANUFACTURER_SITE if source_name.startswith("manufacturer_") else ProviderKind.VENDOR_SITE
        self.definition = ProviderDefinition(
            provider_id=provider_id,
            source_name=source_name,
            kind=kind,
        )
        self._product = product
        self._final_url = final_url
        self._fetch_method = fetch_method
        self._fetch_error = fetch_error
        self._normalize_error = normalize_error

    def fetch_snapshot(self, identity: ProviderInputIdentity) -> ProviderSnapshot:
        if self._fetch_error is not None:
            raise self._fetch_error
        return ProviderSnapshot(
            provider_id=self.provider_id,
            identity=identity,
            snapshot_kind=ProviderSnapshotKind.HTML,
            requested_url=identity.url,
            final_url=self._final_url or identity.url,
            content_type="text/html",
            status_code=200,
            body_text="<html></html>",
            metadata={"fetch_method": self._fetch_method, "fallback_used": False},
        )

    def normalize(self, snapshot: ProviderSnapshot, identity: ProviderInputIdentity) -> ProviderResult:
        if self._normalize_error is not None:
            raise self._normalize_error
        return ProviderResult(
            provider=self.definition,
            identity=identity,
            snapshot=snapshot,
            product=self._product,
        )


def _build_provider_error(message: str, *, provider_id: str = "skroutz", stage: ProviderStage = ProviderStage.FETCH) -> ProviderError:
    return ProviderError.build(
        provider_id=provider_id,
        code=ProviderErrorCode.FETCH_FAILED,
        stage=stage,
        message=message,
    )


def _resolve_with_registry(
    cli: CLIInput,
    registry: ProviderRegistry,
    *,
    source: str,
    validate_url_scope_fn,
    source_to_provider_id_fn=None,
) -> PrepareProviderResolutionResult:
    return resolve_prepare_provider_resolution(
        cli,
        detect_source_fn=lambda _url: source,
        validate_url_scope_fn=validate_url_scope_fn,
        schema_matcher_factory=DummySchemaMatcher,
        electronet_parser_factory=lambda **_kwargs: object(),
        skroutz_parser_factory=lambda: object(),
        manufacturer_parser_factory=lambda: object(),
        fetcher_factory=lambda: object(),
        bootstrap_provider_registry_fn=lambda **_kwargs: registry,
        source_to_provider_id_fn=source_to_provider_id_fn or (lambda _source: source),
    )


def test_prepare_provider_resolution_fails_when_supported_source_has_no_provider_mapping() -> None:
    cli = _build_cli("https://www.skroutz.gr/s/123456/example.html")

    with pytest.raises(RuntimeError, match="No provider configured for supported source: skroutz"):
        _resolve_with_registry(
            cli,
            ProviderRegistry(),
            source="skroutz",
            validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
            source_to_provider_id_fn=lambda _source: None,
        )


def test_prepare_provider_resolution_fails_when_registry_provider_is_missing() -> None:
    cli = _build_cli("https://www.skroutz.gr/s/123456/example.html")

    with pytest.raises(RuntimeError, match="Provider 'skroutz' is not registered"):
        _resolve_with_registry(
            cli,
            ProviderRegistry(),
            source="skroutz",
            validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        )


@pytest.mark.parametrize(
    ("failure_stage", "stage_enum"),
    [
        ("fetch", ProviderStage.FETCH),
        ("normalize", ProviderStage.NORMALIZE),
    ],
)
def test_prepare_provider_resolution_preserves_provider_error_runtime_behavior(
    failure_stage: str,
    stage_enum: ProviderStage,
) -> None:
    cli = _build_cli("https://www.skroutz.gr/s/123456/example.html")
    registry = ProviderRegistry()
    provider_error = _build_provider_error(f"{failure_stage}_failed", stage=stage_enum)
    provider = StaticProvider(
        provider_id="skroutz",
        source_name="skroutz",
        product=_build_source(source_name="skroutz", url=cli.url),
        fetch_error=provider_error if failure_stage == "fetch" else None,
        normalize_error=provider_error if failure_stage == "normalize" else None,
    )
    registry.register(provider)

    with pytest.raises(RuntimeError, match=f"{failure_stage}_failed") as exc_info:
        _resolve_with_registry(
            cli,
            registry,
            source="skroutz",
            validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        )

    assert exc_info.value.__cause__ is provider_error


def test_prepare_provider_resolution_fails_when_final_url_scope_mismatches() -> None:
    cli = _build_cli("https://www.skroutz.gr/s/123456/example.html")
    final_url = "https://www.skroutz.gr/c/123/category.html"
    validated_urls: list[str] = []
    registry = ProviderRegistry()
    registry.register(
        StaticProvider(
            provider_id="skroutz",
            source_name="skroutz",
            product=_build_source(source_name="skroutz", url=cli.url),
            final_url=final_url,
        )
    )

    with pytest.raises(RuntimeError, match="Resolved URL is not a supported product page"):
        _resolve_with_registry(
            cli,
            registry,
            source="skroutz",
            validate_url_scope_fn=lambda url: (validated_urls.append(url) or ("skroutz", False, "skroutz_non_product_path")),
        )

    assert validated_urls == [final_url]


def test_prepare_provider_resolution_keeps_electronet_product_code_mismatch_as_warning() -> None:
    cli = _build_cli("https://www.electronet.gr/example")
    registry = ProviderRegistry()
    registry.register(
        StaticProvider(
            provider_id="electronet",
            source_name="electronet",
            product=_build_source(
                source_name="electronet",
                url=cli.url,
                product_code="654321",
            ),
            fetch_method="httpx",
        )
    )

    result = _resolve_with_registry(
        cli,
        registry,
        source="electronet",
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
    )

    assert isinstance(result, PrepareProviderResolutionResult)
    assert result.source == "electronet"
    assert result.provider_id == "electronet"
    assert result.fetch.method == "httpx"
    assert result.parsed.warnings == ["source_product_code_mismatch:input=123456:page=654321"]


def test_prepare_provider_resolution_fails_for_skroutz_non_product_page() -> None:
    cli = _build_cli("https://www.skroutz.gr/s/123456/example.html")
    registry = ProviderRegistry()
    registry.register(
        StaticProvider(
            provider_id="skroutz",
            source_name="skroutz",
            product=_build_source(
                source_name="skroutz",
                url=cli.url,
                page_type="listing",
                taxonomy_escalation_reason="unsupported_skroutz_page_type",
            ),
        )
    )

    with pytest.raises(RuntimeError, match="Unsupported Skroutz page type: unsupported_skroutz_page_type"):
        _resolve_with_registry(
            cli,
            registry,
            source="skroutz",
            validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        )


def test_prepare_provider_resolution_fails_for_manufacturer_non_product_page() -> None:
    cli = _build_cli("https://shop.tefal.gr/products/example")
    registry = ProviderRegistry()
    registry.register(
        StaticProvider(
            provider_id="manufacturer_tefal",
            source_name="manufacturer_tefal",
            product=_build_source(
                source_name="manufacturer_tefal",
                url=cli.url,
                page_type="category",
                taxonomy_escalation_reason="unsupported_manufacturer_page_type",
            ),
        )
    )

    with pytest.raises(RuntimeError, match="Unsupported manufacturer page type: unsupported_manufacturer_page_type"):
        _resolve_with_registry(
            cli,
            registry,
            source="manufacturer_tefal",
            validate_url_scope_fn=lambda _url: ("manufacturer_tefal", True, "manufacturer_tefal_product_path"),
        )
