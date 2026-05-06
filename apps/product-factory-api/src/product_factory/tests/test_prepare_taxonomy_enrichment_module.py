from __future__ import annotations

from pathlib import Path

import pytest

from product_factory.models import ParsedProduct, SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from product_factory.prepare_taxonomy_enrichment import PrepareTaxonomyEnrichmentResult, resolve_prepare_taxonomy_enrichment


def _build_source(
    *,
    source_name: str,
    url: str,
    canonical_url: str | None = None,
    breadcrumbs: list[str] | None = None,
    key_specs: list[SpecItem] | None = None,
    spec_sections: list[SpecSection] | None = None,
) -> SourceProductData:
    return SourceProductData(
        source_name=source_name,
        page_type="product",
        url=url,
        canonical_url=canonical_url or url,
        breadcrumbs=breadcrumbs or [],
        product_code="100001",
        brand="Brand",
        mpn="MODEL-1",
        name="Brand MODEL-1",
        key_specs=key_specs or [],
        spec_sections=spec_sections or [],
    )


def _build_parsed(source: SourceProductData) -> ParsedProduct:
    return ParsedProduct(
        source=source,
        provenance={
            "product_code": "parser",
            "brand": "parser",
            "mpn": "parser",
            "name": "parser",
            "price": "parser",
        },
    )


class DummyFetcher:
    pass


def test_resolve_prepare_taxonomy_enrichment_calls_resolver_with_current_prepare_stage_inputs(tmp_path: Path) -> None:
    key_specs = [SpecItem(label="Power", value="2200 W")]
    spec_sections = [SpecSection(section="Specs", items=[SpecItem(label="Color", value="Black")])]
    source = _build_source(
        source_name="electronet",
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example/canonical",
        breadcrumbs=["Home", "Small Appliances", "Kettles"],
        key_specs=key_specs,
        spec_sections=spec_sections,
    )
    parsed = _build_parsed(source)
    taxonomy = TaxonomyResolution(
        parent_category="Home",
        leaf_category="Small Appliances",
        sub_category="Kettles",
        reason="resolver_reason",
    )
    taxonomy_candidates = [{"taxonomy_path": "Home > Small Appliances > Kettles", "confidence": 0.91}]
    resolver_calls: list[dict[str, object]] = []

    class RecordingResolver:
        def resolve(self, **kwargs):
            resolver_calls.append(kwargs)
            return taxonomy, taxonomy_candidates

    result = resolve_prepare_taxonomy_enrichment(
        source="electronet",
        parsed=parsed,
        fetcher=DummyFetcher(),
        model_dir=tmp_path / "100001",
        taxonomy_resolver_factory=lambda: RecordingResolver(),
    )

    assert isinstance(result, PrepareTaxonomyEnrichmentResult)
    assert resolver_calls == [
        {
            "breadcrumbs": source.breadcrumbs,
            "url": source.canonical_url,
            "name": source.name,
            "key_specs": key_specs,
            "spec_sections": spec_sections,
        }
    ]
    assert result.taxonomy is taxonomy
    assert result.taxonomy_candidates is taxonomy_candidates
    assert result.taxonomy.reason == "resolver_reason"


def test_resolve_prepare_taxonomy_enrichment_skips_skroutz_manufacturer_enrichment_when_disabled(
    tmp_path: Path,
) -> None:
    source = _build_source(source_name="skroutz", url="https://www.skroutz.gr/s/143051/example.html")
    parsed = _build_parsed(source)
    taxonomy = TaxonomyResolution(
        parent_category="Image & Sound",
        leaf_category="Televisions",
        sub_category="50'' and up",
    )
    fetcher = DummyFetcher()
    enrichment_calls: list[dict[str, object]] = []

    class StaticResolver:
        def resolve(self, **_kwargs):
            return taxonomy, []

    def fake_enrich_source_from_manufacturer_docs(**kwargs) -> dict[str, object]:
        enrichment_calls.append(kwargs)
        raise AssertionError("manufacturer enrichment is disabled and should not be called")

    result = resolve_prepare_taxonomy_enrichment(
        source="skroutz",
        parsed=parsed,
        fetcher=fetcher,
        model_dir=tmp_path / "100001",
        taxonomy_resolver_factory=lambda: StaticResolver(),
        enrich_source_from_manufacturer_docs_fn=fake_enrich_source_from_manufacturer_docs,
    )

    assert enrichment_calls == []
    assert result.manufacturer_enrichment == {
        "applied": False,
        "provider": "",
        "providers_considered": [],
        "matched_providers": [],
        "documents": [],
        "documents_discovered": 0,
        "documents_parsed": 0,
        "warnings": [],
        "section_count": 0,
        "field_count": 0,
        "hero_summary_applied": False,
        "presentation_applied": False,
        "presentation_block_count": 0,
        "fallback_reason": "manufacturer_enrichment_disabled",
    }
    assert parsed.source.manufacturer_source_text == ""
    assert parsed.source.manufacturer_spec_sections == []


@pytest.mark.parametrize(
    ("source_name", "fallback_reason"),
    [
        ("electronet", "manufacturer_enrichment_disabled"),
        ("skroutz", "manufacturer_enrichment_disabled"),
    ],
)
def test_resolve_prepare_taxonomy_enrichment_uses_disabled_default_shape(
    tmp_path: Path,
    source_name: str,
    fallback_reason: str,
) -> None:
    source = _build_source(source_name=source_name, url=f"https://example.com/{source_name}")
    parsed = _build_parsed(source)

    class StaticResolver:
        def resolve(self, **_kwargs):
            return TaxonomyResolution(parent_category="Home", leaf_category="Appliances", sub_category="Category"), []

    result = resolve_prepare_taxonomy_enrichment(
        source=source_name,
        parsed=parsed,
        fetcher=DummyFetcher(),
        model_dir=tmp_path / "100001",
        taxonomy_resolver_factory=lambda: StaticResolver(),
        enrich_source_from_manufacturer_docs_fn=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("manufacturer enrichment should not be called for non-skroutz sources")
        ),
    )

    assert result.manufacturer_enrichment == {
        "applied": False,
        "provider": "",
        "providers_considered": [],
        "matched_providers": [],
        "documents": [],
        "documents_discovered": 0,
        "documents_parsed": 0,
        "warnings": [],
        "section_count": 0,
        "field_count": 0,
        "hero_summary_applied": False,
        "presentation_applied": False,
        "presentation_block_count": 0,
        "fallback_reason": fallback_reason,
    }
