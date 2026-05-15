from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .fetcher import ElectronetFetcher
from .html_builders import extract_presentation_blocks
from .models import CLIInput, GalleryImage, ParsedProduct, SchemaMatchResult, TaxonomyResolution
from .prepare_provider_resolution import PrepareProviderResolutionResult, resolve_prepare_provider_resolution
from .prepare_result_assembly import assemble_prepare_result
from .prepare_section_assets import (
    download_section_assets,
    PrepareSectionAssetsResult,
    resolve_skroutz_section_assets,
)
from .prepare_scrape_persistence import (
    PrepareScrapePersistenceInput,
    PrepareScrapePersistenceResult,
    persist_prepare_scrape_artifacts,
)
from .prepare_taxonomy_enrichment import PrepareTaxonomyEnrichmentResult, resolve_prepare_taxonomy_enrichment
from .ecommerce_handoff import (
    write_ecommerce_source_failure_handoff,
    write_ecommerce_source_handoff,
)
from .source_acquisition_models import SourceAcquisitionResult
from .source_acquisition_stage import execute_source_acquisition_stage
from .source_capture_client import SourceCaptureSyncResult, sync_initial_source_capture
from .source_detection import validate_url_scope
from .utils import ensure_directory

BLOCKED_BY_CHALLENGE = "blocked_by_challenge"


def execute_prepare_stage(
    cli: CLIInput,
    *,
    model_dir: Path | None = None,
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]] = validate_url_scope,
    fetcher_factory: Callable[[], ElectronetFetcher] = ElectronetFetcher,
    resolve_prepare_provider_input_fn: Callable[..., PrepareProviderResolutionResult] = resolve_prepare_provider_resolution,
    execute_source_acquisition_stage_fn: Callable[..., SourceAcquisitionResult] = execute_source_acquisition_stage,
    source_capture_sync_fn: Callable[[str, str], SourceCaptureSyncResult] = sync_initial_source_capture,
    resolve_prepare_taxonomy_enrichment_fn: Callable[..., PrepareTaxonomyEnrichmentResult] = resolve_prepare_taxonomy_enrichment,
    resolve_skroutz_section_assets_fn: Callable[..., PrepareSectionAssetsResult] = resolve_skroutz_section_assets,
    assemble_prepare_result_fn: Callable[..., Any] = assemble_prepare_result,
    persist_prepare_scrape_artifacts_fn: Callable[[PrepareScrapePersistenceInput], PrepareScrapePersistenceResult] = persist_prepare_scrape_artifacts,
) -> dict[str, Any]:
    resolved_model_dir = ensure_directory(model_dir or (Path(cli.out) / cli.model))
    acquisition_kwargs: dict[str, Any] = {
        "model": cli.model,
        "url": cli.url,
        "photos": cli.photos,
        "model_dir": resolved_model_dir,
        "gallery_url": cli.gallery_url,
        "characteristics_url": cli.characteristics_url,
        "second_opencart_image_index": cli.second_opencart_image_index,
        "validate_url_scope_fn": validate_url_scope_fn,
        "fetcher_factory": fetcher_factory,
        "resolve_prepare_provider_input_fn": resolve_prepare_provider_input_fn,
    }
    if source_capture_sync_fn is not sync_initial_source_capture:
        acquisition_kwargs["source_capture_sync_fn"] = source_capture_sync_fn
    acquisition = execute_source_acquisition_stage_fn(**acquisition_kwargs)
    try:
        return execute_prepare_from_acquisition(
            cli,
            acquisition,
            validate_url_scope_fn=validate_url_scope_fn,
            fetcher_factory=fetcher_factory,
            resolve_prepare_taxonomy_enrichment_fn=resolve_prepare_taxonomy_enrichment_fn,
            resolve_skroutz_section_assets_fn=resolve_skroutz_section_assets_fn,
            assemble_prepare_result_fn=assemble_prepare_result_fn,
            persist_prepare_scrape_artifacts_fn=persist_prepare_scrape_artifacts_fn,
        )
    except Exception as exc:
        try:
            write_ecommerce_source_failure_handoff(
                cli=cli,
                source=acquisition.source,
                provider_id=acquisition.provider_id,
                fetch=acquisition.fetch,
                parsed=acquisition.parsed,
                model_dir=acquisition.model_dir,
                error=exc,
            )
        except Exception:
            pass
        raise


def execute_prepare_from_acquisition(
    cli: CLIInput,
    acquisition: SourceAcquisitionResult,
    *,
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]] = validate_url_scope,
    fetcher_factory: Callable[[], ElectronetFetcher] = ElectronetFetcher,
    resolve_prepare_taxonomy_enrichment_fn: Callable[..., PrepareTaxonomyEnrichmentResult] = resolve_prepare_taxonomy_enrichment,
    resolve_skroutz_section_assets_fn: Callable[..., PrepareSectionAssetsResult] = resolve_skroutz_section_assets,
    assemble_prepare_result_fn: Callable[..., Any] = assemble_prepare_result,
    persist_prepare_scrape_artifacts_fn: Callable[[PrepareScrapePersistenceInput], PrepareScrapePersistenceResult] = persist_prepare_scrape_artifacts,
) -> dict[str, Any]:
    fetcher = fetcher_factory()
    source = acquisition.source
    fetch = acquisition.fetch
    parsed = acquisition.parsed
    final_source, final_scope_ok, final_scope_reason = validate_url_scope_fn(fetch.final_url)
    resolved_model_dir = ensure_directory(acquisition.model_dir)
    scrape_persistence_input = PrepareScrapePersistenceInput(
        model=cli.model,
        scrape_dir=resolved_model_dir,
        raw_html=fetch.html,
        source_payload={},
        normalized_payload={},
        report_payload={},
    )

    if _is_blocked_by_challenge(parsed):
        return _persist_blocked_prepare_result(
            cli=cli,
            source=source,
            provider_id=acquisition.provider_id,
            fetch=fetch,
            parsed=parsed,
            model_dir=resolved_model_dir,
            final_source=final_source,
            final_scope_ok=final_scope_ok,
            final_scope_reason=final_scope_reason,
            scrape_persistence_input=scrape_persistence_input,
            persist_prepare_scrape_artifacts_fn=persist_prepare_scrape_artifacts_fn,
        )

    extracted_gallery_count = acquisition.extracted_gallery_count
    gallery_warnings = list(acquisition.gallery_warnings)
    gallery_files = list(acquisition.gallery_files)
    downloaded_gallery = list(acquisition.downloaded_gallery)
    gallery_settings = {
        "gallery_url_used": bool(acquisition.snapshot_provenance.get("gallery_url_used", False)),
        "gallery_extraction_url": str(acquisition.snapshot_provenance.get("gallery_extraction_url") or cli.url),
        "product_data_extraction_url": str(acquisition.snapshot_provenance.get("product_data_extraction_url") or cli.url),
        "product_data_extraction_uses_main_url": True,
        "second_opencart_image_index": acquisition.snapshot_provenance.get("second_opencart_image_index"),
        "second_opencart_image_override_applied": bool(
            acquisition.snapshot_provenance.get("second_opencart_image_override_applied", False)
        ),
        "second_opencart_image_warning": acquisition.snapshot_provenance.get("second_opencart_image_warning"),
        "deduplicated_gallery_count": acquisition.snapshot_provenance.get("deduplicated_gallery_count"),
    }
    characteristics_settings = {
        "characteristics_url_used": bool(acquisition.snapshot_provenance.get("characteristics_url_used", False)),
        "characteristics_extraction_url": str(
            acquisition.snapshot_provenance.get("characteristics_extraction_url") or cli.url
        ),
        "product_data_extraction_url": str(acquisition.snapshot_provenance.get("product_data_extraction_url") or cli.url),
        "product_data_extraction_uses_main_url": True,
    }

    selected_presentation_blocks = []
    selected_besco_images: list[GalleryImage] = []
    section_warnings: list[str] = []
    section_image_candidates: list[dict[str, Any]] = []
    section_image_urls_resolved: list[dict[str, Any]] = []
    section_extraction_window: dict[str, Any] = {
        "candidate_count": 0,
        "duplicate_signatures_skipped": 0,
        "selected_container_index": None,
        "start_anchor": "",
        "stop_anchor": "",
        "title_signature": [],
    }
    sections_artifact_payload: dict[str, Any] | None = None
    if cli.sections > 0 and source != "skroutz":
        selected_presentation_blocks = extract_presentation_blocks(
            parsed.source.presentation_source_html,
            parsed.source.presentation_source_text,
            base_url=parsed.source.canonical_url or parsed.source.url,
        )[: cli.sections]
        selected_besco_images = [
            GalleryImage(url=block["image_url"], alt=block["title"], position=section_index)
            for section_index, block in enumerate(selected_presentation_blocks, start=1)
            if block.get("image_url")
        ]
    parsed.source.besco_images = selected_besco_images

    besco_warnings: list[str] = []
    besco_files: list[str] = []
    downloaded_besco: list[GalleryImage] = []
    besco_filenames_by_section: dict[int, str] = {}
    if selected_besco_images:
        section_asset_download = download_section_assets(
            fetcher=fetcher,
            images=selected_besco_images,
            output_dir=resolved_model_dir,
            requested_sections=len(selected_presentation_blocks),
            strict=source == "skroutz" and cli.sections > 0,
            strict_expected_count=cli.sections if source == "skroutz" and cli.sections > 0 else None,
        )
        downloaded_besco = section_asset_download.downloaded_besco
        besco_warnings = section_asset_download.besco_warnings
        besco_files = section_asset_download.besco_files
        besco_filenames_by_section = section_asset_download.besco_filenames_by_section
        if downloaded_besco:
            parsed.source.besco_images = downloaded_besco

    parsed.source.raw_html_path = str(scrape_persistence_input.raw_html_path)
    parsed.source.fallback_used = fetch.fallback_used

    taxonomy_enrichment = resolve_prepare_taxonomy_enrichment_fn(
        source=source,
        parsed=parsed,
        fetcher=fetcher,
        model_dir=resolved_model_dir,
    )
    taxonomy = taxonomy_enrichment.taxonomy
    taxonomy_candidates = taxonomy_enrichment.taxonomy_candidates
    manufacturer_enrichment = taxonomy_enrichment.manufacturer_enrichment
    if source == "skroutz" and cli.sections > 0:
        skroutz_section_assets = resolve_skroutz_section_assets_fn(
            requested_sections=cli.sections,
            fetch_html=fetch.html,
            final_url=fetch.final_url,
            canonical_url=parsed.source.canonical_url,
            url=parsed.source.url,
            presentation_source_html=parsed.source.presentation_source_html,
            presentation_source_text=parsed.source.presentation_source_text,
            manufacturer_enrichment=manufacturer_enrichment,
            fetcher=fetcher,
            output_dir=resolved_model_dir,
        )
        selected_presentation_blocks = skroutz_section_assets.selected_presentation_blocks
        selected_besco_images = skroutz_section_assets.selected_besco_images
        downloaded_besco = skroutz_section_assets.downloaded_besco
        besco_warnings = skroutz_section_assets.besco_warnings
        besco_files = skroutz_section_assets.besco_files
        besco_filenames_by_section = skroutz_section_assets.besco_filenames_by_section
        section_warnings = skroutz_section_assets.section_warnings
        section_image_candidates = skroutz_section_assets.section_image_candidates
        section_image_urls_resolved = skroutz_section_assets.section_image_urls_resolved
        section_extraction_window = skroutz_section_assets.section_extraction_window
        sections_artifact_payload = skroutz_section_assets.sections_artifact_payload
        if skroutz_section_assets.presentation_source_html_override is not None:
            parsed.source.presentation_source_html = skroutz_section_assets.presentation_source_html_override
        parsed.source.besco_images = selected_besco_images
        if downloaded_besco:
            parsed.source.besco_images = downloaded_besco
    source_payload = parsed.source.to_dict()

    result_assembly = assemble_prepare_result_fn(
        cli=cli,
        source=source,
        fetch=fetch,
        parsed=parsed,
        taxonomy=taxonomy,
        taxonomy_candidates=taxonomy_candidates,
        manufacturer_enrichment=manufacturer_enrichment,
        extracted_gallery_count=extracted_gallery_count,
        downloaded_gallery=downloaded_gallery,
        gallery_warnings=gallery_warnings,
        gallery_files=gallery_files,
        gallery_settings=gallery_settings,
        characteristics_source=acquisition.characteristics_source,
        characteristics_raw_html=acquisition.characteristics_fetch.html if acquisition.characteristics_fetch else None,
        characteristics_settings=characteristics_settings,
        selected_presentation_blocks=selected_presentation_blocks,
        section_warnings=section_warnings,
        section_image_candidates=section_image_candidates,
        section_image_urls_resolved=section_image_urls_resolved,
        section_extraction_window=section_extraction_window,
        selected_besco_images=selected_besco_images,
        downloaded_besco=downloaded_besco,
        besco_warnings=besco_warnings,
        besco_files=besco_files,
        besco_filenames_by_section=besco_filenames_by_section,
        final_source=final_source,
        final_scope_ok=final_scope_ok,
        final_scope_reason=final_scope_reason,
        scrape_persistence_input=scrape_persistence_input,
        sections_artifact_payload=sections_artifact_payload,
    )

    scrape_persistence_input.source_payload = source_payload
    scrape_persistence_input.normalized_payload = result_assembly.normalized
    scrape_persistence_input.report_payload = result_assembly.report
    scrape_persistence_input.bescos_raw_payload = sections_artifact_payload
    scrape_persistence = persist_prepare_scrape_artifacts_fn(scrape_persistence_input)
    write_ecommerce_source_handoff(
        cli=cli,
        source=source,
        provider_id=acquisition.provider_id,
        fetch=fetch,
        parsed=parsed,
        model_dir=resolved_model_dir,
    )

    return {
        "cli": cli,
        "source": source,
        "fetch": fetch,
        "parsed": parsed,
        "taxonomy": taxonomy,
        "taxonomy_candidates": taxonomy_candidates,
        "schema_match": result_assembly.schema_match,
        "schema_candidates": result_assembly.schema_candidates,
        "manufacturer_enrichment": manufacturer_enrichment,
        "row": result_assembly.row,
        "normalized": result_assembly.normalized,
        "report": result_assembly.report,
        "model_dir": resolved_model_dir,
        "raw_html_path": scrape_persistence.raw_html_path,
        "source_json_path": scrape_persistence.source_json_path,
        "normalized_json_path": scrape_persistence.normalized_json_path,
        "report_json_path": scrape_persistence.report_json_path,
        "selected_presentation_blocks": selected_presentation_blocks,
        "downloaded_gallery": downloaded_gallery,
        "downloaded_besco": downloaded_besco,
        "besco_filenames_by_section": besco_filenames_by_section,
    }


def _is_blocked_by_challenge(parsed: ParsedProduct) -> bool:
    return parsed.source.page_type == BLOCKED_BY_CHALLENGE


def _append_warning_once(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def _persist_blocked_prepare_result(
    *,
    cli: CLIInput,
    source: str,
    provider_id: str,
    fetch,
    parsed: ParsedProduct,
    model_dir: Path,
    final_source: str,
    final_scope_ok: bool,
    final_scope_reason: str,
    scrape_persistence_input: PrepareScrapePersistenceInput,
    persist_prepare_scrape_artifacts_fn: Callable[[PrepareScrapePersistenceInput], PrepareScrapePersistenceResult],
) -> dict[str, Any]:
    _append_warning_once(parsed.warnings, BLOCKED_BY_CHALLENGE)
    _append_warning_once(parsed.warnings, "prepare_snapshot_blocked_by_challenge")
    parsed.source.raw_html_path = str(scrape_persistence_input.raw_html_path)
    parsed.source.fallback_used = fetch.fallback_used
    source_payload = parsed.source.to_dict()
    taxonomy = TaxonomyResolution(reason=BLOCKED_BY_CHALLENGE)
    schema_match = SchemaMatchResult(fail_reason=BLOCKED_BY_CHALLENGE, warnings=[BLOCKED_BY_CHALLENGE])
    blocked_snapshot = {
        "blocked": True,
        "reason": BLOCKED_BY_CHALLENGE,
        "status_code": fetch.status_code,
        "requested_url": fetch.url,
        "final_url": fetch.final_url,
        "fetch_method": fetch.method,
        "provider_id": provider_id,
    }
    normalized = {
        "input": cli.to_dict(),
        "source": source_payload,
        "taxonomy": taxonomy.to_dict(),
        "schema_match": schema_match.to_dict(),
        "deterministic_product": {},
        "blocked_snapshot": blocked_snapshot,
    }
    report = {
        "input": cli.to_dict(),
        "source": source,
        "fetch_mode": fetch.method,
        "source_resolution": {
            "requested_url": cli.url,
            "detected_source": source,
            "resolved_url": fetch.final_url,
        },
        "identity_checks": {
            "source": source,
            "input_model": cli.model,
            "page_type": parsed.source.page_type,
            "page_product_code": parsed.source.product_code,
            "name_present": bool(parsed.source.name),
            "brand_present": bool(parsed.source.brand),
            "mpn_present": bool(parsed.source.mpn),
        },
        "url_scope_validation": {
            "ok": final_scope_ok,
            "reason": final_scope_reason,
            "final_url_source": final_source,
        },
        "blocked_snapshot": blocked_snapshot,
        "gallery_settings": {
            "gallery_url_used": bool(cli.gallery_url),
            "gallery_extraction_url": cli.gallery_url or cli.url,
            "product_data_extraction_url": cli.url,
            "product_data_extraction_uses_main_url": True,
            "second_opencart_image_index": cli.second_opencart_image_index,
            "second_opencart_image_override_applied": False,
            "second_opencart_image_warning": None,
            "deduplicated_gallery_count": 0,
        },
        "characteristics_settings": {
            "characteristics_url_used": bool(cli.characteristics_url),
            "characteristics_extraction_url": cli.characteristics_url or cli.url,
            "product_data_extraction_url": cli.url,
            "product_data_extraction_uses_main_url": True,
        },
        "critical_extractors": {
            "product_code": "blocked",
            "brand": "blocked",
            "mpn": "blocked",
            "name": "blocked",
            "price": "blocked",
            "taxonomy": "blocked",
            "schema_match": "blocked",
        },
        "missing_fields": list(parsed.missing_fields),
        "warnings": list(parsed.warnings),
        "files_written": [
            str(scrape_persistence_input.raw_html_path),
            str(scrape_persistence_input.source_json_path),
            str(scrape_persistence_input.normalized_json_path),
            str(scrape_persistence_input.report_json_path),
        ],
    }
    scrape_persistence_input.source_payload = source_payload
    scrape_persistence_input.normalized_payload = normalized
    scrape_persistence_input.report_payload = report
    scrape_persistence = persist_prepare_scrape_artifacts_fn(scrape_persistence_input)
    write_ecommerce_source_handoff(
        cli=cli,
        source=source,
        provider_id=provider_id,
        fetch=fetch,
        parsed=parsed,
        model_dir=model_dir,
    )
    return {
        "cli": cli,
        "source": source,
        "fetch": fetch,
        "parsed": parsed,
        "taxonomy": taxonomy,
        "taxonomy_candidates": [],
        "schema_match": schema_match,
        "schema_candidates": [],
        "manufacturer_enrichment": {},
        "row": {},
        "normalized": normalized,
        "report": report,
        "model_dir": model_dir,
        "raw_html_path": scrape_persistence.raw_html_path,
        "source_json_path": scrape_persistence.source_json_path,
        "normalized_json_path": scrape_persistence.normalized_json_path,
        "report_json_path": scrape_persistence.report_json_path,
        "selected_presentation_blocks": [],
        "downloaded_gallery": [],
        "downloaded_besco": [],
        "besco_filenames_by_section": {},
        "blocked_reason": BLOCKED_BY_CHALLENGE,
    }
