from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.fetcher import FetchError
from pipeline.models import GalleryImage
from pipeline.prepare_section_assets import (
    SectionAssetDownloadResult,
    build_section_image_candidates,
    build_section_image_urls_resolved,
    build_sections_artifact_payload,
    download_section_assets,
)


class RecordingFetcher:
    def __init__(
        self,
        *,
        download_result: tuple[list[GalleryImage], list[str], list[str]] | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self.download_result = download_result or ([], [], [])
        self.download_error = download_error
        self.calls: list[dict[str, Any]] = []

    def download_besco_images(self, **kwargs: Any):
        self.calls.append(kwargs)
        if self.download_error is not None:
            raise self.download_error
        return self.download_result


def test_download_section_assets_returns_empty_result_without_fetching_when_no_images(tmp_path: Path) -> None:
    fetcher = RecordingFetcher()

    result = download_section_assets(
        fetcher=fetcher,
        images=[],
        output_dir=tmp_path,
        requested_sections=2,
        strict=False,
    )

    assert result == SectionAssetDownloadResult()
    assert fetcher.calls == []


def test_download_section_assets_keeps_fetch_errors_warning_only_on_non_strict_path(tmp_path: Path) -> None:
    fetcher = RecordingFetcher(download_error=FetchError("direct-download-failed"))
    images = [GalleryImage(url="https://cdn.example/one.jpg", alt="One", position=1)]

    result = download_section_assets(
        fetcher=fetcher,
        images=images,
        output_dir=tmp_path,
        requested_sections=3,
        strict=False,
    )

    assert fetcher.calls == [{"images": images, "output_dir": tmp_path, "requested_sections": 3}]
    assert result.downloaded_besco == []
    assert result.besco_warnings == ["besco_download_failed:direct-download-failed"]
    assert result.besco_files == []
    assert result.besco_filenames_by_section == {}


def test_download_section_assets_raises_runtime_error_on_strict_fetch_error(tmp_path: Path) -> None:
    fetcher = RecordingFetcher(download_error=FetchError("skroutz-download-failed"))
    images = [GalleryImage(url="https://cdn.example/one.jpg", alt="One", position=1)]

    with pytest.raises(RuntimeError) as excinfo:
        download_section_assets(
            fetcher=fetcher,
            images=images,
            output_dir=tmp_path,
            requested_sections=2,
            strict=True,
            strict_expected_count=2,
        )

    assert str(excinfo.value) == "Skroutz besco image download failed: skroutz-download-failed"
    assert fetcher.calls == [{"images": images, "output_dir": tmp_path, "requested_sections": 2}]


def test_download_section_assets_raises_on_strict_incomplete_download(tmp_path: Path) -> None:
    fetcher = RecordingFetcher(
        download_result=(
            [GalleryImage(url="https://cdn.example/one.jpg", alt="One", position=1, local_filename="besco1.jpg")],
            [],
            [str(tmp_path / "bescos" / "besco1.jpg")],
        )
    )
    images = [
        GalleryImage(url="https://cdn.example/one.jpg", alt="One", position=1),
        GalleryImage(url="https://cdn.example/two.jpg", alt="Two", position=2),
    ]

    with pytest.raises(RuntimeError) as excinfo:
        download_section_assets(
            fetcher=fetcher,
            images=images,
            output_dir=tmp_path,
            requested_sections=2,
            strict=True,
            strict_expected_count=2,
        )

    assert str(excinfo.value) == "Skroutz besco image download incomplete: expected 2, downloaded 1"
    assert fetcher.calls == [{"images": images, "output_dir": tmp_path, "requested_sections": 2}]


def test_download_section_assets_returns_files_warnings_and_filename_map_on_success(tmp_path: Path) -> None:
    downloaded = [
        GalleryImage(url="https://cdn.example/one.jpg", alt="One", position=1, local_filename="besco1.jpg"),
        GalleryImage(url="https://cdn.example/three.jpg", alt="Three", position=3, local_filename="besco3.jpg"),
    ]
    fetcher = RecordingFetcher(
        download_result=(
            downloaded,
            ["besco_images_less_than_requested_sections"],
            [str(tmp_path / "bescos" / "besco1.jpg"), str(tmp_path / "bescos" / "besco3.jpg")],
        )
    )
    images = [
        GalleryImage(url="https://cdn.example/one.jpg", alt="One", position=1),
        GalleryImage(url="https://cdn.example/three.jpg", alt="Three", position=3),
    ]

    result = download_section_assets(
        fetcher=fetcher,
        images=images,
        output_dir=tmp_path,
        requested_sections=3,
        strict=False,
    )

    assert fetcher.calls == [{"images": images, "output_dir": tmp_path, "requested_sections": 3}]
    assert result.downloaded_besco == downloaded
    assert result.besco_warnings == ["besco_images_less_than_requested_sections"]
    assert result.besco_files == [str(tmp_path / "bescos" / "besco1.jpg"), str(tmp_path / "bescos" / "besco3.jpg")]
    assert result.besco_filenames_by_section == {1: "besco1.jpg", 3: "besco3.jpg"}


def test_build_section_image_candidates_uses_image_candidates_when_present() -> None:
    blocks = [
        {
            "title": "Alpha",
            "paragraph": "Alpha body",
            "image_candidates": ["https://cdn.example/alpha-a.jpg", "https://cdn.example/alpha-b.jpg"],
            "image_url": "https://cdn.example/alpha-resolved.jpg",
        },
        {
            "title": "Beta",
            "paragraph": "Beta body",
            "image_candidates": [],
            "image_url": "",
        },
    ]

    assert build_section_image_candidates(blocks) == [
        {
            "position": 1,
            "title": "Alpha",
            "candidates": ["https://cdn.example/alpha-a.jpg", "https://cdn.example/alpha-b.jpg"],
        },
        {
            "position": 2,
            "title": "Beta",
            "candidates": [],
        },
    ]


def test_build_section_image_candidates_falls_back_to_image_url_for_manufacturer_blocks() -> None:
    blocks = [
        {"title": "Manufacturer One", "paragraph": "Body 1", "image_url": "https://cdn.example/manufacturer-1.jpg"},
        {"title": "Manufacturer Two", "paragraph": "Body 2", "image_url": ""},
    ]

    assert build_section_image_candidates(blocks) == [
        {
            "position": 1,
            "title": "Manufacturer One",
            "candidates": ["https://cdn.example/manufacturer-1.jpg"],
        },
        {
            "position": 2,
            "title": "Manufacturer Two",
            "candidates": [],
        },
    ]


def test_build_section_image_urls_resolved_only_includes_blocks_with_image_url() -> None:
    blocks = [
        {"title": "Alpha", "paragraph": "Alpha body", "image_url": "https://cdn.example/alpha.jpg"},
        {"title": "Beta", "paragraph": "Beta body", "image_url": ""},
        {"title": "Gamma", "paragraph": "Gamma body", "image_url": "https://cdn.example/gamma.jpg"},
    ]

    assert build_section_image_urls_resolved(blocks) == [
        {
            "position": 1,
            "title": "Alpha",
            "url": "https://cdn.example/alpha.jpg",
        },
        {
            "position": 3,
            "title": "Gamma",
            "url": "https://cdn.example/gamma.jpg",
        },
    ]


def test_build_sections_artifact_payload_preserves_exact_shape_and_target_filenames() -> None:
    section_extraction_window = {
        "candidate_count": 5,
        "duplicate_signatures_skipped": 1,
        "selected_container_index": "rendered_dom",
        "start_anchor": "Περιγραφή",
        "stop_anchor": "Κατασκευαστής",
        "title_signature": ["Alpha", "Gamma"],
    }
    blocks = [
        {
            "title": "Alpha",
            "paragraph": "Alpha body",
            "image_candidates": ["https://cdn.example/alpha-a.jpg", "https://cdn.example/alpha-b.jpg"],
            "image_url": "https://cdn.example/alpha-resolved.jpg",
        },
        {
            "title": "Gamma",
            "paragraph": "Gamma body",
            "image_candidates": ["https://cdn.example/gamma-a.jpg"],
            "image_url": "https://cdn.example/gamma-resolved.jpg",
        },
    ]

    assert build_sections_artifact_payload(
        source="skroutz",
        requested_sections=2,
        section_extraction_window=section_extraction_window,
        blocks=blocks,
    ) == {
        "source": "skroutz",
        "requested_sections": 2,
        "window": section_extraction_window,
        "sections": [
            {
                "position": 1,
                "title": "Alpha",
                "body": "Alpha body",
                "image_candidates": ["https://cdn.example/alpha-a.jpg", "https://cdn.example/alpha-b.jpg"],
                "resolved_image_url": "https://cdn.example/alpha-resolved.jpg",
                "target_filename": "besco1.jpg",
            },
            {
                "position": 2,
                "title": "Gamma",
                "body": "Gamma body",
                "image_candidates": ["https://cdn.example/gamma-a.jpg"],
                "resolved_image_url": "https://cdn.example/gamma-resolved.jpg",
                "target_filename": "besco2.jpg",
            },
        ],
    }
