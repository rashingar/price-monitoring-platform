from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .characteristics_pipeline import get_characteristics_registry
from .deterministic_fields import effective_spec_sections as build_effective_spec_sections
from .mapping import build_row
from .models import CLIInput, FetchResult, GalleryImage, ParsedProduct, SchemaMatchResult, TaxonomyResolution
from .normalize import normalize_for_match
from .prepare_scrape_persistence import PrepareScrapePersistenceInput
from .repo_paths import SCHEMA_LIBRARY_PATH
from .schema_matcher import SchemaMatcher
from .skroutz_taxonomy import serialize_source_category


@dataclass(slots=True)
class PrepareResultAssemblyResult:
    schema_match: SchemaMatchResult
    schema_candidates: list[dict[str, Any]]
    row: dict[str, Any]
    normalized: dict[str, Any]
    report: dict[str, Any]


def assemble_prepare_result(
    *,
    cli: CLIInput,
    source: str,
    fetch: FetchResult,
    parsed: ParsedProduct,
    taxonomy: TaxonomyResolution,
    taxonomy_candidates: list[dict[str, Any]],
    manufacturer_enrichment: dict[str, Any],
    extracted_gallery_count: int,
    downloaded_gallery: list[GalleryImage],
    gallery_warnings: list[str],
    gallery_files: list[str],
    selected_presentation_blocks: list[dict[str, Any]],
    section_warnings: list[str],
    section_image_candidates: list[dict[str, Any]],
    section_image_urls_resolved: list[dict[str, Any]],
    section_extraction_window: dict[str, Any],
    selected_besco_images: list[GalleryImage],
    downloaded_besco: list[GalleryImage],
    besco_warnings: list[str],
    besco_files: list[str],
    besco_filenames_by_section: dict[int, str],
    final_source: str,
    final_scope_ok: bool,
    final_scope_reason: str,
    scrape_persistence_input: PrepareScrapePersistenceInput,
    sections_artifact_payload: dict[str, Any] | None = None,
    schema_matcher_factory: Callable[..., Any] = SchemaMatcher,
) -> PrepareResultAssemblyResult:
    schema_matcher = schema_matcher_factory(str(SCHEMA_LIBRARY_PATH))
    effective_spec_sections = build_effective_spec_sections(
        parsed.source,
        manufacturer_first=normalize_for_match(parsed.source.source_name) == "skroutz",
    )
    characteristics_registry = get_characteristics_registry()
    preferred_schema_source_files = characteristics_registry.preferred_schema_source_files(parsed.source, taxonomy)
    schema_match, schema_candidates = schema_matcher.match(
        effective_spec_sections,
        taxonomy.sub_category,
        preferred_source_files=preferred_schema_source_files,
        taxonomy_path=taxonomy.taxonomy_path,
        taxonomy_parent_category=taxonomy.parent_category,
        taxonomy_leaf_category=taxonomy.leaf_category,
    )

    row, normalized, mapping_warnings = build_row(
        cli,
        parsed,
        taxonomy,
        schema_match,
        downloaded_image_count=len(downloaded_gallery),
        besco_filenames_by_section=besco_filenames_by_section,
        source_raw_html=fetch.html,
    )

    report = {
        "input": cli.to_dict(),
        "source": source,
        "fetch_mode": fetch.method,
        "source_resolution": {
            "requested_url": cli.url,
            "detected_source": source,
            "resolved_url": fetch.final_url,
        },
        "identity_checks": build_prepare_result_identity_checks(cli, parsed, source),
        "url_scope_validation": {
            "ok": final_scope_ok,
            "reason": final_scope_reason,
            "final_url_source": final_source,
        },
        "skroutz_blocks_found": {
            "hero_summary_present": bool(parsed.source.hero_summary),
            "gallery_images_count": len(parsed.source.gallery_images),
            "spec_sections_count": len(parsed.source.spec_sections),
            "manufacturer_spec_sections_count": len(parsed.source.manufacturer_spec_sections),
        },
        "characteristics_pairs": {
            "count": sum(len(section.items) for section in effective_spec_sections),
            "source_count": sum(len(section.items) for section in parsed.source.spec_sections),
            "manufacturer_count": sum(len(section.items) for section in parsed.source.manufacturer_spec_sections),
        },
        "taxonomy_resolution": taxonomy.to_dict(),
        "manufacturer_enrichment": manufacturer_enrichment,
        "schema_resolution": schema_match.to_dict(),
        "characteristics_diagnostics": normalized.get("characteristics_diagnostics", {}),
        "skroutz_taxonomy_diagnostics": {
            "family_key": parsed.source.skroutz_family,
            "raw_category_tag": parsed.source.category_tag_text,
            "raw_category_href": parsed.source.category_tag_href,
            "normalized_href_slug": parsed.source.category_tag_slug,
            "matched_rule": parsed.source.taxonomy_rule_id,
            "source_category": parsed.source.taxonomy_source_category
            or serialize_source_category(
                taxonomy.parent_category,
                taxonomy.leaf_category,
                [taxonomy.sub_category] if taxonomy.sub_category else [],
            ),
            "match_type": parsed.source.taxonomy_match_type or ("exact_category" if taxonomy.parent_category and taxonomy.leaf_category else ""),
            "tv_inches": parsed.source.taxonomy_tv_inches,
            "ambiguity": parsed.source.taxonomy_ambiguity,
            "escalation_reason": parsed.source.taxonomy_escalation_reason,
        },
        "schema_preference": {
            "preferred_source_files": preferred_schema_source_files,
        },
        "unsupported_features": [],
        "critical_extractors": {
            "product_code": parsed.provenance.get("product_code", "missing"),
            "brand": parsed.provenance.get("brand", "missing"),
            "mpn": parsed.provenance.get("mpn", "missing"),
            "name": parsed.provenance.get("name", "missing"),
            "price": parsed.provenance.get("price", "missing"),
            "taxonomy": "resolved" if taxonomy.parent_category and taxonomy.leaf_category else "unresolved",
            "schema_match": "matched" if schema_match.score >= 0.35 else ("weak" if schema_match.score > 0 else "none"),
        },
        "field_diagnostics": {key: value.to_dict() for key, value in parsed.field_diagnostics.items()},
        "missing_fields": parsed.missing_fields,
        "warnings": parsed.warnings
        + gallery_warnings
        + section_warnings
        + besco_warnings
        + mapping_warnings
        + schema_match.warnings
        + ([taxonomy.reason] if taxonomy.reason and taxonomy.reason != "" else []),
        "taxonomy_candidates": taxonomy_candidates,
        "schema_candidates": schema_candidates,
        "gallery_summary": {
            "extracted_count": extracted_gallery_count,
            "downloaded_count": len(downloaded_gallery),
            "requested_photos": cli.photos,
        },
        "sections_requested": cli.sections,
        "sections_extracted": len(selected_presentation_blocks),
        "section_titles": [block["title"] for block in selected_presentation_blocks],
        "section_image_candidates": section_image_candidates,
        "section_image_urls_resolved": section_image_urls_resolved,
        "section_downloads": [
            {
                "position": image.position,
                "source_url": image.url,
                "local_filename": image.local_filename,
                "local_path": image.local_path,
            }
            for image in downloaded_besco
        ],
        "section_extraction_window": section_extraction_window,
        "besco_summary": {
            "presentation_blocks_count": len(selected_presentation_blocks),
            "extracted_count": len(selected_besco_images),
            "downloaded_count": len(downloaded_besco),
            "requested_sections": cli.sections,
        },
        "files_written": [
            str(scrape_persistence_input.raw_html_path),
            str(scrape_persistence_input.source_json_path),
            str(scrape_persistence_input.normalized_json_path),
            str(scrape_persistence_input.report_json_path),
            *[
                path
                for document in manufacturer_enrichment.get("documents", [])
                for path in [document.get("local_path", ""), document.get("text_path", "")]
                if path
            ],
            *gallery_files,
            *([str(scrape_persistence_input.bescos_raw_path)] if sections_artifact_payload is not None else []),
            *besco_files,
        ],
    }

    return PrepareResultAssemblyResult(
        schema_match=schema_match,
        schema_candidates=schema_candidates,
        row=row,
        normalized=normalized,
        report=report,
    )


def build_prepare_result_identity_checks(cli: CLIInput, parsed: ParsedProduct, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "input_model": cli.model,
        "page_type": parsed.source.page_type,
        "page_product_code": parsed.source.product_code,
        "name_present": bool(parsed.source.name),
        "brand_present": bool(parsed.source.brand),
        "mpn_present": bool(parsed.source.mpn),
    }
