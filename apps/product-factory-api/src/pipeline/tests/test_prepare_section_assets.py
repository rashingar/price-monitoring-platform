from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import pipeline.prepare_stage as prepare_stage_module
from pipeline.fetcher import FetchError
from pipeline.models import CLIInput, FetchResult, GalleryImage, ParsedProduct, SchemaMatchResult, SourceProductData, TaxonomyResolution
from pipeline.prepare_provider_resolution import PrepareProviderResolutionResult
from pipeline.prepare_result_assembly import PrepareResultAssemblyResult
from pipeline.prepare_section_assets import PrepareSectionAssetsResult
from pipeline.prepare_scrape_persistence import PrepareScrapePersistenceInput, PrepareScrapePersistenceResult
from pipeline.prepare_stage import execute_prepare_stage
from pipeline.prepare_taxonomy_enrichment import PrepareTaxonomyEnrichmentResult
from pipeline.source_acquisition_models import SourceAcquisitionResult


def _build_cli(tmp_path: Path, *, model: str = "100001", url: str, sections: int) -> CLIInput:
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
    presentation_source_html: str = "",
    presentation_source_text: str = "",
) -> SourceProductData:
    return SourceProductData(
        source_name=source_name,
        page_type="product",
        url=url,
        canonical_url=canonical_url or url,
        product_code="100001",
        brand="Brand",
        mpn="MODEL-1",
        name="Brand MODEL-1",
        presentation_source_html=presentation_source_html,
        presentation_source_text=presentation_source_text,
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
    html: str = "<html></html>",
) -> PrepareProviderResolutionResult:
    return PrepareProviderResolutionResult(
        source=source,
        provider_id=source,
        fetch=FetchResult(
            url=url,
            final_url=url,
            html=html,
            status_code=200,
            method="fixture",
            fallback_used=False,
        ),
        parsed=parsed,
    )


def _build_manufacturer_enrichment(
    *,
    presentation_applied: bool,
    fallback_reason: str,
    presentation_block_count: int = 0,
) -> dict[str, Any]:
    return {
        "applied": presentation_applied,
        "provider": "manufacturer_docs" if presentation_applied else "",
        "providers_considered": ["manufacturer_docs"] if presentation_applied else [],
        "matched_providers": ["manufacturer_docs"] if presentation_applied else [],
        "documents": [],
        "documents_discovered": 0,
        "documents_parsed": 0,
        "warnings": [],
        "section_count": 0,
        "field_count": 0,
        "hero_summary_applied": False,
        "presentation_applied": presentation_applied,
        "presentation_block_count": presentation_block_count,
        "fallback_reason": fallback_reason,
    }


def _build_taxonomy_enrichment(
    *,
    manufacturer_enrichment: dict[str, Any],
) -> PrepareTaxonomyEnrichmentResult:
    return PrepareTaxonomyEnrichmentResult(
        taxonomy=TaxonomyResolution(
            parent_category="Home",
            leaf_category="Appliances",
            sub_category="Category",
        ),
        taxonomy_candidates=[],
        manufacturer_enrichment=manufacturer_enrichment,
    )


def _build_assembly_result(**kwargs: Any) -> PrepareResultAssemblyResult:
    return PrepareResultAssemblyResult(
        schema_match=SchemaMatchResult(matched_schema_id="schema-1", score=0.9),
        schema_candidates=[{"matched_schema_id": "schema-1"}],
        row={"model": kwargs["cli"].model},
        normalized={"source": kwargs["source"]},
        report={"source": kwargs["source"], "warnings": [], "identity_checks": {"source": kwargs["source"]}},
    )


def _capture_persist(calls: list[PrepareScrapePersistenceInput]):
    def fake_persist(persistence_input: PrepareScrapePersistenceInput) -> PrepareScrapePersistenceResult:
        calls.append(persistence_input)
        return PrepareScrapePersistenceResult(
            scrape_dir=persistence_input.scrape_dir,
            raw_html_path=persistence_input.raw_html_path,
            source_json_path=persistence_input.source_json_path,
            normalized_json_path=persistence_input.normalized_json_path,
            report_json_path=persistence_input.report_json_path,
            bescos_raw_path=persistence_input.bescos_raw_path,
        )

    return fake_persist


class RecordingFetcher:
    def __init__(
        self,
        *,
        besco_download_result: tuple[list[GalleryImage], list[str], list[str]] | None = None,
        besco_error: Exception | None = None,
        rendered_section_data: dict[str, Any] | None = None,
        rendered_error: Exception | None = None,
    ) -> None:
        self.besco_download_result = besco_download_result or ([], [], [])
        self.besco_error = besco_error
        self.rendered_section_data = rendered_section_data or {"window": {}, "sections": []}
        self.rendered_error = rendered_error
        self.besco_download_calls: list[dict[str, Any]] = []
        self.rendered_calls: list[str] = []

    def download_gallery_images(self, **_kwargs: Any):
        return [], [], []

    def download_besco_images(self, **kwargs: Any):
        self.besco_download_calls.append(kwargs)
        if self.besco_error is not None:
            raise self.besco_error
        return self.besco_download_result

    def extract_skroutz_section_image_records(self, url: str):
        self.rendered_calls.append(url)
        if self.rendered_error is not None:
            raise self.rendered_error
        return self.rendered_section_data


def test_prepare_stage_can_start_from_prebuilt_source_acquisition_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _build_cli(tmp_path, url="https://www.electronet.gr/example", sections=1)
    source = _build_source(
        source_name="electronet",
        url=cli.url,
        canonical_url="https://www.electronet.gr/example/canonical",
        presentation_source_html="<section>source html</section>",
        presentation_source_text="source text",
    )
    parsed = _build_parsed(source)
    fetcher = RecordingFetcher()
    acquisition_calls: list[dict[str, Any]] = []
    assembly_calls: list[dict[str, Any]] = []
    persistence_calls: list[PrepareScrapePersistenceInput] = []

    prebuilt_acquisition = SourceAcquisitionResult(
        model_dir=tmp_path / cli.model,
        source="electronet",
        provider_id="electronet",
        fetch=FetchResult(
            url=cli.url,
            final_url=cli.url,
            html="<html>front block</html>",
            status_code=200,
            method="fixture",
            fallback_used=False,
        ),
        parsed=parsed,
        extracted_gallery_count=0,
        requested_gallery_photos=2,
        downloaded_gallery=[],
        gallery_warnings=[],
        gallery_files=[],
        snapshot_provenance={
            "requested_url": cli.url,
            "detected_source": "electronet",
            "provider_id": "electronet",
            "final_url": cli.url,
            "status_code": 200,
            "fetch_method": "fixture",
            "fallback_used": False,
            "response_headers": {},
            "gallery_requested_photos": 2,
            "gallery_downloaded_count": 0,
        },
    )

    def fake_extract_presentation_blocks(
        presentation_source_html: str,
        presentation_source_text: str,
        *,
        base_url: str,
    ) -> list[dict[str, Any]]:
        assert presentation_source_html == "<section>source html</section>"
        assert presentation_source_text == "source text"
        assert base_url == "https://www.electronet.gr/example/canonical"
        return [{"title": "Direct One", "paragraph": "Paragraph 1", "image_url": "https://cdn.example/direct-1.jpg"}]

    def fake_assemble_prepare_result(**kwargs: Any) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return _build_assembly_result(**kwargs)

    monkeypatch.setattr(prepare_stage_module, "extract_presentation_blocks", fake_extract_presentation_blocks)

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_product_path"),
        fetcher_factory=lambda: fetcher,
        execute_source_acquisition_stage_fn=lambda **kwargs: acquisition_calls.append(kwargs) or prebuilt_acquisition,
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
            manufacturer_enrichment=_build_manufacturer_enrichment(
                presentation_applied=False,
                fallback_reason="not_applicable_non_skroutz",
            )
        ),
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_capture_persist(persistence_calls),
    )

    assert acquisition_calls == [
        {
            "model": cli.model,
            "url": cli.url,
            "photos": cli.photos,
            "model_dir": tmp_path / cli.model,
            "validate_url_scope_fn": acquisition_calls[0]["validate_url_scope_fn"],
            "fetcher_factory": acquisition_calls[0]["fetcher_factory"],
            "resolve_prepare_provider_input_fn": acquisition_calls[0]["resolve_prepare_provider_input_fn"],
        }
    ]
    assert len(fetcher.besco_download_calls) == 1
    assert fetcher.besco_download_calls[0]["requested_sections"] == 1
    assert assembly_calls[0]["source"] == "electronet"
    assert assembly_calls[0]["selected_presentation_blocks"] == [
        {"title": "Direct One", "paragraph": "Paragraph 1", "image_url": "https://cdn.example/direct-1.jpg"}
    ]
    assert len(persistence_calls) == 1
    assert result["selected_presentation_blocks"] == [
        {"title": "Direct One", "paragraph": "Paragraph 1", "image_url": "https://cdn.example/direct-1.jpg"}
    ]


def test_prepare_stage_direct_section_assets_use_extracted_blocks_and_keep_besco_failures_warning_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _build_cli(tmp_path, url="https://www.electronet.gr/example", sections=3)
    source = _build_source(
        source_name="electronet",
        url=cli.url,
        canonical_url="https://www.electronet.gr/example/canonical",
        presentation_source_html="<section>source html</section>",
        presentation_source_text="source text",
    )
    parsed = _build_parsed(source)
    extracted_blocks = [
        {"title": "Direct One", "paragraph": "Paragraph 1", "image_url": "https://cdn.example/direct-1.jpg"},
        {"title": "Direct Two", "paragraph": "Paragraph 2", "image_url": ""},
        {"title": "Direct Three", "paragraph": "Paragraph 3", "image_url": "https://cdn.example/direct-3.jpg"},
        {"title": "Direct Four", "paragraph": "Paragraph 4", "image_url": "https://cdn.example/direct-4.jpg"},
    ]
    extract_calls: list[dict[str, Any]] = []
    assembly_calls: list[dict[str, Any]] = []
    persistence_calls: list[PrepareScrapePersistenceInput] = []
    fetcher = RecordingFetcher(besco_error=FetchError("direct-besco-download-failed"))

    def fake_extract_presentation_blocks(
        presentation_source_html: str,
        presentation_source_text: str,
        *,
        base_url: str,
    ) -> list[dict[str, Any]]:
        extract_calls.append(
            {
                "presentation_source_html": presentation_source_html,
                "presentation_source_text": presentation_source_text,
                "base_url": base_url,
            }
        )
        return extracted_blocks

    def fake_assemble_prepare_result(**kwargs: Any) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return _build_assembly_result(**kwargs)

    monkeypatch.setattr(prepare_stage_module, "extract_presentation_blocks", fake_extract_presentation_blocks)

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_product_path"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="electronet",
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
            manufacturer_enrichment=_build_manufacturer_enrichment(
                presentation_applied=False,
                fallback_reason="not_applicable_non_skroutz",
            )
        ),
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_capture_persist(persistence_calls),
    )

    assert extract_calls == [
        {
            "presentation_source_html": "<section>source html</section>",
            "presentation_source_text": "source text",
            "base_url": "https://www.electronet.gr/example/canonical",
        }
    ]
    assert len(fetcher.besco_download_calls) == 1
    assert fetcher.besco_download_calls[0]["requested_sections"] == 3
    assert fetcher.besco_download_calls[0]["output_dir"] == tmp_path / cli.model
    assert fetcher.besco_download_calls[0]["images"] == [
        GalleryImage(url="https://cdn.example/direct-1.jpg", alt="Direct One", position=1),
        GalleryImage(url="https://cdn.example/direct-3.jpg", alt="Direct Three", position=3),
    ]

    assert len(assembly_calls) == 1
    assert assembly_calls[0]["selected_presentation_blocks"] == extracted_blocks[:3]
    assert assembly_calls[0]["section_warnings"] == []
    assert assembly_calls[0]["section_image_candidates"] == []
    assert assembly_calls[0]["section_image_urls_resolved"] == []
    assert assembly_calls[0]["section_extraction_window"] == {
        "candidate_count": 0,
        "duplicate_signatures_skipped": 0,
        "selected_container_index": None,
        "start_anchor": "",
        "stop_anchor": "",
        "title_signature": [],
    }
    assert assembly_calls[0]["selected_besco_images"] == [
        GalleryImage(url="https://cdn.example/direct-1.jpg", alt="Direct One", position=1),
        GalleryImage(url="https://cdn.example/direct-3.jpg", alt="Direct Three", position=3),
    ]
    assert assembly_calls[0]["downloaded_besco"] == []
    assert assembly_calls[0]["besco_warnings"] == ["besco_download_failed:direct-besco-download-failed"]
    assert assembly_calls[0]["besco_filenames_by_section"] == {}
    assert assembly_calls[0]["sections_artifact_payload"] is None

    assert len(persistence_calls) == 1
    assert persistence_calls[0].bescos_raw_payload is None
    assert result["selected_presentation_blocks"] == extracted_blocks[:3]
    assert result["downloaded_besco"] == []
    assert result["besco_filenames_by_section"] == {}


def test_prepare_stage_skroutz_prefers_manufacturer_blocks_and_preserves_manufacturer_section_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _build_cli(tmp_path, model="143051", url="https://www.skroutz.gr/s/143051/example.html", sections=2)
    source = _build_source(
        source_name="skroutz",
        url=cli.url,
        presentation_source_html="<section>manufacturer presentation</section>",
        presentation_source_text="manufacturer text",
    )
    parsed = _build_parsed(source)
    manufacturer_blocks = [
        {"title": "Manufacturer One", "paragraph": "Body 1", "image_url": "https://cdn.example/manufacturer-1.jpg"},
        {"title": "Manufacturer Two", "paragraph": "Body 2", "image_url": "https://cdn.example/manufacturer-2.jpg"},
        {"title": "Manufacturer Three", "paragraph": "Body 3", "image_url": "https://cdn.example/manufacturer-3.jpg"},
    ]
    downloaded_besco = [
        GalleryImage(
            url="https://cdn.example/manufacturer-1.jpg",
            alt="Manufacturer One",
            position=1,
            local_filename="besco1.jpg",
            local_path=str(tmp_path / cli.model / "bescos" / "besco1.jpg"),
            downloaded=True,
        ),
        GalleryImage(
            url="https://cdn.example/manufacturer-2.jpg",
            alt="Manufacturer Two",
            position=2,
            local_filename="besco2.jpg",
            local_path=str(tmp_path / cli.model / "bescos" / "besco2.jpg"),
            downloaded=True,
        ),
    ]
    resolve_calls: list[dict[str, Any]] = []
    assembly_calls: list[dict[str, Any]] = []
    persistence_calls: list[PrepareScrapePersistenceInput] = []
    fetcher = RecordingFetcher()
    expected_window = {
        "candidate_count": 3,
        "duplicate_signatures_skipped": 0,
        "selected_container_index": "manufacturer_html",
        "start_anchor": "manufacturer_presentation",
        "stop_anchor": "",
        "title_signature": ["Manufacturer One", "Manufacturer Two"],
    }
    expected_payload = {
        "source": "manufacturer",
        "requested_sections": 2,
        "window": expected_window,
        "sections": [
            {
                "position": 1,
                "title": "Manufacturer One",
                "body": "Body 1",
                "image_candidates": ["https://cdn.example/manufacturer-1.jpg"],
                "resolved_image_url": "https://cdn.example/manufacturer-1.jpg",
                "target_filename": "besco1.jpg",
            },
            {
                "position": 2,
                "title": "Manufacturer Two",
                "body": "Body 2",
                "image_candidates": ["https://cdn.example/manufacturer-2.jpg"],
                "resolved_image_url": "https://cdn.example/manufacturer-2.jpg",
                "target_filename": "besco2.jpg",
            },
        ],
    }

    def fake_resolve_skroutz_section_assets(**kwargs: Any) -> PrepareSectionAssetsResult:
        resolve_calls.append(kwargs)
        return PrepareSectionAssetsResult(
            selected_presentation_blocks=manufacturer_blocks[:2],
            selected_besco_images=[
                GalleryImage(url="https://cdn.example/manufacturer-1.jpg", alt="Manufacturer One", position=1),
                GalleryImage(url="https://cdn.example/manufacturer-2.jpg", alt="Manufacturer Two", position=2),
            ],
            downloaded_besco=downloaded_besco,
            besco_warnings=[],
            besco_files=[str(tmp_path / cli.model / "bescos" / "besco1.jpg"), str(tmp_path / cli.model / "bescos" / "besco2.jpg")],
            besco_filenames_by_section={1: "besco1.jpg", 2: "besco2.jpg"},
            section_warnings=[],
            section_image_candidates=[
                {
                    "position": 1,
                    "title": "Manufacturer One",
                    "candidates": ["https://cdn.example/manufacturer-1.jpg"],
                },
                {
                    "position": 2,
                    "title": "Manufacturer Two",
                    "candidates": ["https://cdn.example/manufacturer-2.jpg"],
                },
            ],
            section_image_urls_resolved=[
                {
                    "position": 1,
                    "title": "Manufacturer One",
                    "url": "https://cdn.example/manufacturer-1.jpg",
                },
                {
                    "position": 2,
                    "title": "Manufacturer Two",
                    "url": "https://cdn.example/manufacturer-2.jpg",
                },
            ],
            section_extraction_window=expected_window,
            sections_artifact_payload=expected_payload,
            presentation_source_html_override=None,
        )

    def fake_assemble_prepare_result(**kwargs: Any) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return _build_assembly_result(**kwargs)

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
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
            manufacturer_enrichment=_build_manufacturer_enrichment(
                presentation_applied=True,
                presentation_block_count=3,
                fallback_reason="",
            )
        ),
        resolve_skroutz_section_assets_fn=fake_resolve_skroutz_section_assets,
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_capture_persist(persistence_calls),
    )

    assert resolve_calls == [
        {
            "requested_sections": 2,
            "fetch_html": "<html></html>",
            "final_url": cli.url,
            "canonical_url": cli.url,
            "url": cli.url,
            "presentation_source_html": "<section>manufacturer presentation</section>",
            "presentation_source_text": "manufacturer text",
            "manufacturer_enrichment": _build_manufacturer_enrichment(
                presentation_applied=True,
                presentation_block_count=3,
                fallback_reason="",
            ),
            "fetcher": fetcher,
            "output_dir": tmp_path / cli.model,
        }
    ]
    assert fetcher.rendered_calls == []
    assert fetcher.besco_download_calls == []

    assert len(assembly_calls) == 1
    assert assembly_calls[0]["selected_presentation_blocks"] == manufacturer_blocks[:2]
    assert assembly_calls[0]["section_warnings"] == []
    assert assembly_calls[0]["section_image_candidates"] == [
        {
            "position": 1,
            "title": "Manufacturer One",
            "candidates": ["https://cdn.example/manufacturer-1.jpg"],
        },
        {
            "position": 2,
            "title": "Manufacturer Two",
            "candidates": ["https://cdn.example/manufacturer-2.jpg"],
        },
    ]
    assert assembly_calls[0]["section_image_urls_resolved"] == [
        {
            "position": 1,
            "title": "Manufacturer One",
            "url": "https://cdn.example/manufacturer-1.jpg",
        },
        {
            "position": 2,
            "title": "Manufacturer Two",
            "url": "https://cdn.example/manufacturer-2.jpg",
        },
    ]
    assert assembly_calls[0]["section_extraction_window"] == expected_window
    assert assembly_calls[0]["selected_besco_images"] == [
        GalleryImage(url="https://cdn.example/manufacturer-1.jpg", alt="Manufacturer One", position=1),
        GalleryImage(url="https://cdn.example/manufacturer-2.jpg", alt="Manufacturer Two", position=2),
    ]
    assert assembly_calls[0]["downloaded_besco"] == downloaded_besco
    assert assembly_calls[0]["besco_filenames_by_section"] == {1: "besco1.jpg", 2: "besco2.jpg"}
    assert assembly_calls[0]["sections_artifact_payload"] == expected_payload

    assert len(persistence_calls) == 1
    assert persistence_calls[0].bescos_raw_payload == expected_payload
    assert result["selected_presentation_blocks"] == manufacturer_blocks[:2]
    assert result["downloaded_besco"] == downloaded_besco
    assert result["besco_filenames_by_section"] == {1: "besco1.jpg", 2: "besco2.jpg"}


def test_prepare_stage_skroutz_fallback_uses_section_window_and_rendered_records_and_preserves_bescos_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _build_cli(tmp_path, model="143481", url="https://www.skroutz.gr/s/143481/example.html", sections=2)
    source = _build_source(source_name="skroutz", url=cli.url)
    parsed = _build_parsed(source)
    downloaded_besco = [
        GalleryImage(
            url="https://cdn.example/alpha-resolved.jpg",
            alt="Alpha",
            position=1,
            local_filename="besco1.jpg",
            local_path=str(tmp_path / cli.model / "bescos" / "besco1.jpg"),
            downloaded=True,
        ),
        GalleryImage(
            url="https://cdn.example/gamma-resolved.jpg",
            alt="Gamma",
            position=2,
            local_filename="besco2.jpg",
            local_path=str(tmp_path / cli.model / "bescos" / "besco2.jpg"),
            downloaded=True,
        ),
    ]
    assembly_calls: list[dict[str, Any]] = []
    persistence_calls: list[PrepareScrapePersistenceInput] = []
    resolve_calls: list[dict[str, Any]] = []
    fetcher = RecordingFetcher()
    expected_blocks = [
        {
            "title": "Alpha",
            "paragraph": "Alpha body",
            "image_candidates": ["https://cdn.example/alpha-candidate-1.jpg", "https://cdn.example/alpha-candidate-2.jpg"],
            "image_url": "https://cdn.example/alpha-resolved.jpg",
        },
        {
            "title": "Gamma",
            "paragraph": "Gamma body",
            "image_candidates": ["https://cdn.example/gamma-candidate.jpg"],
            "image_url": "https://cdn.example/gamma-resolved.jpg",
        },
    ]
    expected_window = {
        "candidate_count": 5,
        "duplicate_signatures_skipped": 1,
        "selected_container_index": "rendered_dom",
        "start_anchor": "Περιγραφή",
        "stop_anchor": "Κατασκευαστής",
        "title_signature": ["Alpha", "Beta", "Gamma"],
        "rendered_container_count": 2,
    }
    expected_payload = {
        "source": "skroutz",
        "requested_sections": 2,
        "window": expected_window,
        "sections": [
            {
                "position": 1,
                "title": "Alpha",
                "body": "Alpha body",
                "image_candidates": ["https://cdn.example/alpha-candidate-1.jpg", "https://cdn.example/alpha-candidate-2.jpg"],
                "resolved_image_url": "https://cdn.example/alpha-resolved.jpg",
                "target_filename": "besco1.jpg",
            },
            {
                "position": 2,
                "title": "Gamma",
                "body": "Gamma body",
                "image_candidates": ["https://cdn.example/gamma-candidate.jpg"],
                "resolved_image_url": "https://cdn.example/gamma-resolved.jpg",
                "target_filename": "besco2.jpg",
            },
        ],
    }

    def fake_resolve_skroutz_section_assets(**kwargs: Any) -> PrepareSectionAssetsResult:
        resolve_calls.append(kwargs)
        return PrepareSectionAssetsResult(
            selected_presentation_blocks=expected_blocks,
            selected_besco_images=[
                GalleryImage(url="https://cdn.example/alpha-resolved.jpg", alt="Alpha", position=1),
                GalleryImage(url="https://cdn.example/gamma-resolved.jpg", alt="Gamma", position=2),
            ],
            downloaded_besco=downloaded_besco,
            besco_warnings=[],
            besco_files=[str(tmp_path / cli.model / "bescos" / "besco1.jpg"), str(tmp_path / cli.model / "bescos" / "besco2.jpg")],
            besco_filenames_by_section={1: "besco1.jpg", 2: "besco2.jpg"},
            section_warnings=["skroutz_window_warning"],
            section_image_candidates=[
                {
                    "position": 1,
                    "title": "Alpha",
                    "candidates": ["https://cdn.example/alpha-candidate-1.jpg", "https://cdn.example/alpha-candidate-2.jpg"],
                },
                {
                    "position": 2,
                    "title": "Gamma",
                    "candidates": ["https://cdn.example/gamma-candidate.jpg"],
                },
            ],
            section_image_urls_resolved=[
                {
                    "position": 1,
                    "title": "Alpha",
                    "url": "https://cdn.example/alpha-resolved.jpg",
                },
                {
                    "position": 2,
                    "title": "Gamma",
                    "url": "https://cdn.example/gamma-resolved.jpg",
                },
            ],
            section_extraction_window=expected_window,
            sections_artifact_payload=expected_payload,
            presentation_source_html_override="rebuilt::Alpha|Gamma",
        )

    def fake_assemble_prepare_result(**kwargs: Any) -> PrepareResultAssemblyResult:
        assembly_calls.append(kwargs)
        return _build_assembly_result(**kwargs)

    result = execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="skroutz",
            url=cli_arg.url,
            parsed=parsed,
            html="<html>skroutz page</html>",
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
            manufacturer_enrichment=_build_manufacturer_enrichment(
                presentation_applied=False,
                presentation_block_count=0,
                fallback_reason="provider_not_matched",
            )
        ),
        resolve_skroutz_section_assets_fn=fake_resolve_skroutz_section_assets,
        assemble_prepare_result_fn=fake_assemble_prepare_result,
        persist_prepare_scrape_artifacts_fn=_capture_persist(persistence_calls),
    )

    assert resolve_calls == [
        {
            "requested_sections": 2,
            "fetch_html": "<html>skroutz page</html>",
            "final_url": cli.url,
            "canonical_url": cli.url,
            "url": cli.url,
            "presentation_source_html": "",
            "presentation_source_text": "",
            "manufacturer_enrichment": _build_manufacturer_enrichment(
                presentation_applied=False,
                presentation_block_count=0,
                fallback_reason="provider_not_matched",
            ),
            "fetcher": fetcher,
            "output_dir": tmp_path / cli.model,
        }
    ]
    assert fetcher.rendered_calls == []
    assert fetcher.besco_download_calls == []

    assert len(assembly_calls) == 1
    assert assembly_calls[0]["selected_presentation_blocks"] == expected_blocks
    assert assembly_calls[0]["section_warnings"] == ["skroutz_window_warning"]
    assert assembly_calls[0]["section_image_candidates"] == [
        {
            "position": 1,
            "title": "Alpha",
            "candidates": ["https://cdn.example/alpha-candidate-1.jpg", "https://cdn.example/alpha-candidate-2.jpg"],
        },
        {
            "position": 2,
            "title": "Gamma",
            "candidates": ["https://cdn.example/gamma-candidate.jpg"],
        },
    ]
    assert assembly_calls[0]["section_image_urls_resolved"] == [
        {
            "position": 1,
            "title": "Alpha",
            "url": "https://cdn.example/alpha-resolved.jpg",
        },
        {
            "position": 2,
            "title": "Gamma",
            "url": "https://cdn.example/gamma-resolved.jpg",
        },
    ]
    assert assembly_calls[0]["section_extraction_window"] == expected_window
    assert assembly_calls[0]["selected_besco_images"] == [
        GalleryImage(url="https://cdn.example/alpha-resolved.jpg", alt="Alpha", position=1),
        GalleryImage(url="https://cdn.example/gamma-resolved.jpg", alt="Gamma", position=2),
    ]
    assert assembly_calls[0]["downloaded_besco"] == downloaded_besco
    assert assembly_calls[0]["besco_filenames_by_section"] == {1: "besco1.jpg", 2: "besco2.jpg"}
    assert assembly_calls[0]["sections_artifact_payload"] == expected_payload

    assert len(persistence_calls) == 1
    assert persistence_calls[0].bescos_raw_payload == expected_payload
    assert parsed.source.presentation_source_html == "rebuilt::Alpha|Gamma"
    assert result["selected_presentation_blocks"] == expected_blocks
    assert result["downloaded_besco"] == downloaded_besco
    assert result["besco_filenames_by_section"] == {1: "besco1.jpg", 2: "besco2.jpg"}


def test_prepare_stage_skroutz_fallback_fails_when_rendered_sections_are_insufficient(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _build_cli(tmp_path, model="200001", url="https://www.skroutz.gr/s/200001/example.html", sections=2)
    parsed = _build_parsed(_build_source(source_name="skroutz", url=cli.url))
    fetcher = RecordingFetcher()
    resolve_calls: list[dict[str, Any]] = []

    def fake_resolve_skroutz_section_assets(**kwargs: Any) -> PrepareSectionAssetsResult:
        resolve_calls.append(kwargs)
        raise RuntimeError("Skroutz rendered section extraction failed: expected 2 image records, found 1")

    with pytest.raises(RuntimeError) as excinfo:
        execute_prepare_stage(
            cli,
            model_dir=tmp_path / cli.model,
            validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
            fetcher_factory=lambda: fetcher,
            resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
                source="skroutz",
                url=cli_arg.url,
                parsed=parsed,
            ),
            resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
                manufacturer_enrichment=_build_manufacturer_enrichment(
                    presentation_applied=False,
                    presentation_block_count=0,
                    fallback_reason="provider_not_matched",
                )
            ),
            resolve_skroutz_section_assets_fn=fake_resolve_skroutz_section_assets,
            assemble_prepare_result_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("result assembly should not run")),
            persist_prepare_scrape_artifacts_fn=lambda _persistence_input: (_ for _ in ()).throw(
                AssertionError("persistence should not run")
            ),
        )

    assert str(excinfo.value) == "Skroutz rendered section extraction failed: expected 2 image records, found 1"
    assert len(resolve_calls) == 1
    assert fetcher.besco_download_calls == []


def test_prepare_stage_skroutz_fallback_fails_on_title_order_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _build_cli(tmp_path, model="200002", url="https://www.skroutz.gr/s/200002/example.html", sections=2)
    parsed = _build_parsed(_build_source(source_name="skroutz", url=cli.url))
    fetcher = RecordingFetcher()
    resolve_calls: list[dict[str, Any]] = []

    def fake_resolve_skroutz_section_assets(**kwargs: Any) -> PrepareSectionAssetsResult:
        resolve_calls.append(kwargs)
        raise RuntimeError("Skroutz section title order mismatch between rendered DOM and parsed description")

    with pytest.raises(RuntimeError) as excinfo:
        execute_prepare_stage(
            cli,
            model_dir=tmp_path / cli.model,
            validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
            fetcher_factory=lambda: fetcher,
            resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
                source="skroutz",
                url=cli_arg.url,
                parsed=parsed,
            ),
            resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
                manufacturer_enrichment=_build_manufacturer_enrichment(
                    presentation_applied=False,
                    presentation_block_count=0,
                    fallback_reason="provider_not_matched",
                )
            ),
            resolve_skroutz_section_assets_fn=fake_resolve_skroutz_section_assets,
            assemble_prepare_result_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("result assembly should not run")),
            persist_prepare_scrape_artifacts_fn=lambda _persistence_input: (_ for _ in ()).throw(
                AssertionError("persistence should not run")
            ),
        )

    assert str(excinfo.value) == "Skroutz section title order mismatch between rendered DOM and parsed description"
    assert len(resolve_calls) == 1
    assert fetcher.besco_download_calls == []


def test_prepare_stage_skroutz_manufacturer_path_keeps_besco_download_incomplete_as_strict_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _build_cli(tmp_path, model="200003", url="https://www.skroutz.gr/s/200003/example.html", sections=2)
    parsed = _build_parsed(
        _build_source(
            source_name="skroutz",
            url=cli.url,
            presentation_source_html="<section>manufacturer presentation</section>",
            presentation_source_text="manufacturer text",
        )
    )
    fetcher = RecordingFetcher()
    resolve_calls: list[dict[str, Any]] = []

    def fake_resolve_skroutz_section_assets(**kwargs: Any) -> PrepareSectionAssetsResult:
        resolve_calls.append(kwargs)
        raise RuntimeError("Skroutz besco image download incomplete: expected 2, downloaded 1")

    with pytest.raises(RuntimeError) as excinfo:
        execute_prepare_stage(
            cli,
            model_dir=tmp_path / cli.model,
            validate_url_scope_fn=lambda _url: ("skroutz", True, "skroutz_product_path"),
            fetcher_factory=lambda: fetcher,
            resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
                source="skroutz",
                url=cli_arg.url,
                parsed=parsed,
            ),
            resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
                manufacturer_enrichment=_build_manufacturer_enrichment(
                    presentation_applied=True,
                    presentation_block_count=2,
                    fallback_reason="",
                )
            ),
            resolve_skroutz_section_assets_fn=fake_resolve_skroutz_section_assets,
            assemble_prepare_result_fn=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("result assembly should not run")),
            persist_prepare_scrape_artifacts_fn=lambda _persistence_input: (_ for _ in ()).throw(
                AssertionError("persistence should not run")
            ),
        )

    assert str(excinfo.value) == "Skroutz besco image download incomplete: expected 2, downloaded 1"
    assert len(resolve_calls) == 1
    assert fetcher.besco_download_calls == []


def test_prepare_stage_injects_energy_label_into_gallery_slot_two(tmp_path: Path) -> None:
    cli = _build_cli(tmp_path, url="https://www.electronet.gr/example", sections=0)
    source = _build_source(source_name="electronet", url=cli.url)
    source.gallery_images = [
        GalleryImage(url="https://cdn.example/main.jpg", alt="main", position=1),
        GalleryImage(url="https://cdn.example/second.jpg", alt="second", position=2),
        GalleryImage(url="https://cdn.example/third.jpg", alt="third", position=3),
    ]
    source.energy_label_asset_url = "https://eprel.ec.europa.eu/labels/example.png"
    parsed = _build_parsed(source)
    persistence_calls: list[PrepareScrapePersistenceInput] = []

    class GalleryRecordingFetcher(RecordingFetcher):
        def __init__(self) -> None:
            super().__init__()
            self.gallery_download_calls: list[dict[str, Any]] = []

        def download_gallery_images(self, **kwargs: Any):
            self.gallery_download_calls.append(kwargs)
            return [], [], []

    fetcher = GalleryRecordingFetcher()

    execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_product_path"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="electronet",
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
            manufacturer_enrichment=_build_manufacturer_enrichment(
                presentation_applied=False,
                fallback_reason="not_applicable_non_skroutz",
            )
        ),
        assemble_prepare_result_fn=_build_assembly_result,
        persist_prepare_scrape_artifacts_fn=_capture_persist(persistence_calls),
    )

    assert len(fetcher.gallery_download_calls) == 1
    assert fetcher.gallery_download_calls[0]["requested_photos"] == 3
    assert [item.position for item in fetcher.gallery_download_calls[0]["images"]] == [1, 2, 3, 4]
    assert [item.url for item in fetcher.gallery_download_calls[0]["images"]] == [
        "https://cdn.example/main.jpg",
        "https://eprel.ec.europa.eu/labels/example.png",
        "https://cdn.example/second.jpg",
        "https://cdn.example/third.jpg",
    ]


def test_prepare_stage_adds_energy_label_on_top_of_requested_photo_count(tmp_path: Path) -> None:
    cli = _build_cli(tmp_path, url="https://www.electronet.gr/example", sections=0)
    source = _build_source(source_name="electronet", url=cli.url)
    source.gallery_images = [
        GalleryImage(url="https://cdn.example/main.jpg", alt="main", position=1),
        GalleryImage(url="https://cdn.example/second.jpg", alt="second", position=2),
        GalleryImage(url="https://cdn.example/third.jpg", alt="third", position=3),
    ]
    source.energy_label_asset_url = "https://eprel.ec.europa.eu/labels/example.png"
    parsed = _build_parsed(source)
    persistence_calls: list[PrepareScrapePersistenceInput] = []

    class GalleryRecordingFetcher(RecordingFetcher):
        def __init__(self) -> None:
            super().__init__()
            self.gallery_download_calls: list[dict[str, Any]] = []

        def download_gallery_images(self, **kwargs: Any):
            self.gallery_download_calls.append(kwargs)
            return [], [], []

    fetcher = GalleryRecordingFetcher()

    execute_prepare_stage(
        cli,
        model_dir=tmp_path / cli.model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_product_path"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli_arg, **_kwargs: _build_prepare_provider_resolution_result(
            source="electronet",
            url=cli_arg.url,
            parsed=parsed,
        ),
        resolve_prepare_taxonomy_enrichment_fn=lambda **_kwargs: _build_taxonomy_enrichment(
            manufacturer_enrichment=_build_manufacturer_enrichment(
                presentation_applied=False,
                fallback_reason="not_applicable_non_skroutz",
            )
        ),
        assemble_prepare_result_fn=_build_assembly_result,
        persist_prepare_scrape_artifacts_fn=_capture_persist(persistence_calls),
    )

    assert len(fetcher.gallery_download_calls) == 1
    assert fetcher.gallery_download_calls[0]["requested_photos"] == 3
