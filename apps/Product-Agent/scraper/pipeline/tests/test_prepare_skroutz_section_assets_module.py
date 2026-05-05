from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import pipeline.prepare_section_assets as section_assets_module
from pipeline.fetcher import FetchError
from pipeline.models import GalleryImage
from pipeline.prepare_section_assets import PrepareSectionAssetsResult, resolve_skroutz_section_assets


class RecordingFetcher:
    def __init__(
        self,
        *,
        download_result: tuple[list[GalleryImage], list[str], list[str]] | None = None,
        download_error: Exception | None = None,
        rendered_section_data: dict[str, Any] | None = None,
        rendered_error: Exception | None = None,
    ) -> None:
        self.download_result = download_result or ([], [], [])
        self.download_error = download_error
        self.rendered_section_data = rendered_section_data or {"window": {}, "sections": []}
        self.rendered_error = rendered_error
        self.download_calls: list[dict[str, Any]] = []
        self.rendered_calls: list[str] = []

    def download_besco_images(self, **kwargs: Any):
        self.download_calls.append(kwargs)
        if self.download_error is not None:
            raise self.download_error
        return self.download_result

    def extract_skroutz_section_image_records(self, url: str):
        self.rendered_calls.append(url)
        if self.rendered_error is not None:
            raise self.rendered_error
        return self.rendered_section_data


def _build_manufacturer_enrichment(*, presentation_applied: bool, presentation_block_count: int = 0) -> dict[str, Any]:
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
        "fallback_reason": "" if presentation_applied else "provider_not_matched",
    }


def test_resolve_skroutz_section_assets_prefers_manufacturer_blocks_when_enough_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            local_path=str(tmp_path / "bescos" / "besco1.jpg"),
            downloaded=True,
        ),
        GalleryImage(
            url="https://cdn.example/manufacturer-2.jpg",
            alt="Manufacturer Two",
            position=2,
            local_filename="besco2.jpg",
            local_path=str(tmp_path / "bescos" / "besco2.jpg"),
            downloaded=True,
        ),
    ]
    fetcher = RecordingFetcher(
        download_result=(
            downloaded_besco,
            [],
            [str(tmp_path / "bescos" / "besco1.jpg"), str(tmp_path / "bescos" / "besco2.jpg")],
        )
    )
    extract_calls: list[dict[str, Any]] = []

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
        return manufacturer_blocks

    monkeypatch.setattr(section_assets_module, "extract_presentation_blocks", fake_extract_presentation_blocks)
    monkeypatch.setattr(
        section_assets_module,
        "extract_skroutz_section_window",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fallback should not run")),
    )

    result = resolve_skroutz_section_assets(
        requested_sections=2,
        fetch_html="<html></html>",
        final_url="https://www.skroutz.gr/s/143051/example.html",
        canonical_url="https://www.skroutz.gr/s/143051/example.html",
        url="https://www.skroutz.gr/s/143051/example.html",
        presentation_source_html="<section>manufacturer presentation</section>",
        presentation_source_text="manufacturer text",
        manufacturer_enrichment=_build_manufacturer_enrichment(presentation_applied=True, presentation_block_count=3),
        fetcher=fetcher,
        output_dir=tmp_path,
    )

    assert extract_calls == [
        {
            "presentation_source_html": "<section>manufacturer presentation</section>",
            "presentation_source_text": "manufacturer text",
            "base_url": "https://www.skroutz.gr/s/143051/example.html",
        }
    ]
    assert fetcher.rendered_calls == []
    assert fetcher.download_calls == [
        {
            "images": [
                GalleryImage(url="https://cdn.example/manufacturer-1.jpg", alt="Manufacturer One", position=1),
                GalleryImage(url="https://cdn.example/manufacturer-2.jpg", alt="Manufacturer Two", position=2),
            ],
            "output_dir": tmp_path,
            "requested_sections": 2,
        }
    ]
    assert result == PrepareSectionAssetsResult(
        selected_presentation_blocks=manufacturer_blocks[:2],
        selected_besco_images=[
            GalleryImage(url="https://cdn.example/manufacturer-1.jpg", alt="Manufacturer One", position=1),
            GalleryImage(url="https://cdn.example/manufacturer-2.jpg", alt="Manufacturer Two", position=2),
        ],
        downloaded_besco=downloaded_besco,
        besco_warnings=[],
        besco_files=[str(tmp_path / "bescos" / "besco1.jpg"), str(tmp_path / "bescos" / "besco2.jpg")],
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
        section_extraction_window={
            "candidate_count": 3,
            "duplicate_signatures_skipped": 0,
            "selected_container_index": "manufacturer_html",
            "start_anchor": "manufacturer_presentation",
            "stop_anchor": "",
            "title_signature": ["Manufacturer One", "Manufacturer Two"],
        },
        sections_artifact_payload={
            "source": "manufacturer",
            "requested_sections": 2,
            "window": {
                "candidate_count": 3,
                "duplicate_signatures_skipped": 0,
                "selected_container_index": "manufacturer_html",
                "start_anchor": "manufacturer_presentation",
                "stop_anchor": "",
                "title_signature": ["Manufacturer One", "Manufacturer Two"],
            },
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
        },
        presentation_source_html_override=None,
    )


def test_resolve_skroutz_section_assets_falls_back_to_skroutz_sections_and_sets_presentation_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extracted_window = {
        "warnings": ["skroutz_window_warning"],
        "window": {
            "candidate_count": 3,
            "duplicate_signatures_skipped": 1,
            "selected_container_index": 4,
            "start_anchor": "Περιγραφή",
            "stop_anchor": "Κατασκευαστής",
            "title_signature": ["Alpha", "Beta", "Gamma"],
        },
        "sections": [
            {
                "title": "Alpha",
                "paragraph": "Alpha body",
                "image_candidates": ["https://cdn.example/alpha-candidate-1.jpg", "https://cdn.example/alpha-candidate-2.jpg"],
            },
            {
                "title": "Beta",
                "paragraph": "Beta body",
                "image_candidates": ["https://cdn.example/beta-candidate.jpg"],
            },
            {
                "title": "Gamma",
                "paragraph": "Gamma body",
                "image_candidates": ["https://cdn.example/gamma-candidate.jpg"],
            },
        ],
    }
    rendered_section_data = {
        "window": {
            "candidate_count": 5,
            "duplicate_signatures_skipped": 0,
            "selected_container_index": "rendered_dom",
            "rendered_container_count": 2,
        },
        "sections": [
            {"title": "Alpha", "resolved_image_url": "https://cdn.example/alpha-resolved.jpg"},
            {"title": "Beta", "resolved_image_url": ""},
            {"title": "Gamma", "resolved_image_url": "https://cdn.example/gamma-resolved.jpg"},
        ],
    }
    downloaded_besco = [
        GalleryImage(
            url="https://cdn.example/alpha-resolved.jpg",
            alt="Alpha",
            position=1,
            local_filename="besco1.jpg",
            local_path=str(tmp_path / "bescos" / "besco1.jpg"),
            downloaded=True,
        ),
        GalleryImage(
            url="https://cdn.example/gamma-resolved.jpg",
            alt="Gamma",
            position=2,
            local_filename="besco2.jpg",
            local_path=str(tmp_path / "bescos" / "besco2.jpg"),
            downloaded=True,
        ),
    ]
    fetcher = RecordingFetcher(
        download_result=(
            downloaded_besco,
            [],
            [str(tmp_path / "bescos" / "besco1.jpg"), str(tmp_path / "bescos" / "besco2.jpg")],
        ),
        rendered_section_data=rendered_section_data,
    )

    monkeypatch.setattr(
        section_assets_module,
        "extract_presentation_blocks",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("manufacturer path should not run")),
    )
    monkeypatch.setattr(section_assets_module, "extract_skroutz_section_window", lambda *_args, **_kwargs: extracted_window)
    monkeypatch.setattr(
        section_assets_module,
        "build_skroutz_presentation_source_html",
        lambda blocks: "rebuilt::" + "|".join(block["title"] for block in blocks),
    )

    result = resolve_skroutz_section_assets(
        requested_sections=2,
        fetch_html="<html>skroutz page</html>",
        final_url="https://www.skroutz.gr/s/143481/example.html",
        canonical_url="https://www.skroutz.gr/s/143481/example.html",
        url="https://www.skroutz.gr/s/143481/example.html",
        presentation_source_html="",
        presentation_source_text="",
        manufacturer_enrichment=_build_manufacturer_enrichment(presentation_applied=False),
        fetcher=fetcher,
        output_dir=tmp_path,
    )

    assert fetcher.rendered_calls == ["https://www.skroutz.gr/s/143481/example.html"]
    assert fetcher.download_calls == [
        {
            "images": [
                GalleryImage(url="https://cdn.example/alpha-resolved.jpg", alt="Alpha", position=1),
                GalleryImage(url="https://cdn.example/gamma-resolved.jpg", alt="Gamma", position=2),
            ],
            "output_dir": tmp_path,
            "requested_sections": 2,
        }
    ]
    assert result.selected_presentation_blocks == [
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
    assert result.selected_besco_images == [
        GalleryImage(url="https://cdn.example/alpha-resolved.jpg", alt="Alpha", position=1),
        GalleryImage(url="https://cdn.example/gamma-resolved.jpg", alt="Gamma", position=2),
    ]
    assert result.downloaded_besco == downloaded_besco
    assert result.besco_warnings == []
    assert result.besco_files == [str(tmp_path / "bescos" / "besco1.jpg"), str(tmp_path / "bescos" / "besco2.jpg")]
    assert result.besco_filenames_by_section == {1: "besco1.jpg", 2: "besco2.jpg"}
    assert result.section_warnings == ["skroutz_window_warning"]
    assert result.section_image_candidates == [
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
    assert result.section_image_urls_resolved == [
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
    assert result.section_extraction_window == {
        "candidate_count": 5,
        "duplicate_signatures_skipped": 1,
        "selected_container_index": "rendered_dom",
        "start_anchor": "Περιγραφή",
        "stop_anchor": "Κατασκευαστής",
        "title_signature": ["Alpha", "Beta", "Gamma"],
        "rendered_container_count": 2,
    }
    assert result.sections_artifact_payload == {
        "source": "skroutz",
        "requested_sections": 2,
        "window": {
            "candidate_count": 5,
            "duplicate_signatures_skipped": 1,
            "selected_container_index": "rendered_dom",
            "start_anchor": "Περιγραφή",
            "stop_anchor": "Κατασκευαστής",
            "title_signature": ["Alpha", "Beta", "Gamma"],
            "rendered_container_count": 2,
        },
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
    assert result.presentation_source_html_override == "rebuilt::Alpha|Gamma"


def test_resolve_skroutz_section_assets_fails_when_rendered_sections_are_insufficient(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = RecordingFetcher(
        rendered_section_data={
            "window": {},
            "sections": [{"title": "Alpha", "resolved_image_url": "https://cdn.example/alpha.jpg"}],
        }
    )

    monkeypatch.setattr(
        section_assets_module,
        "extract_skroutz_section_window",
        lambda *_args, **_kwargs: {
            "warnings": [],
            "window": {},
            "sections": [
                {"title": "Alpha", "paragraph": "Alpha body", "image_candidates": ["https://cdn.example/alpha-candidate.jpg"]},
                {"title": "Beta", "paragraph": "Beta body", "image_candidates": ["https://cdn.example/beta-candidate.jpg"]},
            ],
        },
    )

    with pytest.raises(RuntimeError) as excinfo:
        resolve_skroutz_section_assets(
            requested_sections=2,
            fetch_html="<html></html>",
            final_url="https://www.skroutz.gr/s/200001/example.html",
            canonical_url="https://www.skroutz.gr/s/200001/example.html",
            url="https://www.skroutz.gr/s/200001/example.html",
            presentation_source_html="",
            presentation_source_text="",
            manufacturer_enrichment=_build_manufacturer_enrichment(presentation_applied=False),
            fetcher=fetcher,
            output_dir=tmp_path,
        )

    assert str(excinfo.value) == "Skroutz rendered section extraction failed: expected 2 image records, found 1"
    assert fetcher.download_calls == []


def test_resolve_skroutz_section_assets_fails_on_title_order_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = RecordingFetcher(
        rendered_section_data={
            "window": {},
            "sections": [
                {"title": "Alpha", "resolved_image_url": "https://cdn.example/alpha.jpg"},
                {"title": "Wrong Title", "resolved_image_url": "https://cdn.example/beta.jpg"},
            ],
        }
    )

    monkeypatch.setattr(
        section_assets_module,
        "extract_skroutz_section_window",
        lambda *_args, **_kwargs: {
            "warnings": [],
            "window": {},
            "sections": [
                {"title": "Alpha", "paragraph": "Alpha body", "image_candidates": ["https://cdn.example/alpha-candidate.jpg"]},
                {"title": "Beta", "paragraph": "Beta body", "image_candidates": ["https://cdn.example/beta-candidate.jpg"]},
            ],
        },
    )

    with pytest.raises(RuntimeError) as excinfo:
        resolve_skroutz_section_assets(
            requested_sections=2,
            fetch_html="<html></html>",
            final_url="https://www.skroutz.gr/s/200002/example.html",
            canonical_url="https://www.skroutz.gr/s/200002/example.html",
            url="https://www.skroutz.gr/s/200002/example.html",
            presentation_source_html="",
            presentation_source_text="",
            manufacturer_enrichment=_build_manufacturer_enrichment(presentation_applied=False),
            fetcher=fetcher,
            output_dir=tmp_path,
        )

    assert str(excinfo.value) == "Skroutz section title order mismatch between rendered DOM and parsed description"
    assert fetcher.download_calls == []


def test_resolve_skroutz_section_assets_keeps_incomplete_besco_download_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = RecordingFetcher(
        download_result=(
            [
                GalleryImage(
                    url="https://cdn.example/manufacturer-1.jpg",
                    alt="Manufacturer One",
                    position=1,
                    local_filename="besco1.jpg",
                    local_path=str(tmp_path / "bescos" / "besco1.jpg"),
                    downloaded=True,
                )
            ],
            [],
            [str(tmp_path / "bescos" / "besco1.jpg")],
        )
    )
    monkeypatch.setattr(
        section_assets_module,
        "extract_presentation_blocks",
        lambda *_args, **_kwargs: [
            {"title": "Manufacturer One", "paragraph": "Body 1", "image_url": "https://cdn.example/manufacturer-1.jpg"},
            {"title": "Manufacturer Two", "paragraph": "Body 2", "image_url": "https://cdn.example/manufacturer-2.jpg"},
        ],
    )
    monkeypatch.setattr(
        section_assets_module,
        "extract_skroutz_section_window",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fallback should not run")),
    )

    with pytest.raises(RuntimeError) as excinfo:
        resolve_skroutz_section_assets(
            requested_sections=2,
            fetch_html="<html></html>",
            final_url="https://www.skroutz.gr/s/200003/example.html",
            canonical_url="https://www.skroutz.gr/s/200003/example.html",
            url="https://www.skroutz.gr/s/200003/example.html",
            presentation_source_html="<section>manufacturer presentation</section>",
            presentation_source_text="manufacturer text",
            manufacturer_enrichment=_build_manufacturer_enrichment(presentation_applied=True, presentation_block_count=2),
            fetcher=fetcher,
            output_dir=tmp_path,
        )

    assert str(excinfo.value) == "Skroutz besco image download incomplete: expected 2, downloaded 1"
    assert fetcher.download_calls == [
        {
            "images": [
                GalleryImage(url="https://cdn.example/manufacturer-1.jpg", alt="Manufacturer One", position=1),
                GalleryImage(url="https://cdn.example/manufacturer-2.jpg", alt="Manufacturer Two", position=2),
            ],
            "output_dir": tmp_path,
            "requested_sections": 2,
        }
    ]
