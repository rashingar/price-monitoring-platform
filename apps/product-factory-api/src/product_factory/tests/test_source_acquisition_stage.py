from __future__ import annotations

from pathlib import Path

from product_factory.fetcher import FetchError
from product_factory.models import (
    FetchResult,
    GalleryImage,
    ParsedProduct,
    SourceProductData,
    SpecItem,
    SpecSection,
)
from product_factory.prepare_provider_resolution import PrepareProviderResolutionResult
from product_factory.source_capture_client import SourceCaptureSyncResult
from product_factory.source_acquisition_stage import (
    _repair_source_product_text,
    apply_second_opencart_image_index,
    apply_source_specific_gallery_rules,
    execute_source_acquisition_stage,
)


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


def _make_cp1253_utf8_mojibake(text: str) -> str:
    chars: list[str] = []
    for byte in text.encode("utf-8"):
        try:
            chars.append(bytes([byte]).decode("cp1253"))
        except UnicodeDecodeError:
            chars.append(chr(byte))
    return "".join(chars)


def test_repair_source_product_text_repairs_fields_and_nested_source_data() -> None:
    broken_power = _make_cp1253_utf8_mojibake("Ισχύς")
    broken_max_power = _make_cp1253_utf8_mojibake("Μέγιστη Ισχύς")
    broken_section = _make_cp1253_utf8_mojibake("Χαρακτηριστικά")
    source = SourceProductData(
        source_name="electronet",
        page_type="product",
        url="https://www.electronet.gr/example",
        canonical_url="https://www.electronet.gr/example",
        breadcrumbs=[broken_section, broken_power],
        brand=broken_power,
        name=broken_max_power,
        hero_summary=broken_section,
        gallery_images=[
            GalleryImage(
                url="https://cdn.example/main.jpg", alt=broken_power, position=1
            )
        ],
        besco_images=[
            GalleryImage(
                url="https://cdn.example/besco.jpg", alt=broken_max_power, position=1
            )
        ],
        key_specs=[SpecItem(label=broken_power, value=broken_max_power)],
        spec_sections=[
            SpecSection(
                section=broken_section,
                items=[SpecItem(label=broken_power, value=broken_max_power)],
            )
        ],
        manufacturer_spec_sections=[
            SpecSection(
                section=broken_section,
                items=[SpecItem(label=broken_power, value=broken_max_power)],
            )
        ],
        presentation_source_text=broken_max_power,
        mpn=broken_power,
    )

    _repair_source_product_text(source)

    assert source.breadcrumbs == ["Χαρακτηριστικά", "Ισχύς"]
    assert source.brand == "Ισχύς"
    assert source.name == "Μέγιστη Ισχύς"
    assert source.hero_summary == "Χαρακτηριστικά"
    assert source.presentation_source_text == "Μέγιστη Ισχύς"
    assert source.mpn == "Ισχύς"
    assert source.gallery_images[0].alt == "Ισχύς"
    assert source.besco_images[0].alt == "Μέγιστη Ισχύς"
    assert source.key_specs[0].label == "Ισχύς"
    assert source.key_specs[0].value == "Μέγιστη Ισχύς"
    assert source.spec_sections[0].section == "Χαρακτηριστικά"
    assert source.spec_sections[0].items[0].label == "Ισχύς"
    assert source.spec_sections[0].items[0].value == "Μέγιστη Ισχύς"
    assert source.manufacturer_spec_sections[0].section == "Χαρακτηριστικά"
    assert source.manufacturer_spec_sections[0].items[0].label == "Ισχύς"
    assert source.manufacturer_spec_sections[0].items[0].value == "Μέγιστη Ισχύς"


def test_execute_source_acquisition_stage_returns_acquisition_owned_fields_only(
    tmp_path: Path,
) -> None:
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
            GalleryImage(
                url="https://cdn.example/second.jpg", alt="second", position=2
            ),
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
    fetcher = RecordingFetcher(
        gallery_result=(downloaded_gallery, ["gallery_warning"], ["gallery/file1.jpg"])
    )
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
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="skipped", message="not configured"
        ),
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
    assert [item.position for item in fetcher.gallery_download_calls[0]["images"]] == [
        1,
        2,
        3,
    ]
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
        "gallery_mode": None,
        "gallery_whole_mode": False,
        "gallery_requested_photos": 3,
        "gallery_downloaded_count": 3,
        "gallery_url_used": False,
        "gallery_extraction_url": url,
        "gallery_source_filter_url": url,
        "gallery_source_filter_final_url": url,
        "gallery_source_filter_domain": "electronet.gr",
        "gallery_source_filter_rule": "",
        "gallery_extracted_before_source_filter_count": 2,
        "gallery_after_source_filter_count": 2,
        "gallery_skroutz_skip_last_applied": False,
        "gallery_skroutz_skip_last_skipped_url": "",
        "product_data_extraction_url": url,
        "product_data_extraction_uses_main_url": True,
        "characteristics_url_used": False,
        "characteristics_extraction_url": url,
        "second_opencart_image_index": None,
        "second_opencart_image_override_applied": False,
        "second_opencart_image_warning": None,
        "deduplicated_gallery_count": None,
    }


def test_execute_source_acquisition_stage_keeps_gallery_failure_as_warning_only(
    tmp_path: Path,
) -> None:
    model = "233541"
    url = "https://www.electronet.gr/example"
    original_gallery = [
        GalleryImage(url="https://cdn.example/main.jpg", alt="main", position=1)
    ]
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
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="skipped", message="not configured"
        ),
    )

    assert result.downloaded_gallery == []
    assert result.gallery_files == []
    assert result.gallery_warnings == ["gallery_download_failed:gallery exploded"]
    assert result.extracted_gallery_count == 1
    assert result.requested_gallery_photos == 1
    assert result.parsed.source.gallery_images == original_gallery
    assert result.snapshot_provenance["gallery_downloaded_count"] == 0


def test_execute_source_acquisition_stage_uses_gallery_url_only_for_gallery_images(
    tmp_path: Path,
) -> None:
    model = "233541"
    main_url = "https://www.electronet.gr/main-product"
    gallery_url = "https://www.electronet.gr/gallery-product"
    main_parsed = ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=main_url,
            canonical_url=main_url,
            product_code=model,
            brand="LG",
            mpn="MAIN-MPN",
            name="Main Product",
            gallery_images=[
                GalleryImage(
                    url="https://cdn.example/main-a.jpg", alt="main", position=1
                )
            ],
        )
    )
    gallery_parsed = ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=gallery_url,
            canonical_url=gallery_url,
            product_code="999999",
            brand="Other",
            mpn="GALLERY-MPN",
            name="Gallery Product",
            gallery_images=[
                GalleryImage(
                    url="https://cdn.example/gallery-a.jpg", alt="gallery a", position=1
                ),
                GalleryImage(
                    url="https://cdn.example/gallery-b.jpg", alt="gallery b", position=2
                ),
            ],
        )
    )
    fetcher = RecordingFetcher()
    provider_urls: list[str] = []

    def fake_resolve_prepare_provider_input(cli, **_kwargs):
        provider_urls.append(cli.url)
        parsed = gallery_parsed if cli.url == gallery_url else main_parsed
        return _build_provider_resolution_result(
            source="electronet",
            provider_id="electronet",
            url=cli.url,
            parsed=parsed,
        )

    result = execute_source_acquisition_stage(
        model=model,
        url=main_url,
        photos=2,
        model_dir=tmp_path / model,
        gallery_url=gallery_url,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=fake_resolve_prepare_provider_input,
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="skipped", message="not configured"
        ),
    )

    assert provider_urls == [main_url, gallery_url]
    assert result.parsed is main_parsed
    assert result.parsed.source.name == "Main Product"
    assert result.parsed.source.mpn == "MAIN-MPN"
    assert result.extracted_gallery_count == 2
    assert [image.url for image in fetcher.gallery_download_calls[0]["images"]] == [
        "https://cdn.example/gallery-a.jpg",
        "https://cdn.example/gallery-b.jpg",
    ]
    assert result.snapshot_provenance["gallery_url_used"] is True
    assert result.snapshot_provenance["gallery_extraction_url"] == gallery_url
    assert result.snapshot_provenance["product_data_extraction_url"] == main_url
    assert result.snapshot_provenance["product_data_extraction_uses_main_url"] is True


def test_execute_source_acquisition_stage_gallery_mode_all_removes_download_cap(
    tmp_path: Path,
) -> None:
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
            gallery_images=[
                GalleryImage(url="https://cdn.example/1.jpg", position=1),
                GalleryImage(url="https://cdn.example/2.jpg", position=2),
                GalleryImage(url="https://cdn.example/3.jpg", position=3),
            ],
        )
    )
    fetcher = RecordingFetcher()

    result = execute_source_acquisition_stage(
        model=model,
        url=url,
        photos=1,
        gallery_mode="all",
        model_dir=tmp_path / model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli, **_kwargs: _build_provider_resolution_result(
            source="electronet",
            provider_id="electronet",
            url=cli.url,
            parsed=parsed,
        ),
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="skipped", message="not configured"
        ),
    )

    assert fetcher.gallery_download_calls[0]["requested_photos"] is None
    assert [image.url for image in fetcher.gallery_download_calls[0]["images"]] == [
        "https://cdn.example/1.jpg",
        "https://cdn.example/2.jpg",
        "https://cdn.example/3.jpg",
    ]
    assert result.snapshot_provenance["gallery_mode"] == "all"
    assert result.snapshot_provenance["gallery_whole_mode"] is True


def test_apply_source_specific_gallery_rules_skroutz_source_url_skips_last_image() -> (
    None
):
    images = [
        GalleryImage(url="https://cdn.example/1.jpg", position=1),
        GalleryImage(url="https://cdn.example/2.jpg", position=2),
        GalleryImage(url="https://cdn.example/3.jpg", position=3),
    ]

    filtered, metadata = apply_source_specific_gallery_rules(
        images,
        source_url="https://www.skroutz.gr/s/123456/example.html",
    )

    assert [image.url for image in filtered] == [
        "https://cdn.example/1.jpg",
        "https://cdn.example/2.jpg",
    ]
    assert metadata["domain"] == "skroutz.gr"
    assert metadata["rule"] == "skroutz_skip_last_gallery_image"
    assert metadata["skroutz_skip_last_applied"] is True
    assert metadata["skipped_url"] == "https://cdn.example/3.jpg"


def test_apply_source_specific_gallery_rules_skroutz_single_image_keeps_image() -> None:
    images = [GalleryImage(url="https://cdn.example/1.jpg", position=1)]

    filtered, metadata = apply_source_specific_gallery_rules(
        images,
        source_url="https://www.skroutz.gr/s/123456/example.html",
    )

    assert [image.url for image in filtered] == ["https://cdn.example/1.jpg"]
    assert metadata["rule"] == "skroutz_skip_last_gallery_image"
    assert metadata["skroutz_skip_last_applied"] is False
    assert metadata["skipped_url"] == ""


def test_apply_source_specific_gallery_rules_manual_skroutz_url_skips_last_image() -> (
    None
):
    images = [
        GalleryImage(url="https://cdn.example/1.jpg"),
        GalleryImage(url="https://cdn.example/2.jpg"),
    ]

    filtered, metadata = apply_source_specific_gallery_rules(
        images,
        source_url="https://skroutz.cy/s/123456/example.html",
    )

    assert [image.url for image in filtered] == ["https://cdn.example/1.jpg"]
    assert metadata["domain"] == "skroutz.cy"
    assert metadata["skroutz_skip_last_applied"] is True


def test_apply_source_specific_gallery_rules_non_skroutz_source_does_not_skip_last_image() -> (
    None
):
    images = [
        GalleryImage(url="https://cdn.example/1.jpg"),
        GalleryImage(url="https://cdn.example/2.jpg"),
    ]

    filtered, metadata = apply_source_specific_gallery_rules(
        images,
        source_url="https://www.electronet.gr/example",
    )

    assert [image.url for image in filtered] == [
        "https://cdn.example/1.jpg",
        "https://cdn.example/2.jpg",
    ]
    assert metadata["domain"] == "electronet.gr"
    assert metadata["rule"] == ""
    assert metadata["skroutz_skip_last_applied"] is False


def test_execute_source_acquisition_stage_skroutz_enabled_non_skroutz_url_does_not_skip_last_image(
    tmp_path: Path,
) -> None:
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
            gallery_images=[
                GalleryImage(url="https://cdn.example/1.jpg", position=1),
                GalleryImage(url="https://cdn.example/2.jpg", position=2),
            ],
        )
    )
    fetcher = RecordingFetcher()

    result = execute_source_acquisition_stage(
        model=model,
        url=url,
        photos=2,
        model_dir=tmp_path / model,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=lambda cli, **_kwargs: _build_provider_resolution_result(
            source="electronet",
            provider_id="electronet",
            url=cli.url,
            parsed=parsed,
        ),
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="skipped", message="not configured"
        ),
    )

    assert [image.url for image in fetcher.gallery_download_calls[0]["images"]] == [
        "https://cdn.example/1.jpg",
        "https://cdn.example/2.jpg",
    ]
    assert result.snapshot_provenance["gallery_skroutz_skip_last_applied"] is False
    assert (
        result.snapshot_provenance["gallery_extracted_before_source_filter_count"] == 2
    )
    assert result.snapshot_provenance["gallery_after_source_filter_count"] == 2


def test_execute_source_acquisition_stage_uses_characteristics_url_only_for_specs(
    tmp_path: Path,
) -> None:
    model = "233541"
    main_url = "https://www.electronet.gr/main-product"
    characteristics_url = "https://www.electronet.gr/spec-product"
    main_parsed = ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=main_url,
            canonical_url=main_url,
            product_code=model,
            brand="LG",
            mpn="MAIN-MPN",
            name="Main Product",
            price_text="199,00",
            price_value=199.0,
            gallery_images=[
                GalleryImage(
                    url="https://cdn.example/main-a.jpg", alt="main", position=1
                )
            ],
        )
    )
    characteristics_parsed = ParsedProduct(
        source=SourceProductData(
            source_name="electronet",
            page_type="product",
            url=characteristics_url,
            canonical_url=characteristics_url,
            product_code="999999",
            brand="Other",
            mpn="SPECS-MPN",
            name="Specs Product",
            price_text="999,00",
            price_value=999.0,
            gallery_images=[
                GalleryImage(
                    url="https://cdn.example/specs-gallery.jpg",
                    alt="specs gallery",
                    position=1,
                )
            ],
            key_specs=[],
            spec_sections=[
                SpecSection(
                    section="Specs", items=[SpecItem(label="Capacity", value="10Lt")]
                ),
            ],
        )
    )
    fetcher = RecordingFetcher()
    provider_urls: list[str] = []

    def fake_resolve_prepare_provider_input(cli, **_kwargs):
        provider_urls.append(cli.url)
        parsed = (
            characteristics_parsed if cli.url == characteristics_url else main_parsed
        )
        return _build_provider_resolution_result(
            source="electronet",
            provider_id="electronet",
            url=cli.url,
            parsed=parsed,
        )

    result = execute_source_acquisition_stage(
        model=model,
        url=main_url,
        photos=1,
        model_dir=tmp_path / model,
        characteristics_url=characteristics_url,
        validate_url_scope_fn=lambda _url: ("electronet", True, "electronet_domain"),
        fetcher_factory=lambda: fetcher,
        resolve_prepare_provider_input_fn=fake_resolve_prepare_provider_input,
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="skipped", message="not configured"
        ),
    )

    assert provider_urls == [main_url, characteristics_url]
    assert result.parsed is main_parsed
    assert result.parsed.source.name == "Main Product"
    assert result.parsed.source.price_value == 199.0
    assert [image.url for image in fetcher.gallery_download_calls[0]["images"]] == [
        "https://cdn.example/main-a.jpg",
    ]
    assert result.characteristics_source is characteristics_parsed.source
    assert result.characteristics_fetch is not None
    assert result.characteristics_fetch.url == characteristics_url
    assert result.characteristics_source.spec_sections[0].items[0].value == "10Lt"
    assert result.snapshot_provenance["characteristics_url_used"] is True
    assert (
        result.snapshot_provenance["characteristics_extraction_url"]
        == characteristics_url
    )
    assert result.snapshot_provenance["gallery_url_used"] is False
    assert result.snapshot_provenance["gallery_extraction_url"] == main_url


def test_apply_second_opencart_image_index_moves_selected_after_deduplication() -> None:
    images = [
        GalleryImage(url="https://cdn.example/a.jpg", alt="A", position=1),
        GalleryImage(url="https://cdn.example/b.jpg", alt="B", position=2),
        GalleryImage(url="https://cdn.example/b.jpg", alt="B duplicate", position=3),
        GalleryImage(url="https://cdn.example/c.jpg", alt="C", position=4),
        GalleryImage(url="https://cdn.example/d.jpg", alt="D", position=5),
    ]

    reordered, metadata, warnings = apply_second_opencart_image_index(images, 4)

    assert [image.url for image in reordered] == [
        "https://cdn.example/a.jpg",
        "https://cdn.example/d.jpg",
        "https://cdn.example/b.jpg",
        "https://cdn.example/c.jpg",
    ]
    assert [image.position for image in reordered] == [1, 2, 3, 4]
    assert metadata["deduplicated_gallery_count"] == 4
    assert metadata["second_opencart_image_override_applied"] is True
    assert warnings == []


def test_apply_second_opencart_image_index_one_keeps_order_without_duplicates() -> None:
    images = [
        GalleryImage(url="https://cdn.example/a.jpg", position=1),
        GalleryImage(url="https://cdn.example/a.jpg", position=2),
        GalleryImage(url="https://cdn.example/b.jpg", position=3),
    ]

    reordered, metadata, warnings = apply_second_opencart_image_index(images, 1)

    assert [image.url for image in reordered] == [
        "https://cdn.example/a.jpg",
        "https://cdn.example/b.jpg",
    ]
    assert metadata["second_opencart_image_override_applied"] is False
    assert warnings == []


def test_apply_second_opencart_image_index_out_of_range_warns_and_keeps_default_order() -> (
    None
):
    images = [
        GalleryImage(url="https://cdn.example/a.jpg", position=1),
        GalleryImage(url="https://cdn.example/b.jpg", position=2),
    ]

    reordered, metadata, warnings = apply_second_opencart_image_index(images, 4)

    assert [image.url for image in reordered] == [
        "https://cdn.example/a.jpg",
        "https://cdn.example/b.jpg",
    ]
    assert metadata["second_opencart_image_override_applied"] is False
    assert metadata["deduplicated_gallery_count"] == 2
    assert warnings == [
        "second_opencart_image_index_out_of_range:requested=4:available=2:default_image_order_used"
    ]


def test_execute_source_acquisition_stage_consumes_shared_source_capture_payload_without_provider_fetch(
    tmp_path: Path,
) -> None:
    model = "233541"
    url = "https://www.electronet.gr/example"
    fetcher = RecordingFetcher()
    provider_calls = 0

    def provider_resolution(_cli, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError(
            "provider resolution should not run when shared capture supplies normalized data"
        )

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
                                    "items": [
                                        {"label": "Τύπος", "value": "Ψυγειοκαταψύκτης"}
                                    ],
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
    assert (
        result.snapshot_provenance["product_factory_capture_mode"]
        == "shared_source_capture"
    )


def test_execute_source_acquisition_stage_keeps_source_capture_sync_failure_as_warning_only(
    tmp_path: Path,
) -> None:
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
        source_capture_sync_fn=lambda _model, _url: SourceCaptureSyncResult(
            status="failed", message="connection refused"
        ),
    )

    assert result.parsed is parsed
    assert result.parsed.warnings == ["source_capture_sync_failed:connection refused"]
    assert result.snapshot_provenance["source_capture_sync_status"] == "failed"
    assert (
        result.snapshot_provenance["product_factory_capture_mode"]
        == "local_provider_fetch"
    )
