from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .fetcher import FetchError
from .html_builders import extract_presentation_blocks
from .models import GalleryImage
from .normalize import normalize_for_match
from .skroutz_sections import build_skroutz_presentation_source_html, extract_skroutz_section_window


@dataclass(slots=True)
class SectionAssetDownloadResult:
    downloaded_besco: list[GalleryImage] = field(default_factory=list)
    besco_warnings: list[str] = field(default_factory=list)
    besco_files: list[str] = field(default_factory=list)
    besco_filenames_by_section: dict[int, str] = field(default_factory=dict)


@dataclass(slots=True)
class PrepareSectionAssetsResult:
    selected_presentation_blocks: list[dict[str, Any]] = field(default_factory=list)
    selected_besco_images: list[GalleryImage] = field(default_factory=list)
    downloaded_besco: list[GalleryImage] = field(default_factory=list)
    besco_warnings: list[str] = field(default_factory=list)
    besco_files: list[str] = field(default_factory=list)
    besco_filenames_by_section: dict[int, str] = field(default_factory=dict)
    section_warnings: list[str] = field(default_factory=list)
    section_image_candidates: list[dict[str, Any]] = field(default_factory=list)
    section_image_urls_resolved: list[dict[str, Any]] = field(default_factory=list)
    section_extraction_window: dict[str, Any] = field(default_factory=dict)
    sections_artifact_payload: dict[str, Any] | None = None
    presentation_source_html_override: str | None = None


def _default_section_extraction_window() -> dict[str, Any]:
    return {
        "candidate_count": 0,
        "duplicate_signatures_skipped": 0,
        "selected_container_index": None,
        "start_anchor": "",
        "stop_anchor": "",
        "title_signature": [],
    }


def _select_skroutz_image_backed_sections(
    all_sections: list[dict[str, Any]],
    rendered_sections: list[dict[str, Any]],
    requested_sections: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_blocks: list[dict[str, Any]] = []
    selected_rendered_sections: list[dict[str, Any]] = []
    effective_limit = min(requested_sections, len(all_sections), len(rendered_sections))
    for block, rendered_section in zip(all_sections, rendered_sections):
        block_title = normalize_for_match(str(block.get("title", "")))
        rendered_title = normalize_for_match(str(rendered_section.get("title", "")))
        if block_title != rendered_title:
            raise RuntimeError("Skroutz section title order mismatch between rendered DOM and parsed description")

        resolved_image_url = str(rendered_section.get("resolved_image_url", "")).strip()
        if not resolved_image_url:
            continue

        selected_blocks.append(block)
        selected_rendered_sections.append(rendered_section)
        if len(selected_blocks) == effective_limit:
            return selected_blocks, selected_rendered_sections

    return selected_blocks, selected_rendered_sections


def _select_static_image_backed_sections(
    all_sections: list[dict[str, Any]],
    requested_sections: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_blocks: list[dict[str, Any]] = []
    selected_rendered_sections: list[dict[str, Any]] = []
    effective_limit = min(requested_sections, len(all_sections))
    for block in all_sections:
        resolved_image_url = str(block.get("image_url", "")).strip()
        if not resolved_image_url:
            continue
        selected_blocks.append(block)
        selected_rendered_sections.append(
            {
                "title": block.get("title", ""),
                "resolved_image_url": resolved_image_url,
            }
        )
        if len(selected_blocks) == effective_limit:
            return selected_blocks, selected_rendered_sections

    return selected_blocks, selected_rendered_sections


def _section_image_candidates_for_block(block: dict[str, Any]) -> list[str]:
    if "image_candidates" in block:
        return list(block.get("image_candidates", []))
    image_url = str(block.get("image_url", "")).strip()
    return [image_url] if image_url else []


def build_section_image_candidates(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "position": index,
            "title": block["title"],
            "candidates": _section_image_candidates_for_block(block),
        }
        for index, block in enumerate(blocks, start=1)
    ]


def build_section_image_urls_resolved(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "position": index,
            "title": block["title"],
            "url": block["image_url"],
        }
        for index, block in enumerate(blocks, start=1)
        if block.get("image_url")
    ]


def build_sections_artifact_payload(
    *,
    source: str,
    requested_sections: int,
    section_extraction_window: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source": source,
        "requested_sections": requested_sections,
        "window": section_extraction_window,
        "sections": [
            {
                "position": index,
                "title": block["title"],
                "body": block["paragraph"],
                "image_candidates": _section_image_candidates_for_block(block),
                "resolved_image_url": block.get("image_url", ""),
                "target_filename": f"besco{index}.jpg",
            }
            for index, block in enumerate(blocks, start=1)
        ],
    }


def resolve_skroutz_section_assets(
    *,
    requested_sections: int,
    fetch_html: str,
    final_url: str,
    canonical_url: str,
    url: str,
    presentation_source_html: str,
    presentation_source_text: str,
    manufacturer_enrichment: dict[str, Any],
    fetcher: Any,
    output_dir: Path,
) -> PrepareSectionAssetsResult:
    if requested_sections <= 0:
        return PrepareSectionAssetsResult(section_extraction_window=_default_section_extraction_window())

    base_url = canonical_url or url
    section_extraction_window = _default_section_extraction_window()
    manufacturer_blocks: list[dict[str, Any]] = []
    if manufacturer_enrichment.get("presentation_applied"):
        manufacturer_blocks = extract_presentation_blocks(
            presentation_source_html,
            presentation_source_text,
            base_url=base_url,
        )

    if len(manufacturer_blocks) >= requested_sections:
        selected_presentation_blocks = manufacturer_blocks[:requested_sections]
        selected_besco_images = [
            GalleryImage(url=block["image_url"], alt=block["title"], position=section_index)
            for section_index, block in enumerate(selected_presentation_blocks, start=1)
            if block.get("image_url")
        ]
        section_image_candidates = build_section_image_candidates(selected_presentation_blocks)
        section_image_urls_resolved = build_section_image_urls_resolved(selected_presentation_blocks)
        section_extraction_window = {
            "candidate_count": len(manufacturer_blocks),
            "duplicate_signatures_skipped": 0,
            "selected_container_index": "manufacturer_html",
            "start_anchor": "manufacturer_presentation",
            "stop_anchor": "",
            "title_signature": [block["title"] for block in selected_presentation_blocks],
        }
        sections_artifact_payload = build_sections_artifact_payload(
            source="manufacturer",
            requested_sections=requested_sections,
            section_extraction_window=section_extraction_window,
            blocks=selected_presentation_blocks,
        )
        section_warnings: list[str] = []
        presentation_source_html_override = None
    else:
        extracted_window = extract_skroutz_section_window(fetch_html, base_url=base_url)
        section_warnings = list(extracted_window.get("warnings", []))
        section_extraction_window = dict(extracted_window.get("window", section_extraction_window))
        all_sections = list(extracted_window.get("sections", []))
        rendered_section_data: dict[str, Any] = {"window": {}, "sections": []}
        try:
            rendered_section_data = fetcher.extract_skroutz_section_image_records(final_url)
        except FetchError as exc:
            section_warnings.append(f"skroutz_rendered_section_extraction_failed:{exc}")
        rendered_sections = list(rendered_section_data.get("sections", []))
        rendered_window = rendered_section_data.get("window", {})
        if rendered_window:
            section_extraction_window = {
                **section_extraction_window,
                **rendered_window,
                "candidate_count": max(
                    int(section_extraction_window.get("candidate_count", 0) or 0),
                    int(rendered_window.get("candidate_count", 0) or 0),
                ),
                "duplicate_signatures_skipped": max(
                    int(section_extraction_window.get("duplicate_signatures_skipped", 0) or 0),
                    int(rendered_window.get("duplicate_signatures_skipped", 0) or 0),
                ),
            }
        if rendered_sections:
            selected_presentation_blocks, rendered_sections = _select_skroutz_image_backed_sections(
                all_sections=all_sections,
                rendered_sections=rendered_sections,
                requested_sections=requested_sections,
            )
        else:
            selected_presentation_blocks, rendered_sections = _select_static_image_backed_sections(
                all_sections=all_sections,
                requested_sections=requested_sections,
            )
        if len(all_sections) < requested_sections:
            section_warnings.append(f"skroutz_sections_clamped:{len(all_sections)}/{requested_sections}")
        if len(rendered_sections) < requested_sections:
            section_warnings.append(f"skroutz_rendered_sections_clamped:{len(rendered_sections)}/{requested_sections}")
        if len(selected_presentation_blocks) < requested_sections:
            section_warnings.append(f"skroutz_image_backed_sections_clamped:{len(selected_presentation_blocks)}/{requested_sections}")
        section_image_candidates = build_section_image_candidates(selected_presentation_blocks)
        selected_besco_images = []
        for section_index, block in enumerate(selected_presentation_blocks, start=1):
            rendered_section = rendered_sections[section_index - 1]
            resolved_image_url = str(rendered_section.get("resolved_image_url", "")).strip()
            block["image_url"] = resolved_image_url
            selected_besco_images.append(GalleryImage(url=resolved_image_url, alt=block["title"], position=section_index))
        section_image_urls_resolved = build_section_image_urls_resolved(selected_presentation_blocks)
        presentation_source_html_override = None
        if not manufacturer_enrichment.get("presentation_applied"):
            presentation_source_html_override = build_skroutz_presentation_source_html(selected_presentation_blocks)
        sections_artifact_payload = build_sections_artifact_payload(
            source="skroutz",
            requested_sections=requested_sections,
            section_extraction_window=section_extraction_window,
            blocks=selected_presentation_blocks,
        )

    section_asset_download = download_section_assets(
        fetcher=fetcher,
        images=selected_besco_images,
        output_dir=output_dir,
        requested_sections=len(selected_presentation_blocks),
        strict=True,
        strict_expected_count=len(selected_presentation_blocks),
    )

    return PrepareSectionAssetsResult(
        selected_presentation_blocks=selected_presentation_blocks,
        selected_besco_images=selected_besco_images,
        downloaded_besco=section_asset_download.downloaded_besco,
        besco_warnings=section_asset_download.besco_warnings,
        besco_files=section_asset_download.besco_files,
        besco_filenames_by_section=section_asset_download.besco_filenames_by_section,
        section_warnings=section_warnings,
        section_image_candidates=section_image_candidates,
        section_image_urls_resolved=section_image_urls_resolved,
        section_extraction_window=section_extraction_window,
        sections_artifact_payload=sections_artifact_payload,
        presentation_source_html_override=presentation_source_html_override,
    )


def download_section_assets(
    *,
    fetcher: Any,
    images: list[GalleryImage],
    output_dir: Path,
    requested_sections: int,
    strict: bool,
    strict_expected_count: int | None = None,
) -> SectionAssetDownloadResult:
    if not images:
        return SectionAssetDownloadResult()

    try:
        downloaded_besco, besco_warnings, besco_files = fetcher.download_besco_images(
            images=images,
            output_dir=output_dir,
            requested_sections=requested_sections,
        )
    except FetchError as exc:
        if strict:
            raise RuntimeError(f"Skroutz besco image download failed: {exc}") from exc
        return SectionAssetDownloadResult(besco_warnings=[f"besco_download_failed:{exc}"])

    if strict and strict_expected_count is not None and len(downloaded_besco) < strict_expected_count:
        raise RuntimeError(
            f"Skroutz besco image download incomplete: expected {strict_expected_count}, downloaded {len(downloaded_besco)}"
        )

    return SectionAssetDownloadResult(
        downloaded_besco=downloaded_besco,
        besco_warnings=besco_warnings,
        besco_files=besco_files,
        besco_filenames_by_section={image.position: image.local_filename for image in downloaded_besco},
    )
