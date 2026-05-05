from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.models import CLIInput, FetchResult, ParsedProduct, SchemaMatchResult, SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from pipeline.prepare_provider_resolution import PrepareProviderResolutionResult
from pipeline.prepare_result_assembly import PrepareResultAssemblyResult
from pipeline.prepare_scrape_persistence import PrepareScrapePersistenceInput, PrepareScrapePersistenceResult
from pipeline.prepare_stage import execute_prepare_stage
from pipeline.prepare_taxonomy_enrichment import PrepareTaxonomyEnrichmentResult


def _build_cli(tmp_path: Path, *, model: str = "100001", url: str, sections: int = 0) -> CLIInput:
    return CLIInput(
        model=model,
        url=url,
        photos=2,
        sections=sections,
        skroutz_status=1,
        boxnow=0,
        price="299",
        out=str(tmp_path),
    )


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


def _build_prepare_provider_resolution_result(
    *,
    source: str,
    url: str,
    parsed: ParsedProduct,
    fetch_method: str = "fixture",
) -> PrepareProviderResolutionResult:
    return PrepareProviderResolutionResult(
        source=source,
        provider_id=source,
        fetch=FetchResult(
            url=url,
            final_url=url,
            html="<html></html>",
            status_code=200,
            method=fetch_method,
            fallback_used=False,
        ),
        parsed=parsed,
    )


def _persist_stub(persistence_input: PrepareScrapePersistenceInput) -> PrepareScrapePersistenceResult:
    return PrepareScrapePersistenceResult(
        scrape_dir=persistence_input.scrape_dir,
        raw_html_path=persistence_input.raw_html_path,
        source_json_path=persistence_input.source_json_path,
        normalized_json_path=persistence_input.normalized_json_path,
        report_json_path=persistence_input.report_json_path,
        bescos_raw_path=persistence_input.bescos_raw_path,
    )


def _build_schema_match() -> SchemaMatchResult:
    return SchemaMatchResult(matched_schema_id="schema-1", score=0.9)


def _build_assembly_result(*, cli: CLIInput, source: str) -> PrepareResultAssemblyResult:
    return PrepareResultAssemblyResult(
        schema_match=_build_schema_match(),
        schema_candidates=[{"matched_schema_id": "schema-1"}],
        row={"model": cli.model},
        normalized={"input": cli.to_dict()},
        report={"source": source, "warnings": [], "identity_checks": {"source": source}},
    )


class DummyFetcher:
    def download_gallery_images(self, **_kwargs):
        return [], [], []

    def download_besco_images(self, **_kwargs):
        return [], [], []


def test_prepare_stage_passes_current_source_fields_to_taxonomy_resolver_and_propagates_candidates(tmp_path: Path) -> None:
    cli = _build_cli(tmp_path, url="https://www.electronet.gr/example")
    key_specs = [SpecItem(label="Power", value="2200 W")]
    spec_sections = [SpecSection(section="Specs", items=[SpecItem(label="Color", value="Black")])]
    source = _build_source(
        source_name="electronet",
        url=cli.url,
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
    )
    taxonomy_candidates = [
        {"taxonomy_path": "Home > Small Appliances > Kettles", "confidence": 0.91},
        {"taxonomy_path": "Home > Kitchen > Kettles", "confidence": 0.54},
    ]
    assembly_calls: list[dict[str, object]] = []

    def fake_assemble_prepare_result(**kwargs) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return _build_assembly_result(cli=kwargs["cli"], source=kwargs["source"])

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_product_path"),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="electronet",
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **kwargs: PrepareTaxonomyEnrichmentResult(
            taxonomy=taxonomy,
            taxonomy_candidates=taxonomy_candidates,
            manufacturer_enrichment={
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
                "fallback_reason": "manufacturer_enrichment_deprecated",
            },
        ),
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_persist_stub,
    )

    assert len(assembly_calls) == 1
    assert assembly_calls[0]["taxonomy"] is taxonomy
    assert assembly_calls[0]["taxonomy_candidates"] is taxonomy_candidates
    assert result["taxonomy"] is taxonomy
    assert result["taxonomy_candidates"] is taxonomy_candidates


def test_prepare_stage_propagates_taxonomy_enrichment_payload_and_mutated_source(tmp_path: Path) -> None:
    cli = _build_cli(tmp_path, model="143051", url="https://www.skroutz.gr/s/143051/example.html")
    source = _build_source(
        source_name="skroutz",
        url=cli.url,
        breadcrumbs=["Home", "Televisions"],
        key_specs=[SpecItem(label="Diagonal", value='55"')],
        spec_sections=[SpecSection(section="Image", items=[SpecItem(label="Resolution", value="4K")])],
    )
    parsed = _build_parsed(source)
    taxonomy = TaxonomyResolution(
        parent_category="Image & Sound",
        leaf_category="Televisions",
        sub_category="50'' and up",
    )
    assembly_calls: list[dict[str, object]] = []
    enrichment_result = {
        "applied": True,
        "provider": "brand_docs",
        "providers_considered": ["brand_docs"],
        "matched_providers": ["brand_docs"],
        "documents": [{"local_path": str(tmp_path / "manufacturer" / "manual.pdf")}],
        "documents_discovered": 1,
        "documents_parsed": 1,
        "warnings": ["manufacturer_pdf_used"],
        "section_count": 1,
        "field_count": 2,
        "hero_summary_applied": False,
        "presentation_applied": False,
        "presentation_block_count": 0,
        "fallback_reason": "",
    }

    fetcher = DummyFetcher()

    def fake_resolve_prepare_taxonomy_enrichment(**kwargs) -> PrepareTaxonomyEnrichmentResult:
        kwargs["parsed"].source.manufacturer_source_text = "Power: 2200 W"
        kwargs["parsed"].source.manufacturer_spec_sections = [
            SpecSection(section="Manufacturer Specs", items=[SpecItem(label="Power", value="2200 W")])
        ]
        return PrepareTaxonomyEnrichmentResult(
            taxonomy=taxonomy,
            taxonomy_candidates=[],
            manufacturer_enrichment=enrichment_result,
        )

    def fake_assemble_prepare_result(**kwargs) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return PrepareResultAssemblyResult(
            schema_match=_build_schema_match(),
            schema_candidates=[{"matched_schema_id": "schema-1"}],
            row={"model": kwargs["cli"].model},
            normalized={
                "manufacturer_source_text": kwargs["parsed"].source.manufacturer_source_text,
                "manufacturer_section_count": len(kwargs["parsed"].source.manufacturer_spec_sections),
            },
            report={"source": kwargs["source"], "warnings": [], "identity_checks": {"source": kwargs["source"]}},
        )

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="skroutz",
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=fake_resolve_prepare_taxonomy_enrichment,
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_persist_stub,
    )

    assert len(assembly_calls) == 1
    assert assembly_calls[0]["manufacturer_enrichment"] is enrichment_result
    assert assembly_calls[0]["parsed"].source.manufacturer_source_text == "Power: 2200 W"
    assert [section.section for section in assembly_calls[0]["parsed"].source.manufacturer_spec_sections] == [
        "Manufacturer Specs"
    ]
    assert result["manufacturer_enrichment"] is enrichment_result
    assert result["parsed"].source.manufacturer_source_text == "Power: 2200 W"
    assert result["normalized"] == {
        "manufacturer_source_text": "Power: 2200 W",
        "manufacturer_section_count": 1,
    }


@pytest.mark.parametrize(
    ("source_name", "scope_reason", "fallback_reason"),
    [
        ("electronet", "electronet_product_path", "manufacturer_enrichment_deprecated"),
        ("skroutz", "skroutz_product_path", "manufacturer_enrichment_deprecated"),
    ],
)
def test_prepare_stage_uses_deprecated_manufacturer_enrichment_default_shape(
    tmp_path: Path,
    source_name: str,
    scope_reason: str,
    fallback_reason: str,
) -> None:
    cli = _build_cli(tmp_path, url=f"https://example.com/{source_name}")
    source = _build_source(source_name=source_name, url=cli.url)
    parsed = _build_parsed(source)
    assembly_calls: list[dict[str, object]] = []

    def fake_assemble_prepare_result(**kwargs) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return _build_assembly_result(cli=kwargs["cli"], source=kwargs["source"])

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: (source_name, True, scope_reason),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source=source_name,
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: PrepareTaxonomyEnrichmentResult(
            taxonomy=TaxonomyResolution(parent_category="Home", leaf_category="Appliances", sub_category="Category"),
            taxonomy_candidates=[],
            manufacturer_enrichment={
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
            },
        ),
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_persist_stub,
    )

    expected_manufacturer_enrichment = {
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

    assert len(assembly_calls) == 1
    assert assembly_calls[0]["manufacturer_enrichment"] == expected_manufacturer_enrichment
    assert result["manufacturer_enrichment"] == expected_manufacturer_enrichment


def test_prepare_stage_with_real_result_assembly_keeps_taxonomy_reason_in_report_warnings_and_enrichment_warnings_nested(
    tmp_path: Path,
) -> None:
    cli = _build_cli(tmp_path, model="200002", url="https://www.skroutz.gr/s/200002/example.html")
    source = _build_source(source_name="skroutz", url=cli.url)
    parsed = _build_parsed(source)
    taxonomy_reason = "taxonomy_resolved_from_candidate_fallback"
    taxonomy_candidates = [{"taxonomy_path": "Home > Appliances > Special Cases"}]

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="skroutz",
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: PrepareTaxonomyEnrichmentResult(
            taxonomy=TaxonomyResolution(
                parent_category="Home",
                leaf_category="Appliances",
                sub_category="Special Cases",
                cta_url="https://www.etranoulis.gr/example",
                reason=taxonomy_reason,
            ),
            taxonomy_candidates=taxonomy_candidates,
            manufacturer_enrichment={
                "applied": False,
                "provider": "",
                "providers_considered": [],
                "matched_providers": [],
                "documents": [],
                "documents_discovered": 0,
                "documents_parsed": 0,
                "warnings": ["manufacturer_doc_lookup_unavailable"],
                "section_count": 0,
                "field_count": 0,
                "hero_summary_applied": False,
                "presentation_applied": False,
                "presentation_block_count": 0,
                "fallback_reason": "provider_not_matched",
            },
        ),
        persist_prepare_scrape_artifacts_fn=_persist_stub,
    )

    assert taxonomy_reason in result["report"]["warnings"]
    assert result["report"]["taxonomy_candidates"] == taxonomy_candidates
    assert result["report"]["manufacturer_enrichment"]["warnings"] == ["manufacturer_doc_lookup_unavailable"]
    assert "manufacturer_doc_lookup_unavailable" not in result["report"]["warnings"]


def test_prepare_stage_returns_current_output_shape_for_downstream_code(tmp_path: Path) -> None:
    cli = _build_cli(tmp_path, url="https://www.electronet.gr/example")
    source = _build_source(source_name="electronet", url=cli.url)
    parsed = _build_parsed(source)

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_product_path"),
        fetcher_factory=DummyFetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="electronet",
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: PrepareTaxonomyEnrichmentResult(
            taxonomy=TaxonomyResolution(parent_category="Home", leaf_category="Appliances", sub_category="Category"),
            taxonomy_candidates=[],
            manufacturer_enrichment={
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
                "fallback_reason": "manufacturer_enrichment_deprecated",
            },
        ),
        assemble_prepare_result_fn=lambda **kwargs: _build_assembly_result(cli=kwargs["cli"], source=kwargs["source"]),
        persist_prepare_scrape_artifacts_fn=_persist_stub,
    )

    assert set(result) == {
        "cli",
        "source",
        "fetch",
        "parsed",
        "taxonomy",
        "taxonomy_candidates",
        "schema_match",
        "schema_candidates",
        "manufacturer_enrichment",
        "row",
        "normalized",
        "report",
        "model_dir",
        "raw_html_path",
        "source_json_path",
        "normalized_json_path",
        "report_json_path",
        "selected_presentation_blocks",
        "downloaded_gallery",
        "downloaded_besco",
        "besco_filenames_by_section",
    }
    assert result["cli"] is cli
    assert result["parsed"] is parsed
    assert result["source"] == "electronet"
    assert result["selected_presentation_blocks"] == []
    assert result["downloaded_gallery"] == []
    assert result["downloaded_besco"] == []
    assert result["besco_filenames_by_section"] == {}
