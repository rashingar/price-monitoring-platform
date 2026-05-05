from __future__ import annotations

from pathlib import Path

from pipeline.models import CLIInput, FetchResult, ParsedProduct, SourceProductData, TaxonomyResolution
from pipeline.prepare_provider_resolution import PrepareProviderResolutionResult
from pipeline.prepare_result_assembly import PrepareResultAssemblyResult
from pipeline.prepare_scrape_persistence import PrepareScrapePersistenceInput, PrepareScrapePersistenceResult
from pipeline.prepare_stage import execute_prepare_from_acquisition
from pipeline.prepare_taxonomy_enrichment import PrepareTaxonomyEnrichmentResult
from pipeline.source_acquisition_models import SourceAcquisitionResult


def _build_manufacturer_enrichment_stub() -> dict[str, object]:
    return {
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
        "fallback_reason": "test_stub",
    }


def _build_prepare_provider_resolution_result(
    *,
    source: str,
    url: str,
    parsed: ParsedProduct,
    fetch_method: str,
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


def _build_source_acquisition_result(
    *,
    model_dir: Path,
    source: str,
    provider_id: str,
    url: str,
    parsed: ParsedProduct,
    fetch_method: str,
) -> SourceAcquisitionResult:
    return SourceAcquisitionResult(
        model_dir=model_dir,
        source=source,
        provider_id=provider_id,
        fetch=FetchResult(
            url=url,
            final_url=url,
            html="<html></html>",
            status_code=200,
            method=fetch_method,
            fallback_used=False,
        ),
        parsed=parsed,
        extracted_gallery_count=0,
        requested_gallery_photos=2,
        downloaded_gallery=[],
        gallery_warnings=[],
        gallery_files=[],
        snapshot_provenance={
            "requested_url": url,
            "detected_source": source,
            "provider_id": provider_id,
            "final_url": url,
            "status_code": 200,
            "fetch_method": fetch_method,
            "fallback_used": False,
            "response_headers": {},
            "gallery_requested_photos": 2,
            "gallery_downloaded_count": 0,
        },
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


def _build_cli(tmp_path: Path, *, model: str = "344424", url: str) -> CLIInput:
    return CLIInput(
        model=model,
        url=url,
        photos=2,
        sections=0,
        skroutz_status=1,
        boxnow=0,
        price="299",
        out=str(tmp_path),
    )


def _build_source(*, source_name: str, url: str, product_code: str, brand: str, mpn: str, name: str) -> SourceProductData:
    return SourceProductData(
        source_name=source_name,
        page_type="product",
        url=url,
        canonical_url=url,
        product_code=product_code,
        brand=brand,
        mpn=mpn,
        name=name,
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


def test_execute_prepare_stage_calls_single_result_assembly_seam_with_prepared_inputs(tmp_path: Path) -> None:
    source = _build_source(
        source_name="skroutz",
        url="https://www.skroutz.gr/s/344424/Neff-T16BT60N0.html",
        product_code="344424",
        brand="Neff",
        mpn="T16BT60N0",
        name="Neff T16BT60N0 Hob",
    )
    cli = _build_cli(tmp_path, model="344424", url=source.url)
    parsed = _build_parsed(source)
    acquisition = _build_source_acquisition_result(
        model_dir=tmp_path / cli.model,
        source="skroutz",
        provider_id="skroutz",
        url=source.url,
        parsed=parsed,
        fetch_method="fixture",
    )
    assembly_calls: list[dict[str, object]] = []

    class SchemaMatchStub:
        matched_schema_id = "schema-stub"
        score = 0.9
        warnings: list[str] = []

        def to_dict(self) -> dict[str, object]:
            return {"matched_schema_id": self.matched_schema_id, "score": self.score, "warnings": self.warnings}

    def fake_assemble_prepare_result(**kwargs) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return PrepareResultAssemblyResult(
            schema_match=SchemaMatchStub(),
            schema_candidates=[{"matched_schema_id": "schema-stub"}],
            row={"model": kwargs["cli"].model, "name": "stub"},
            normalized={"input": kwargs["cli"].to_dict(), "csv_row": {"model": kwargs["cli"].model, "name": "stub"}},
            report={"source": kwargs["source"], "warnings": [], "identity_checks": {"source": kwargs["source"]}},
        )

    result = execute_prepare_from_acquisition(
        cli,
        acquisition,
        validate_url_scope_fn=lambda _url: (source.source_name or "unknown", True, "test_scope"),
        fetcher_factory=lambda: object(),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: PrepareTaxonomyEnrichmentResult(
            taxonomy=TaxonomyResolution(
                parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
                leaf_category="Εντοιχιζόμενες Συσκευές",
                sub_category="Εστίες",
            ),
            taxonomy_candidates=[{"taxonomy_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες"}],
            manufacturer_enrichment=_build_manufacturer_enrichment_stub(),
        ),
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_persist_stub,
    )

    assert len(assembly_calls) == 1
    assembly_call = assembly_calls[0]
    assert assembly_call["cli"] is cli
    assert assembly_call["source"] == "skroutz"
    assert assembly_call["parsed"] is parsed
    assert assembly_call["taxonomy"].sub_category == "Εστίες"
    assert assembly_call["taxonomy_candidates"] == [{"taxonomy_path": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ > Εντοιχιζόμενες Συσκευές > Εστίες"}]
    assert assembly_call["manufacturer_enrichment"]["fallback_reason"] == "test_stub"
    assert assembly_call["scrape_persistence_input"].model == cli.model
    assert result["row"] == {"model": cli.model, "name": "stub"}
    assert result["normalized"] == {"input": cli.to_dict(), "csv_row": {"model": cli.model, "name": "stub"}}
    assert result["report"] == {"source": "skroutz", "warnings": [], "identity_checks": {"source": "skroutz"}}
    assert result["schema_candidates"] == [{"matched_schema_id": "schema-stub"}]


def test_execute_prepare_stage_uses_result_assembly_output_for_persistence_and_return_paths(tmp_path: Path) -> None:
    source = _build_source(
        source_name="skroutz",
        url="https://www.skroutz.gr/s/61351575/hisense-smart-tileorasi-55-4k-uhd-led-a6q-hdr-2025-55a6q.html",
        product_code="143051",
        brand="Hisense",
        mpn="55A6Q",
        name='Hisense Smart Τηλεόραση 55" 4K UHD LED A6Q HDR (2025) 55A6Q',
    )
    cli = _build_cli(tmp_path, model="143051", url=source.url)
    parsed = _build_parsed(source)
    acquisition = _build_source_acquisition_result(
        model_dir=tmp_path / cli.model,
        source="skroutz",
        provider_id="skroutz",
        url=source.url,
        parsed=parsed,
        fetch_method="fixture",
    )
    persistence_calls: list[PrepareScrapePersistenceInput] = []

    class SchemaMatchStub:
        matched_schema_id = "schema-stub"
        score = 0.4
        warnings: list[str] = []

        def to_dict(self) -> dict[str, object]:
            return {"matched_schema_id": self.matched_schema_id, "score": self.score, "warnings": self.warnings}

    def fake_assemble_prepare_result(**kwargs) -> PrepareResultAssemblyResult:
        return PrepareResultAssemblyResult(
            schema_match=SchemaMatchStub(),
            schema_candidates=[{"matched_schema_id": "schema-stub"}],
            row={"model": kwargs["cli"].model, "name": "stub"},
            normalized={"input": kwargs["cli"].to_dict(), "deterministic_product": {"mpn": "55A6Q"}},
            report={"source": kwargs["source"], "warnings": ["assembly_warning"]},
        )

    def fake_persist(persistence_input: PrepareScrapePersistenceInput) -> PrepareScrapePersistenceResult:
        persistence_calls.append(persistence_input)
        return PrepareScrapePersistenceResult(
            scrape_dir=persistence_input.scrape_dir,
            raw_html_path=persistence_input.raw_html_path,
            source_json_path=persistence_input.source_json_path,
            normalized_json_path=persistence_input.normalized_json_path,
            report_json_path=persistence_input.report_json_path,
            bescos_raw_path=persistence_input.bescos_raw_path,
        )

    result = execute_prepare_from_acquisition(
        cli,
        acquisition,
        validate_url_scope_fn=lambda _url: (source.source_name or "unknown", True, "test_scope"),
        fetcher_factory=lambda: object(),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: PrepareTaxonomyEnrichmentResult(
            taxonomy=TaxonomyResolution(
                parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
                leaf_category="Τηλεοράσεις",
                sub_category="50'' & άνω",
                cta_url="https://www.etranoulis.gr/eikona-hxos/thleoraseis/50-anw",
            ),
            taxonomy_candidates=[],
            manufacturer_enrichment=_build_manufacturer_enrichment_stub(),
        ),
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=fake_persist,
    )

    assert len(persistence_calls) == 1
    persistence_input = persistence_calls[0]
    assert persistence_input.source_payload["raw_html_path"] == str(persistence_input.raw_html_path)
    assert persistence_input.normalized_payload == {"input": cli.to_dict(), "deterministic_product": {"mpn": "55A6Q"}}
    assert persistence_input.report_payload == {"source": "skroutz", "warnings": ["assembly_warning"]}
    assert result["schema_match"].matched_schema_id == "schema-stub"
    assert result["normalized"] == persistence_input.normalized_payload
    assert result["report"] == persistence_input.report_payload
    assert result["normalized_json_path"] == persistence_input.normalized_json_path
    assert result["report_json_path"] == persistence_input.report_json_path
