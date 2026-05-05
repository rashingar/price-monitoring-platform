from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .fetcher import ElectronetFetcher
from .html_builders import extract_presentation_blocks
from .models import CLIInput, GalleryImage
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
from .price_fetcher_handoff import (
    write_price_fetcher_source_failure_handoff,
    write_price_fetcher_source_handoff,
)
from .source_acquisition_models import SourceAcquisitionResult
from .source_acquisition_stage import execute_source_acquisition_stage
from .source_capture_client import SourceCaptureSyncResult, sync_initial_source_capture
from .source_detection import validate_url_scope
from .utils import ensure_directory


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
            write_price_fetcher_source_failure_handoff(
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

    extracted_gallery_count = acquisition.extracted_gallery_count
    gallery_warnings = list(acquisition.gallery_warnings)
    gallery_files = list(acquisition.gallery_files)
    downloaded_gallery = list(acquisition.downloaded_gallery)

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
    write_price_fetcher_source_handoff(
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
