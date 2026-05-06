from __future__ import annotations

from pathlib import Path

from product_factory.fetcher import FetchError
from product_factory.models import FetchResult, GalleryImage, ParsedProduct, SourceProductData
from product_factory.prepare_provider_resolution import PrepareProviderResolutionResult
from product_factory.source_capture_client import SourceCaptureSyncResult
from product_factory.source_acquisition_stage import execute_source_acquisition_stage


def _build_provider_resolution_result(
    *,
    source: str,
    provider_id: str,
    url: str,
    parsed: ParsedProduct,
    response_headers: dict[str, str] | None = None,
) -> PrepareProviderResolutionResult:
    return PrepareProviderResolutionResult(
        source=source,
        provider_id=provider_id,
        fetch=FetchResult(
            url=url,
            final_url=url,
            html="<html></html>",
            status_code=200,
            method="fixture",
            fallback_used=False,
            response_headers=response_headers or {"content-type": "text/html"},
        ),
        parsed=parsed,
    )


class RecordingFetcher:
    def __init__(
        self,
        *,
        gallery_result: tuple[list[GalleryImage], list[str], list[str]] | None = None,
        gallery_error: Exception | None = None,
    ) -> None:
        self.gallery_result = gallery_result or ([], [], [])
        self.gallery_error = gallery_error
        self.gallery_download_calls: list[dict[str, object]] = []

    def download_gallery_images(self, **kwargs):
        self.gallery_download_calls.append(kwargs)
        if self.gallery_error is not None:
            raise self.gallery_error
        return self.gallery_result


def test_execute_source_acquisition_stage_returns_acquisition_owned_fields_only(tmp_path: Path) -> None:
    model = "233541"
    url = "https://www.electronet.gr/example"
    source = SourceProductData(
        source_name="electronet",
        page_type="product",
        url=url,
        canonical_url=url,
        product_code=model,
        brand="LG",
        mpn="GSGV80PYLL",
        name="LG GSGV80PYLL",
        gallery_images=[
            GalleryImage(url="https://cdn.example/main.jpg", alt="main", position=1),
            GalleryImage(url="https://cdn.example/second.jpg", alt="second", position=2),
        ],
        energy_label_asset_url="https://eprel.ec.europa.eu/labels/example.png",
    )
    parsed = ParsedProduct(source=source)
    downloaded_gallery = [
        GalleryImage(
            url="https://cdn.example/main.jpg",
            alt="main",
            position=1,
            local_filename=f"{model}-1.jpg",
            local_path=str(tmp_path / model / "gallery" / f"{model}-1.jpg"),
            downloaded=True,
        ),
        GalleryImage(
            url="https://eprel.ec.europa.eu/labels/example.png",
            alt="Energy Label",
            position=2,
            local_filename=f"{model}-2.jpg",
            local_path=str(tmp_path / model / "gallery" / f"{model}-2.jpg"),
            downloaded=True,
        ),
        GalleryImage(
            url="https://cdn.example/second.jpg",
            alt="second",
            position=3,
            local_filename=f"{model}-3.jpg",
            local_path=str(tmp_path / model / "gallery" / f"{model}-3.jpg"),
            downloaded=True,
        ),
    ]
    fetcher = RecordingFetcher(gallery_result=(downloaded_gallery, ["gallery_warning"], ["gallery/file1.jpg"]))
    provider_calls: list[tuple[object, dict[str, object]]] = []

    def fake_resolve_prepare_provider_input(cli, **kwargs):
        provider_calls.append((cli, kwargs))
        return _build_provider_resolution_result(
            source="electronet",
            provider_id="electronet",
            url=cli.url,
            parsed=parsed,
            response_headers={"content-type": "text/html", "x-test": "1"},
        )

    result = execute_source_acquisition_stage(
        model=model,
        url=url,
        photos=2,
        model_dir=tmp_path / model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=fake_resolve_prepare_provider_input,
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(status="skipped", message="not configured"),
    )

    assert provider_calls and provider_calls[0][0].model == model
    assert provider_calls[0][0].url == url
    assert provider_calls[0][0].photos == 2
    assert provider_calls[0][0].sections == 0
    assert provider_calls[0][1]["fetcher_factory"]() is fetcher
    assert not hasattr(result, "cli")
    assert result.model_dir == tmp_path / model
    assert result.source == "electronet"
    assert result.provider_id == "electronet"
    assert result.parsed is parsed
    assert result.extracted_gallery_count == 2
    assert result.requested_gallery_photos == 3
    assert result.downloaded_gallery == downloaded_gallery
    assert result.gallery_warnings == ["gallery_warning"]
    assert result.gallery_files == ["gallery/file1.jpg"]
    assert result.parsed.source.gallery_images == downloaded_gallery
    assert len(fetcher.gallery_download_calls) == 1
    assert fetcher.gallery_download_calls[0]["requested_photos"] == 3
    assert [item.position for item in fetcher.gallery_download_calls[0]["images"]] == [1, 2, 3]
    assert [item.url for item in fetcher.gallery_download_calls[0]["images"]] == [
        "https://cdn.example/main.jpg",
        "https://eprel.ec.europa.eu/labels/example.png",
        "https://cdn.example/second.jpg",
    ]
    assert result.snapshot_provenance == {
        "requested_url": url,
        "detected_source": "electronet",
        "provider_id": "electronet",
        "final_url": url,
        "status_code": 200,
        "fetch_method": "fixture",
        "fallback_used": False,
        "response_headers": {"content-type": "text/html", "x-test": "1"},
        "gallery_requested_photos": 3,
        "gallery_downloaded_count": 3,
    }


def test_execute_source_acquisition_stage_keeps_gallery_failure_as_warning_only(tmp_path: Path) -> None:
    model = "233541"
    url = "https://www.electronet.gr/example"
    original_gallery = [GalleryImage(url="https://cdn.example/main.jpg", alt="main", position=1)]
    parsed = ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=url,
            canonical_url=url,
            product_code=model,
            brand="LG",
            mpn="GSGV80PYLL",
            name="LG GSGV80PYLL",
            gallery_images=list(original_gallery),
        )
    )
    fetcher = RecordingFetcher(gallery_error=FetchError("gallery exploded"))

    result = execute_source_acquisition_stage(
        model=model,
        url=url,
        photos=1,
        model_dir=tmp_path / model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli, **_kwargs: _build_provider_resolution_result(
            source="electronet",
            provider_id="electronet",
            url=cli.url,
            parsed=parsed,
        ),
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(status="skipped", message="not configured"),
    )

    assert result.downloaded_gallery == []
    assert result.gallery_files == []
    assert result.gallery_warnings == ["gallery_download_failed:gallery exploded"]
    assert result.extracted_gallery_count == 1
    assert result.requested_gallery_photos == 1
    assert result.parsed.source.gallery_images == original_gallery
    assert result.snapshot_provenance["gallery_downloaded_count"] == 0


def test_execute_source_acquisition_stage_consumes_shared_source_capture_payload_without_provider_fetch(tmp_path: Path) -> None:
    model = "233541"
    url = "https://www.electronet.gr/example"
    fetcher = RecordingFetcher()
    provider_calls = 0

    def provider_resolution(_cli, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider resolution should not run when shared capture supplies normalized data")

    result = execute_source_acquisition_stage(
        model=model,
        url=url,
        photos=0,
        model_dir=tmp_path / model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=provider_resolution,
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="submitted",
            message="Initial source capture submitted.",
            payload={
                "sources": [
                    {
                        "source_url": url,
                        "capture_status": "success",
                        "snapshot": {
                            "requested_url": url,
                            "final_url": url,
                            "status_code": 200,
                            "body_text": "<html>shared</html>",
                            "headers": {"content-type": "text/html; charset=utf-8"},
                        },
                        "source_product": {
                            "source_name": "electronet",
                            "page_type": "product",
                            "url": url,
                            "canonical_url": url,
                            "product_code": model,
                            "brand": "LG",
                            "mpn": "GSGV80PYLL",
                            "name": "LG GSGV80PYLL",
                            "spec_sections": [
                                {
                                    "section": "Χαρακτηριστικά",
                                    "items": [{"label": "Τύπος", "value": "Ψυγειοκαταψύκτης"}],
                                }
                            ],
                        },
                    }
                ]
            },
        ),
    )

    assert provider_calls == 0
    assert result.fetch.method == "shared_source_capture"
    assert result.fetch.html == "<html>shared</html>"
    assert result.parsed.source.name == "LG GSGV80PYLL"
    assert result.parsed.source.spec_sections[0].items[0].value == "Ψυγειοκαταψύκτης"
    assert result.snapshot_provenance["source_capture_sync_status"] == "submitted"
    assert result.snapshot_provenance["source_capture_payload_used"] is True
    assert result.snapshot_provenance["product_factory_capture_mode"] == "shared_source_capture"


def test_execute_source_acquisition_stage_keeps_source_capture_sync_failure_as_warning_only(tmp_path: Path) -> None:
    model = "233541"
    url = "https://www.electronet.gr/example"
    parsed = ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=url,
            canonical_url=url,
            product_code=model,
            brand="LG",
            mpn="GSGV80PYLL",
            name="LG GSGV80PYLL",
        )
    )

    result = execute_source_acquisition_stage(
        model=model,
        url=url,
        photos=0,
        model_dir=tmp_path / model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: RecordingFetcher(),
        resolve_prepare_provider_input_fn=lambda cli, **_kwargs: _build_provider_resolution_result(
            source="electronet",
            provider_id="electronet",
            url=cli.url,
            parsed=parsed,
        ),
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(status="failed", message="connection refused"),
    )

    assert result.parsed is parsed
    assert result.parsed.warnings == ["source_capture_sync_failed:connection refused"]
    assert result.snapshot_provenance["source_capture_sync_status"] == "failed"
    assert result.snapshot_provenance["product_factory_capture_mode"] == "local_provider_fetch"
