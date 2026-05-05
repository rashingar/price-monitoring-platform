from __future__ import annotations

from pathlib import Path

from pipeline.models import CLIInput, FetchResult, ParsedProduct, SourceProductData, SpecItem, SpecSection, TaxonomyResolution
from pipeline.prepare_result_assembly import PrepareResultAssemblyResult, assemble_prepare_result
from pipeline.prepare_scrape_persistence import PrepareScrapePersistenceInput
from pipeline.repo_paths import SCHEMA_LIBRARY_PATH
from pipeline.schema_matcher import SchemaMatcher
from pipeline.utils import read_json


def _schema_id_for_source_file(source_file: str) -> str:
    payload = read_json(SCHEMA_LIBRARY_PATH)
    for schema in payload.get("schemas", []):
        if source_file in schema.get("source_files", []):
            schema_id = str(schema.get("schema_id", "")).strip()
            if schema_id:
                return schema_id
    raise AssertionError(f"Schema id not found for source file {source_file!r}.")


TV_TEMPLATE_SCHEMA_ID = _schema_id_for_source_file("tileoraseis.json")
BUILT_IN_HOB_SCHEMA_ID = _schema_id_for_source_file("esties.json")


def _build_cli(tmp_path: Path, *, model: str, url: str) -> CLIInput:
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


def _build_fetch(url: str) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        html="<html></html>",
        status_code=200,
        method="fixture",
        fallback_used=False,
    )


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


def _build_persistence_input(tmp_path: Path, *, model: str) -> PrepareScrapePersistenceInput:
    return PrepareScrapePersistenceInput(
        model=model,
        scrape_dir=tmp_path / model,
        raw_html="<html></html>",
        source_payload={},
        normalized_payload={},
        report_payload={},
    )


def _build_tv_taxonomy() -> TaxonomyResolution:
    return TaxonomyResolution(
        parent_category="ΕΙΚΟΝΑ & ΗΧΟΣ",
        leaf_category="Τηλεοράσεις",
        sub_category="50'' & άνω",
        taxonomy_path="ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω",
        cta_url="https://www.etranoulis.gr/eikona-hxos/thleoraseis/50-anw",
    )


def _build_hob_taxonomy() -> TaxonomyResolution:
    return TaxonomyResolution(
        parent_category="ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
        leaf_category="Εντοιχιζόμενες Συσκευές",
        sub_category="Εστίες",
    )


def _build_skroutz_tv_source() -> SourceProductData:
    return SourceProductData(
        source_name="skroutz",
        page_type="product",
        url="https://www.skroutz.gr/s/61351575/hisense-smart-tileorasi-55-4k-uhd-led-a6q-hdr-2025-55a6q.html",
        canonical_url="https://www.skroutz.gr/s/61351575/hisense-smart-tileorasi-55-4k-uhd-led-a6q-hdr-2025-55a6q.html",
        product_code="143051",
        brand="Hisense",
        mpn="55A6Q",
        name='Hisense Smart Τηλεόραση 55" 4K UHD LED A6Q HDR (2025) 55A6Q',
        hero_summary=(
            "Το AI 4K Upscaler της Hisense αναβαθμίζει το περιεχόμενο σε 4K. "
            "Το Game Mode PLUS και το Game Bar βελτιώνουν το gaming."
        ),
        presentation_source_text=(
            "Το AI 4K Upscaler αναβαθμίζει την εικόνα. "
            "Το Game Mode PLUS και το Game Bar προσθέτουν έλεγχο."
        ),
        taxonomy_tv_inches=55,
        key_specs=[
            SpecItem(label="Διαγώνιος", value='55 "'),
            SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
            SpecItem(label="Ρυθμός Ανανέωσης", value="50/60 Hz"),
            SpecItem(label="Τύπος Panel", value="Direct LED"),
            SpecItem(label="Τύποι HDR", value="HDR10, HDR10+, Dolby Vision, HLG"),
            SpecItem(label="Κανάλια", value="2.1"),
            SpecItem(label="Ισχύς", value="20 W"),
        ],
        spec_sections=[
            SpecSection(
                section="Εικόνα",
                items=[
                    SpecItem(label="Διαγώνιος", value='55 "'),
                    SpecItem(label="Ευκρίνεια", value="4K Ultra HD"),
                    SpecItem(label="Ρυθμός Ανανέωσης", value="50/60 Hz"),
                    SpecItem(label="Τύπος Panel", value="Direct LED"),
                    SpecItem(label="Τύποι HDR", value="HDR10, HDR10+, Dolby Vision, HLG"),
                ],
            ),
            SpecSection(
                section="Ήχος",
                items=[
                    SpecItem(label="Κανάλια", value="2.1"),
                    SpecItem(label="Ισχύς", value="20 W"),
                    SpecItem(label="Πρότυπα Ήχου", value="DTS Virtual: X"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[SpecItem(label="Δέκτης", value="DVB-C, DVB-S2, DVB-T2")],
            ),
            SpecSection(
                section="Ενσύρματες Συνδέσεις",
                items=[
                    SpecItem(label="Πλήθος USB", value="2"),
                    SpecItem(label="Σύνολο Θυρών HDMI", value="3"),
                ],
            ),
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(label="Βάρος", value="10,9 kg"),
                    SpecItem(label="VESA Mount", value="400 x 200 mm"),
                ],
            ),
            SpecSection(
                section="Ενεργειακή Ετικέτα",
                items=[SpecItem(label="Ενεργειακή Κλάση", value="E")],
            ),
            SpecSection(
                section="Διαστάσεις (με Βάση)",
                items=[
                    SpecItem(label="Πλάτος", value="1234 mm"),
                    SpecItem(label="Ύψος", value="751 mm"),
                    SpecItem(label="Πάχος", value="298 mm"),
                ],
            ),
        ],
    )


def _build_skroutz_hob_source() -> SourceProductData:
    return SourceProductData(
        source_name="skroutz",
        page_type="product",
        url="https://www.skroutz.gr/s/344424/Neff-T16BT60N0.html",
        canonical_url="https://www.skroutz.gr/s/344424/Neff-T16BT60N0.html",
        product_code="344424",
        brand="Neff",
        mpn="T16BT60N0",
        name="Neff T16BT60N0 Hob",
        spec_sections=[
            SpecSection(
                section="Γενικά",
                items=[
                    SpecItem(label="Τύπος", value="Κεραμική"),
                    SpecItem(label="Αριθμός Εστιών", value="4"),
                ],
            ),
            SpecSection(
                section="Δυνατότητες & Λειτουργίες",
                items=[SpecItem(label="Χρονοδιακόπτης", value="Ναι")],
            ),
            SpecSection(
                section="Διαστάσεις Συσκευής",
                items=[SpecItem(label="Ύψος", value="4,8 cm")],
            ),
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section="Τεχνικά στοιχεία",
                items=[
                    SpecItem(label="Τύπος εγκατάστασης", value="Εντοιχιζόμενη συσκευή"),
                    SpecItem(label="Τύπος λειτουργίας", value="Ηλεκτρική"),
                    SpecItem(label="Βασικό υλικό επιφανειών", value="Υαλοκεραμική"),
                    SpecItem(label="Συνολικός αριθμός ζωνών που μπορούν να χρησιμοποιηθούν ταυτόχρονα", value="4"),
                ],
            ),
            SpecSection(
                section="Γενικά χαρακτηριστικά",
                items=[SpecItem(label="Συνολική ισχύς", value="6.3 kW")],
            ),
        ],
    )


def _build_no_specs_source() -> SourceProductData:
    return SourceProductData(
        source_name="electronet",
        page_type="product",
        url="https://www.electronet.gr/no-spec-product",
        canonical_url="https://www.electronet.gr/no-spec-product",
        product_code="000001",
        brand="LG",
        mpn="NO-SPECS-1",
        name="LG NO-SPECS-1",
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


def test_assemble_prepare_result_passes_effective_sections_and_schema_preferences(tmp_path: Path) -> None:
    cli = _build_cli(tmp_path, model="344424", url="https://www.skroutz.gr/s/344424/Neff-T16BT60N0.html")
    source = _build_skroutz_hob_source()
    parsed = _build_parsed(source)
    matcher_calls: list[dict[str, object]] = []

    class RecordingSchemaMatcher:
        def __init__(self, *args, **kwargs) -> None:
            self._matcher = SchemaMatcher(*args, **kwargs)
            self.known_section_titles = self._matcher.known_section_titles

        def match(
            self,
            spec_sections,
            taxonomy_sub_category=None,
            preferred_source_files=None,
            taxonomy_path=None,
            taxonomy_parent_category=None,
            taxonomy_leaf_category=None,
        ):
            matcher_calls.append(
                {
                    "section_titles": [section.section for section in spec_sections],
                    "taxonomy_sub_category": taxonomy_sub_category,
                    "preferred_source_files": list(preferred_source_files or []),
                    "taxonomy_path": taxonomy_path,
                    "taxonomy_parent_category": taxonomy_parent_category,
                    "taxonomy_leaf_category": taxonomy_leaf_category,
                }
            )
            return self._matcher.match(
                spec_sections,
                taxonomy_sub_category,
                preferred_source_files,
                taxonomy_path=taxonomy_path,
                taxonomy_parent_category=taxonomy_parent_category,
                taxonomy_leaf_category=taxonomy_leaf_category,
            )

    result = assemble_prepare_result(
        cli=cli,
        source="skroutz",
        fetch=_build_fetch(cli.url),
        parsed=parsed,
        taxonomy=_build_hob_taxonomy(),
        taxonomy_candidates=[],
        manufacturer_enrichment=_build_manufacturer_enrichment_stub(),
        extracted_gallery_count=0,
        downloaded_gallery=[],
        gallery_warnings=[],
        gallery_files=[],
        selected_presentation_blocks=[],
        section_warnings=[],
        section_image_candidates=[],
        section_image_urls_resolved=[],
        section_extraction_window={"candidate_count": 0, "duplicate_signatures_skipped": 0, "selected_container_index": None, "start_anchor": "", "stop_anchor": "", "title_signature": []},
        selected_besco_images=[],
        downloaded_besco=[],
        besco_warnings=[],
        besco_files=[],
        besco_filenames_by_section={},
        final_source="skroutz",
        final_scope_ok=True,
        final_scope_reason="test_scope",
        scrape_persistence_input=_build_persistence_input(tmp_path, model=cli.model),
        schema_matcher_factory=RecordingSchemaMatcher,
    )

    assert isinstance(result, PrepareResultAssemblyResult)
    assert matcher_calls == [
        {
            "section_titles": [
                "Τεχνικά στοιχεία",
                "Γενικά χαρακτηριστικά",
                "Γενικά",
                "Δυνατότητες & Λειτουργίες",
                "Διαστάσεις Συσκευής",
            ],
            "taxonomy_sub_category": "Εστίες",
            "preferred_source_files": ["esties.json"],
            "taxonomy_path": "",
            "taxonomy_parent_category": "ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ",
            "taxonomy_leaf_category": "Εντοιχιζόμενες Συσκευές",
        }
    ]
    assert result.schema_match.matched_schema_id == BUILT_IN_HOB_SCHEMA_ID
    assert result.schema_candidates[0]["source_files"] == ["esties.json"]
    assert result.report["schema_preference"] == {"preferred_source_files": ["esties.json"]}


def test_assemble_prepare_result_pins_normalized_and_report_payloads(tmp_path: Path) -> None:
    source = _build_skroutz_tv_source()
    cli = _build_cli(tmp_path, model="143051", url=source.url)
    result = assemble_prepare_result(
        cli=cli,
        source="skroutz",
        fetch=_build_fetch(cli.url),
        parsed=_build_parsed(source),
        taxonomy=_build_tv_taxonomy(),
        taxonomy_candidates=[{"taxonomy_path": "ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω"}],
        manufacturer_enrichment=_build_manufacturer_enrichment_stub(),
        extracted_gallery_count=0,
        downloaded_gallery=[],
        gallery_warnings=[],
        gallery_files=[],
        selected_presentation_blocks=[],
        section_warnings=[],
        section_image_candidates=[],
        section_image_urls_resolved=[],
        section_extraction_window={"candidate_count": 0, "duplicate_signatures_skipped": 0, "selected_container_index": None, "start_anchor": "", "stop_anchor": "", "title_signature": []},
        selected_besco_images=[],
        downloaded_besco=[],
        besco_warnings=[],
        besco_files=[],
        besco_filenames_by_section={},
        final_source="skroutz",
        final_scope_ok=True,
        final_scope_reason="test_scope",
        scrape_persistence_input=_build_persistence_input(tmp_path, model=cli.model),
        schema_matcher_factory=SchemaMatcher,
    )

    assert result.schema_match.matched_schema_id == TV_TEMPLATE_SCHEMA_ID
    assert result.schema_match.score == 1.0
    assert "weak_schema_match" not in result.schema_match.warnings
    assert result.schema_match.resolved_category_path == "ΕΙΚΟΝΑ & ΗΧΟΣ > Τηλεοράσεις > 50'' & άνω"
    assert result.schema_match.candidate_pool_size == 1
    assert result.schema_match.selected_template_id == "tileoraseis"
    assert result.schema_match.match_mode == "direct_single"
    assert result.schema_match.fail_reason == ""
    assert isinstance(result.schema_match.section_overlap_score, float)
    assert isinstance(result.schema_match.label_overlap_score, float)
    assert result.schema_match.section_overlap_score >= 0.0
    assert result.schema_match.label_overlap_score >= 0.0
    assert result.normalized["llm_product"] == {"meta_keywords": ["Hisense", "55A6Q"]}
    assert result.normalized["csv_row"] == result.row
    assert result.normalized["characteristics_diagnostics"]["matched_schema_id"] == TV_TEMPLATE_SCHEMA_ID
    assert result.report["schema_resolution"] == result.schema_match.to_dict()
    assert result.report["schema_resolution"]["selected_template_id"] == "tileoraseis"
    assert result.report["schema_resolution"]["candidate_pool_size"] == 1
    assert result.report["critical_extractors"]["schema_match"] == "matched"
    assert "weak_schema_match" not in result.report["warnings"]
    assert result.report["schema_candidates"][0]["matched_schema_id"] == TV_TEMPLATE_SCHEMA_ID
    assert result.report["files_written"] == [
        str(tmp_path / cli.model / f"{cli.model}.raw.html"),
        str(tmp_path / cli.model / f"{cli.model}.source.json"),
        str(tmp_path / cli.model / f"{cli.model}.normalized.json"),
        str(tmp_path / cli.model / f"{cli.model}.report.json"),
    ]


def test_assemble_prepare_result_preserves_no_spec_sections_semantics(tmp_path: Path) -> None:
    source = _build_no_specs_source()
    cli = _build_cli(tmp_path, model="000001", url=source.url)
    result = assemble_prepare_result(
        cli=cli,
        source="electronet",
        fetch=_build_fetch(cli.url),
        parsed=_build_parsed(source),
        taxonomy=TaxonomyResolution(),
        taxonomy_candidates=[],
        manufacturer_enrichment=_build_manufacturer_enrichment_stub(),
        extracted_gallery_count=0,
        downloaded_gallery=[],
        gallery_warnings=[],
        gallery_files=[],
        selected_presentation_blocks=[],
        section_warnings=[],
        section_image_candidates=[],
        section_image_urls_resolved=[],
        section_extraction_window={"candidate_count": 0, "duplicate_signatures_skipped": 0, "selected_container_index": None, "start_anchor": "", "stop_anchor": "", "title_signature": []},
        selected_besco_images=[],
        downloaded_besco=[],
        besco_warnings=[],
        besco_files=[],
        besco_filenames_by_section={},
        final_source="electronet",
        final_scope_ok=True,
        final_scope_reason="test_scope",
        scrape_persistence_input=_build_persistence_input(tmp_path, model=cli.model),
        schema_matcher_factory=SchemaMatcher,
    )

    assert result.schema_match.matched_schema_id is None
    assert result.schema_match.score == 0.0
    assert result.schema_match.warnings == ["no_spec_sections_extracted"]
    assert result.schema_match.selected_template_id is None
    assert result.schema_match.fail_reason == "no_safe_template_match"
    assert result.normalized["schema_match"] == result.schema_match.to_dict()
    assert result.normalized["characteristics_diagnostics"]["mode"] == "raw_spec_sections"
    assert result.report["critical_extractors"]["taxonomy"] == "unresolved"
    assert result.report["critical_extractors"]["schema_match"] == "none"
    assert result.report["warnings"] == [
        "description_not_built_from_source",
        "cta_url_unresolved",
        "no_spec_sections_extracted",
    ]
    assert result.schema_candidates == []
