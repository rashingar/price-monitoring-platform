from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .fetcher import ElectronetFetcher, FetchError
from .models import (
    CLIInput,
    FetchResult,
    GalleryImage,
    ParsedProduct,
    SourceProductData,
    SpecItem,
    SpecSection,
)
from .normalize import normalize_whitespace, repair_mojibake_text
from .prepare_provider_resolution import (
    PrepareProviderResolutionResult,
    resolve_prepare_provider_resolution,
    validate_prepare_provider_resolution_result,
)
from .providers.registry import source_to_provider_id
from .source_capture_client import SourceCaptureSyncResult, sync_initial_source_capture
from .source_acquisition_models import SourceAcquisitionResult
from .source_detection import validate_url_scope
from .utils import ensure_directory


def execute_source_acquisition_stage(
    *,
    model: str,
    url: str,
    photos: int,
    model_dir: Path,
    gallery_url: str | None = None,
    characteristics_url: str | None = None,
    second_opencart_image_index: int | None = None,
    gallery_mode: str | None = None,
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]] = validate_url_scope,
    fetcher_factory: Callable[[], ElectronetFetcher] = ElectronetFetcher,
    resolve_prepare_provider_input_fn: Callable[
        ..., PrepareProviderResolutionResult
    ] = resolve_prepare_provider_resolution,
    source_capture_sync_fn: Callable[
        [str, str], SourceCaptureSyncResult
    ] = sync_initial_source_capture,
) -> SourceAcquisitionResult:
    resolved_model_dir = ensure_directory(model_dir)
    fetcher = fetcher_factory()
    provider_resolution, source_capture_warnings, capture_sync = (
        _resolve_provider_for_acquisition_url(
            model=model,
            url=url,
            photos=photos,
            model_dir=resolved_model_dir,
            validate_url_scope_fn=validate_url_scope_fn,
            fetcher=fetcher,
            resolve_prepare_provider_input_fn=resolve_prepare_provider_input_fn,
            source_capture_sync_fn=source_capture_sync_fn,
        )
    )
    if source_capture_warnings:
        provider_resolution.parsed.warnings.extend(source_capture_warnings)
    fetch = provider_resolution.fetch
    parsed = provider_resolution.parsed
    _repair_source_product_text(parsed.source)
    gallery_extraction_url = str(gallery_url or "").strip() or url
    gallery_url_used = bool(str(gallery_url or "").strip())
    gallery_fetch: FetchResult | None = None
    if gallery_url_used:
        (
            gallery_provider_resolution,
            gallery_source_capture_warnings,
            _gallery_capture_sync,
        ) = _resolve_provider_for_acquisition_url(
            model=model,
            url=gallery_extraction_url,
            photos=photos,
            model_dir=resolved_model_dir,
            validate_url_scope_fn=validate_url_scope_fn,
            fetcher=fetcher,
            resolve_prepare_provider_input_fn=resolve_prepare_provider_input_fn,
            source_capture_sync_fn=source_capture_sync_fn,
        )
        gallery_fetch = gallery_provider_resolution.fetch
        _repair_source_product_text(gallery_provider_resolution.parsed.source)
        parsed.source.gallery_images = list(
            gallery_provider_resolution.parsed.source.gallery_images
        )
        if gallery_source_capture_warnings:
            parsed.warnings.extend(
                f"gallery_{warning}" for warning in gallery_source_capture_warnings
            )
    gallery_filter_final_url = (
        gallery_fetch.final_url if gallery_fetch is not None else fetch.final_url
    )
    gallery_extracted_before_source_filter_count = len(parsed.source.gallery_images)
    gallery_images_after_source_filter, gallery_source_filter_metadata = (
        apply_source_specific_gallery_rules(
            parsed.source.gallery_images,
            source_url=gallery_extraction_url,
            final_url=gallery_filter_final_url,
        )
    )
    parsed.source.gallery_images = gallery_images_after_source_filter
    gallery_after_source_filter_count = len(parsed.source.gallery_images)
    characteristics_extraction_url = str(characteristics_url or "").strip() or url
    characteristics_url_used = bool(str(characteristics_url or "").strip())
    characteristics_fetch: FetchResult | None = None
    characteristics_source: SourceProductData | None = None
    if characteristics_url_used:
        (
            characteristics_provider_resolution,
            characteristics_source_capture_warnings,
            _characteristics_capture_sync,
        ) = _resolve_provider_for_acquisition_url(
            model=model,
            url=characteristics_extraction_url,
            photos=photos,
            model_dir=resolved_model_dir,
            validate_url_scope_fn=validate_url_scope_fn,
            fetcher=fetcher,
            resolve_prepare_provider_input_fn=resolve_prepare_provider_input_fn,
            source_capture_sync_fn=source_capture_sync_fn,
        )
        characteristics_fetch = characteristics_provider_resolution.fetch
        characteristics_source = characteristics_provider_resolution.parsed.source
        _repair_source_product_text(characteristics_source)
        if characteristics_source_capture_warnings:
            parsed.warnings.extend(
                f"characteristics_{warning}"
                for warning in characteristics_source_capture_warnings
            )
    extracted_gallery_count = gallery_extracted_before_source_filter_count
    image_order_metadata: dict[str, Any] = {
        "second_opencart_image_index": second_opencart_image_index,
        "second_opencart_image_override_applied": False,
        "deduplicated_gallery_count": None,
    }
    image_order_warnings: list[str] = []
    gallery_images_for_download: list[GalleryImage]
    if second_opencart_image_index is not None:
        reordered_gallery, image_order_metadata, image_order_warnings = (
            apply_second_opencart_image_index(
                parsed.source.gallery_images,
                second_opencart_image_index,
            )
        )
        parsed.source.gallery_images = reordered_gallery
        if image_order_metadata["second_opencart_image_override_applied"]:
            gallery_images_for_download = (
                _inject_energy_label_after_second_opencart_image(parsed.source)
            )
        else:
            gallery_images_for_download = _inject_energy_label_into_gallery(
                parsed.source
            )
    else:
        gallery_images_for_download = _inject_energy_label_into_gallery(parsed.source)
    normalized_gallery_mode = _normalize_gallery_mode(gallery_mode)
    requested_gallery_photos = _resolve_requested_gallery_photos(
        photos,
        parsed.source,
        gallery_mode=normalized_gallery_mode,
    )
    gallery_warnings: list[str] = list(image_order_warnings)
    gallery_files: list[str] = []
    downloaded_gallery: list[GalleryImage] = []
    if gallery_images_for_download:
        try:
            downloaded_gallery, gallery_warnings, gallery_files = (
                fetcher.download_gallery_images(
                    images=gallery_images_for_download,
                    model=model,
                    output_dir=resolved_model_dir,
                    requested_photos=requested_gallery_photos,
                )
            )
            if downloaded_gallery:
                parsed.source.gallery_images = downloaded_gallery
        except FetchError as exc:
            gallery_warnings.append(f"gallery_download_failed:{exc}")

    snapshot_provenance = {
        "requested_url": fetch.url,
        "detected_source": provider_resolution.source,
        "provider_id": provider_resolution.provider_id,
        "final_url": fetch.final_url,
        "status_code": fetch.status_code,
        "fetch_method": fetch.method,
        "fallback_used": fetch.fallback_used,
        "response_headers": dict(fetch.response_headers),
        "gallery_mode": normalized_gallery_mode,
        "gallery_whole_mode": normalized_gallery_mode == "all",
        "gallery_requested_photos": requested_gallery_photos,
        "gallery_downloaded_count": len(downloaded_gallery),
        "gallery_url_used": gallery_url_used,
        "gallery_extraction_url": gallery_extraction_url,
        "gallery_source_filter_url": gallery_extraction_url,
        "gallery_source_filter_final_url": gallery_filter_final_url,
        "gallery_source_filter_domain": gallery_source_filter_metadata["domain"],
        "gallery_source_filter_rule": gallery_source_filter_metadata["rule"],
        "gallery_extracted_before_source_filter_count": gallery_extracted_before_source_filter_count,
        "gallery_after_source_filter_count": gallery_after_source_filter_count,
        "gallery_skroutz_skip_last_applied": gallery_source_filter_metadata[
            "skroutz_skip_last_applied"
        ],
        "gallery_skroutz_skip_last_skipped_url": gallery_source_filter_metadata[
            "skipped_url"
        ],
        "product_data_extraction_url": url,
        "product_data_extraction_uses_main_url": True,
        "characteristics_url_used": characteristics_url_used,
        "characteristics_extraction_url": characteristics_extraction_url,
        "second_opencart_image_index": second_opencart_image_index,
        "second_opencart_image_override_applied": image_order_metadata[
            "second_opencart_image_override_applied"
        ],
        "second_opencart_image_warning": image_order_metadata.get(
            "second_opencart_image_warning"
        ),
        "deduplicated_gallery_count": image_order_metadata[
            "deduplicated_gallery_count"
        ],
    }
    if gallery_fetch is not None:
        snapshot_provenance.update(
            {
                "gallery_fetch_final_url": gallery_fetch.final_url,
                "gallery_fetch_method": gallery_fetch.method,
                "gallery_fetch_status_code": gallery_fetch.status_code,
            }
        )
    if characteristics_fetch is not None:
        snapshot_provenance.update(
            {
                "characteristics_fetch_final_url": characteristics_fetch.final_url,
                "characteristics_fetch_method": characteristics_fetch.method,
                "characteristics_fetch_status_code": characteristics_fetch.status_code,
            }
        )
    if capture_sync.status != "skipped" or fetch.method == "shared_source_capture":
        snapshot_provenance.update(
            {
                "source_capture_sync_status": capture_sync.status,
                "source_capture_sync_message": capture_sync.message,
                "source_capture_payload_used": not source_capture_warnings
                and fetch.method == "shared_source_capture",
                "product_factory_capture_mode": (
                    "shared_source_capture"
                    if fetch.method == "shared_source_capture"
                    else "local_provider_fetch"
                ),
            }
        )

    return SourceAcquisitionResult(
        model_dir=resolved_model_dir,
        source=provider_resolution.source,
        provider_id=provider_resolution.provider_id,
        fetch=fetch,
        parsed=parsed,
        extracted_gallery_count=extracted_gallery_count,
        requested_gallery_photos=requested_gallery_photos,
        downloaded_gallery=downloaded_gallery,
        gallery_warnings=gallery_warnings,
        gallery_files=gallery_files,
        characteristics_source=characteristics_source,
        characteristics_fetch=characteristics_fetch,
        snapshot_provenance=snapshot_provenance,
    )


def _provider_resolution_from_source_capture(
    cli: CLIInput,
    *,
    source: str,
    provider_id: str,
    sync_result: SourceCaptureSyncResult,
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]],
) -> PrepareProviderResolutionResult | None:
    if sync_result.status != "submitted":
        return None

    source_payload = _matching_source_capture_payload(sync_result.payload, cli.url)
    if source_payload is None:
        return None

    product_payload = _normalized_product_payload(source_payload)
    if product_payload is None:
        return None

    source_product = _source_product_data_from_mapping(
        product_payload, source=source, url=cli.url
    )
    if source_product is None:
        return None

    warnings = _source_capture_response_warnings(sync_result.payload)
    parsed = ParsedProduct(
        source=source_product,
        provenance=_string_mapping(
            _first_mapping(product_payload, ("provenance",))
            or source_payload.get("provenance")
        ),
        missing_fields=_string_list(
            product_payload.get("missing_fields")
            or source_payload.get("missing_fields")
        ),
        critical_missing=_string_list(
            product_payload.get("critical_missing")
            or source_payload.get("critical_missing")
        ),
        warnings=warnings,
    )
    fetch = _fetch_result_from_source_capture_payload(
        source_payload, source_product, requested_url=cli.url
    )
    return validate_prepare_provider_resolution_result(
        cli,
        PrepareProviderResolutionResult(
            source=source,
            provider_id=provider_id,
            fetch=fetch,
            parsed=parsed,
        ),
        validate_url_scope_fn=validate_url_scope_fn,
    )


def _matching_source_capture_payload(
    payload: Mapping[str, Any] | None, source_url: str
) -> Mapping[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    candidates: list[Mapping[str, Any]] = []
    sources = payload.get("sources")
    if isinstance(sources, list):
        candidates.extend(item for item in sources if isinstance(item, Mapping))
    candidates.append(payload)
    normalized_source_url = source_url.strip()
    for candidate in candidates:
        urls = [
            candidate.get("url"),
            candidate.get("source_url"),
            candidate.get("requested_url"),
            candidate.get("final_url"),
        ]
        if any(str(item or "").strip() == normalized_source_url for item in urls):
            return candidate
    return candidates[0] if candidates else None


def _normalized_product_payload(
    source_payload: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    direct = _first_mapping(
        source_payload,
        (
            "source_product",
            "source_product_data",
            "normalized_product",
            "normalized_source",
            "parsed_product",
            "product_factory_source",
        ),
    )
    if direct is not None:
        nested_source = direct.get("source")
        return nested_source if isinstance(nested_source, Mapping) else direct

    product = source_payload.get("product")
    if isinstance(product, Mapping):
        nested_source = product.get("source")
        if isinstance(nested_source, Mapping):
            return nested_source
        if _looks_like_source_product(product):
            return product

    if _looks_like_source_product(source_payload):
        return source_payload
    return None


def _fetch_result_from_source_capture_payload(
    source_payload: Mapping[str, Any],
    source_product: SourceProductData,
    *,
    requested_url: str,
) -> FetchResult:
    snapshot = (
        _first_mapping(source_payload, ("snapshot", "capture", "source_snapshot"))
        or source_payload
    )
    response_headers = _string_mapping(
        snapshot.get("response_headers") or snapshot.get("headers")
    )
    return FetchResult(
        url=str(
            snapshot.get("requested_url")
            or source_payload.get("requested_url")
            or requested_url
        ),
        final_url=str(
            snapshot.get("final_url")
            or source_payload.get("final_url")
            or source_product.canonical_url
            or source_product.url
            or requested_url
        ),
        html=str(
            snapshot.get("body_text")
            or snapshot.get("html")
            or snapshot.get("raw_html")
            or source_payload.get("raw_html")
            or ""
        ),
        status_code=_int_value(
            snapshot.get("status_code") or source_payload.get("status_code"),
            default=200,
        ),
        method="shared_source_capture",
        fallback_used=False,
        response_headers=response_headers,
    )


def _source_product_data_from_mapping(
    payload: Mapping[str, Any], *, source: str, url: str
) -> SourceProductData | None:
    if not _looks_like_source_product(payload):
        return None

    field_names = {field.name for field in fields(SourceProductData)}
    values = {key: value for key, value in payload.items() if key in field_names}
    values["source_name"] = str(values.get("source_name") or source)
    values["url"] = str(values.get("url") or url)
    values["canonical_url"] = str(values.get("canonical_url") or values["url"])
    values["page_type"] = str(values.get("page_type") or "product")
    values["product_code"] = str(values.get("product_code") or values.get("code") or "")
    values["brand"] = str(values.get("brand") or "")
    values["name"] = str(values.get("name") or "")
    values["mpn"] = str(values.get("mpn") or "")
    values["gallery_images"] = _gallery_images_from_payload(
        values.get("gallery_images")
    )
    values["besco_images"] = _gallery_images_from_payload(values.get("besco_images"))
    values["key_specs"] = _spec_items_from_payload(values.get("key_specs"))
    values["spec_sections"] = _spec_sections_from_payload(values.get("spec_sections"))
    values["manufacturer_spec_sections"] = _spec_sections_from_payload(
        values.get("manufacturer_spec_sections")
    )
    return SourceProductData(**values)


def _gallery_images_from_payload(value: Any) -> list[GalleryImage]:
    if not isinstance(value, list):
        return []
    images: list[GalleryImage] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        images.append(
            GalleryImage(
                url=str(item.get("url") or ""),
                alt=str(item.get("alt") or ""),
                position=_int_value(item.get("position"), default=len(images) + 1),
                local_filename=str(item.get("local_filename") or ""),
                local_path=str(item.get("local_path") or ""),
                content_type=str(item.get("content_type") or ""),
                downloaded=bool(item.get("downloaded", False)),
            )
        )
    return images


def _spec_items_from_payload(value: Any) -> list[SpecItem]:
    if not isinstance(value, list):
        return []
    items: list[SpecItem] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        items.append(
            SpecItem(
                label=str(item.get("label") or ""),
                value=None if item.get("value") is None else str(item.get("value")),
            )
        )
    return items


def _spec_sections_from_payload(value: Any) -> list[SpecSection]:
    if not isinstance(value, list):
        return []
    sections: list[SpecSection] = []
    for section in value:
        if not isinstance(section, Mapping):
            continue
        sections.append(
            SpecSection(
                section=str(section.get("section") or ""),
                items=_spec_items_from_payload(section.get("items")),
            )
        )
    return sections


def _source_capture_response_warnings(payload: Mapping[str, Any] | None) -> list[str]:
    warnings: list[str] = []
    for source in (payload or {}).get("sources", []):
        if not isinstance(source, Mapping):
            continue
        if source.get("capture_status") == "failed":
            code = str(source.get("error_code") or "CAPTURE_FAILED")
            message = str(source.get("error_message") or "").strip()
            warnings.append(
                f"source_capture_failed:{code}:{message}"
                if message
                else f"source_capture_failed:{code}"
            )
    return warnings


def _first_mapping(payload: Any, keys: tuple[str, ...]) -> Mapping[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _looks_like_source_product(payload: Mapping[str, Any]) -> bool:
    if any(
        key in payload
        for key in (
            "source_name",
            "page_type",
            "spec_sections",
            "gallery_images",
            "taxonomy_source_category",
        )
    ):
        return True
    return bool(
        payload.get("name")
        and (payload.get("brand") or payload.get("mpn") or payload.get("product_code"))
    )


def _inject_energy_label_into_gallery(source: SourceProductData) -> list[GalleryImage]:
    gallery_images = list(getattr(source, "gallery_images", []) or [])
    energy_label_asset_url = str(
        getattr(source, "energy_label_asset_url", "") or ""
    ).strip()
    if not gallery_images or not energy_label_asset_url:
        return gallery_images

    primary_image = gallery_images[0]
    remaining_images = gallery_images[1:]
    injected_images = [
        GalleryImage(
            url=primary_image.url,
            alt=primary_image.alt,
            position=1,
        ),
        GalleryImage(
            url=energy_label_asset_url,
            alt="Energy Label",
            position=2,
        ),
    ]
    for index, image in enumerate(remaining_images, start=3):
        injected_images.append(
            GalleryImage(
                url=image.url,
                alt=image.alt,
                position=index,
            )
        )
    return injected_images


def _inject_energy_label_after_second_opencart_image(
    source: SourceProductData,
) -> list[GalleryImage]:
    gallery_images = list(getattr(source, "gallery_images", []) or [])
    energy_label_asset_url = str(
        getattr(source, "energy_label_asset_url", "") or ""
    ).strip()
    if len(gallery_images) < 2 or not energy_label_asset_url:
        return _inject_energy_label_into_gallery(source)

    injected_images: list[GalleryImage] = []
    for index, image in enumerate(gallery_images[:2], start=1):
        injected_images.append(
            GalleryImage(
                url=image.url,
                alt=image.alt,
                position=index,
            )
        )
    injected_images.append(
        GalleryImage(url=energy_label_asset_url, alt="Energy Label", position=3)
    )
    for index, image in enumerate(gallery_images[2:], start=4):
        injected_images.append(
            GalleryImage(
                url=image.url,
                alt=image.alt,
                position=index,
            )
        )
    return injected_images


def apply_second_opencart_image_index(
    images: list[GalleryImage],
    requested_index: int,
) -> tuple[list[GalleryImage], dict[str, Any], list[str]]:
    deduplicated = _deduplicate_gallery_images(images)
    available_count = len(deduplicated)
    metadata: dict[str, Any] = {
        "second_opencart_image_index": requested_index,
        "deduplicated_gallery_count": available_count,
        "second_opencart_image_override_applied": False,
        "second_opencart_image_warning": None,
    }
    if requested_index < 1:
        warning = f"second_opencart_image_index_invalid:{requested_index}:default_image_order_used"
        metadata["second_opencart_image_warning"] = warning
        return _renumber_gallery_images(deduplicated), metadata, [warning]
    if requested_index > available_count:
        warning = (
            "second_opencart_image_index_out_of_range:"
            f"requested={requested_index}:available={available_count}:default_image_order_used"
        )
        metadata["second_opencart_image_warning"] = warning
        return _renumber_gallery_images(deduplicated), metadata, [warning]
    if requested_index == 1:
        return _renumber_gallery_images(deduplicated), metadata, []

    selected = deduplicated[requested_index - 1]
    remaining = [
        image
        for index, image in enumerate(deduplicated, start=1)
        if index != requested_index
    ]
    reordered = [remaining[0], selected, *remaining[1:]]
    metadata["second_opencart_image_override_applied"] = True
    return _renumber_gallery_images(reordered), metadata, []


def _deduplicate_gallery_images(images: list[GalleryImage]) -> list[GalleryImage]:
    deduplicated: list[GalleryImage] = []
    seen: set[str] = set()
    for image in images:
        url = normalize_whitespace(image.url)
        if not url or url in seen:
            continue
        seen.add(url)
        deduplicated.append(
            GalleryImage(
                url=url,
                alt=image.alt,
                position=image.position,
                local_filename=image.local_filename,
                local_path=image.local_path,
                content_type=image.content_type,
                downloaded=image.downloaded,
            )
        )
    return deduplicated


def _renumber_gallery_images(images: list[GalleryImage]) -> list[GalleryImage]:
    return [
        GalleryImage(
            url=image.url,
            alt=image.alt,
            position=index,
            local_filename=image.local_filename,
            local_path=image.local_path,
            content_type=image.content_type,
            downloaded=image.downloaded,
        )
        for index, image in enumerate(images, start=1)
    ]


def apply_source_specific_gallery_rules(
    images: list[GalleryImage],
    *,
    source_url: str,
    final_url: str = "",
) -> tuple[list[GalleryImage], dict[str, Any]]:
    filter_url = final_url if _is_skroutz_url(final_url) else source_url
    domain = _normalized_domain(filter_url)
    metadata: dict[str, Any] = {
        "domain": domain,
        "rule": "",
        "skroutz_skip_last_applied": False,
        "skipped_url": "",
    }
    if _is_skroutz_url(source_url) or _is_skroutz_url(final_url):
        # The former Skroutz skip-last rule is deprecated: it excluded valid
        # product images before normal download caps, deduplication, and
        # energy-label handling could run.
        return list(images), metadata
    return list(images), metadata


def _resolve_requested_gallery_photos(
    requested_photos: int,
    source: SourceProductData,
    *,
    gallery_mode: str | None = None,
) -> int | None:
    if gallery_mode == "all":
        return None
    requested = max(int(requested_photos), 0)
    if requested <= 0:
        return requested
    if not str(source.energy_label_asset_url or "").strip():
        return requested
    return requested + 1


def _normalize_gallery_mode(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    return "all" if normalized == "all" else None


def _is_skroutz_url(value: str) -> bool:
    domain = _normalized_domain(value)
    return domain in {"skroutz.gr", "skroutz.cy"} or domain.endswith(".skroutz.gr")


def _normalized_domain(value: str) -> str:
    try:
        netloc = urlsplit(value).netloc
    except ValueError:
        return ""
    domain = netloc.split("@")[-1].split(":")[0].lower().strip(".")
    return domain[4:] if domain.startswith("www.") else domain


def _repair_source_product_text(source: SourceProductData) -> None:
    text_fields = (
        "breadcrumbs",
        "category_tag_text",
        "taxonomy_source_category",
        "taxonomy_match_type",
        "taxonomy_rule_id",
        "taxonomy_escalation_reason",
        "product_code",
        "brand",
        "name",
        "hero_summary",
        "price_text",
        "installments_text",
        "delivery_text",
        "pickup_text",
        "manufacturer_source_text",
        "presentation_source_html",
        "presentation_source_text",
        "mpn",
    )
    for field_name in text_fields:
        value = getattr(source, field_name)
        if isinstance(value, str):
            setattr(source, field_name, repair_mojibake_text(value))
        elif isinstance(value, list):
            setattr(
                source,
                field_name,
                [
                    repair_mojibake_text(item) if isinstance(item, str) else item
                    for item in value
                ],
            )

    _repair_gallery_images(source.gallery_images)
    _repair_gallery_images(source.besco_images)
    _repair_spec_items(source.key_specs)
    _repair_spec_sections(source.spec_sections)
    _repair_spec_sections(source.manufacturer_spec_sections)


def _resolve_provider_for_acquisition_url(
    *,
    model: str,
    url: str,
    photos: int,
    model_dir: Path,
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]],
    fetcher: ElectronetFetcher,
    resolve_prepare_provider_input_fn: Callable[..., PrepareProviderResolutionResult],
    source_capture_sync_fn: Callable[[str, str], SourceCaptureSyncResult],
) -> tuple[PrepareProviderResolutionResult, list[str], SourceCaptureSyncResult]:
    acquisition_cli = CLIInput(
        model=model,
        url=url,
        photos=max(int(photos), 0),
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price=0,
        out=str(model_dir),
    )
    detected_source, _scope_ok, _scope_reason = validate_url_scope_fn(url)
    provider_id = source_to_provider_id(detected_source) or detected_source
    source_capture_warnings: list[str] = []
    try:
        capture_sync = source_capture_sync_fn(model, url)
    except Exception as exc:
        capture_sync = SourceCaptureSyncResult(
            status="failed", message=str(exc) or exc.__class__.__name__
        )
    try:
        provider_resolution = _provider_resolution_from_source_capture(
            acquisition_cli,
            source=detected_source,
            provider_id=provider_id,
            sync_result=capture_sync,
            validate_url_scope_fn=validate_url_scope_fn,
        )
    except Exception as exc:
        provider_resolution = None
        source_capture_warnings.append(f"source_capture_payload_unusable:{exc}")
    if provider_resolution is not None:
        return provider_resolution, source_capture_warnings, capture_sync

    # Direct provider fetch remains the canonical local path when shared
    # source capture has not returned a normalized product payload.
    if capture_sync.status == "failed":
        source_capture_warnings.append(
            f"source_capture_sync_failed:{capture_sync.message}"
        )
    elif capture_sync.status == "submitted":
        source_capture_warnings.extend(
            _source_capture_response_warnings(capture_sync.payload)
        )
    return (
        resolve_prepare_provider_input_fn(
            acquisition_cli,
            validate_url_scope_fn=validate_url_scope_fn,
            fetcher_factory=lambda: fetcher,
        ),
        source_capture_warnings,
        capture_sync,
    )


def _repair_gallery_images(images: list[GalleryImage]) -> None:
    for image in images:
        image.alt = repair_mojibake_text(image.alt)


def _repair_spec_items(items: list[SpecItem]) -> None:
    for item in items:
        item.label = repair_mojibake_text(item.label)
        if item.value is not None:
            item.value = repair_mojibake_text(item.value)


def _repair_spec_sections(sections: list[SpecSection]) -> None:
    for section in sections:
        section.section = repair_mojibake_text(section.section)
        _repair_spec_items(section.items)
