from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any, Callable, Mapping

from .fetcher import ElectronetFetcher, FetchError
from .models import CLIInput, FetchResult, GalleryImage, ParsedProduct, SourceProductData, SpecItem, SpecSection
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
    validate_url_scope_fn: Callable[[str], tuple[str, bool, str]] = validate_url_scope,
    fetcher_factory: Callable[[], ElectronetFetcher] = ElectronetFetcher,
    resolve_prepare_provider_input_fn: Callable[..., PrepareProviderResolutionResult] = resolve_prepare_provider_resolution,
    source_capture_sync_fn: Callable[[str, str], SourceCaptureSyncResult] = sync_initial_source_capture,
) -> SourceAcquisitionResult:
    resolved_model_dir = ensure_directory(model_dir)
    fetcher = fetcher_factory()
    acquisition_cli = CLIInput(
        model=model,
        url=url,
        photos=max(int(photos), 0),
        sections=0,
        skroutz_status=0,
        boxnow=0,
        price=0,
        out=str(resolved_model_dir),
    )
    detected_source, _scope_ok, _scope_reason = validate_url_scope_fn(url)
    provider_id = source_to_provider_id(detected_source) or detected_source
    source_capture_warnings: list[str] = []
    try:
        capture_sync = source_capture_sync_fn(model, url)
    except Exception as exc:
        capture_sync = SourceCaptureSyncResult(status="failed", message=str(exc) or exc.__class__.__name__)
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
    if provider_resolution is None:
        # Compatibility fallback: Product-Agent still owns this direct vendor fetch path
        # until shared source-capture can provide a normalized product payload.
        if capture_sync.status == "failed":
            source_capture_warnings.append(f"source_capture_sync_failed:{capture_sync.message}")
        elif capture_sync.status == "submitted":
            source_capture_warnings.extend(_source_capture_response_warnings(capture_sync.payload))
        provider_resolution = resolve_prepare_provider_input_fn(
            acquisition_cli,
            validate_url_scope_fn=validate_url_scope_fn,
            fetcher_factory=lambda: fetcher,
        )
        if source_capture_warnings:
            provider_resolution.parsed.warnings.extend(source_capture_warnings)
    fetch = provider_resolution.fetch
    parsed = provider_resolution.parsed
    extracted_gallery_count = len(parsed.source.gallery_images)
    gallery_images_for_download = _inject_energy_label_into_gallery(parsed.source)
    requested_gallery_photos = _resolve_requested_gallery_photos(photos, parsed.source)
    gallery_warnings: list[str] = []
    gallery_files: list[str] = []
    downloaded_gallery: list[GalleryImage] = []
    if gallery_images_for_download:
        try:
            downloaded_gallery, gallery_warnings, gallery_files = fetcher.download_gallery_images(
                images=gallery_images_for_download,
                model=model,
                output_dir=resolved_model_dir,
                requested_photos=requested_gallery_photos,
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
        "gallery_requested_photos": requested_gallery_photos,
        "gallery_downloaded_count": len(downloaded_gallery),
    }
    if capture_sync.status != "skipped" or fetch.method == "shared_source_capture":
        snapshot_provenance.update(
            {
                "source_capture_sync_status": capture_sync.status,
                "source_capture_sync_message": capture_sync.message,
                "source_capture_payload_used": not source_capture_warnings and fetch.method == "shared_source_capture",
                "product_agent_capture_mode": "shared_source_capture"
                if fetch.method == "shared_source_capture"
                else "compatibility_fallback",
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

    source_product = _source_product_data_from_mapping(product_payload, source=source, url=cli.url)
    if source_product is None:
        return None

    warnings = _source_capture_response_warnings(sync_result.payload)
    parsed = ParsedProduct(
        source=source_product,
        provenance=_string_mapping(_first_mapping(product_payload, ("provenance",)) or source_payload.get("provenance")),
        missing_fields=_string_list(product_payload.get("missing_fields") or source_payload.get("missing_fields")),
        critical_missing=_string_list(product_payload.get("critical_missing") or source_payload.get("critical_missing")),
        warnings=warnings,
    )
    fetch = _fetch_result_from_source_capture_payload(source_payload, source_product, requested_url=cli.url)
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


def _matching_source_capture_payload(payload: Mapping[str, Any] | None, source_url: str) -> Mapping[str, Any] | None:
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


def _normalized_product_payload(source_payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    direct = _first_mapping(
        source_payload,
        (
            "source_product",
            "source_product_data",
            "normalized_product",
            "normalized_source",
            "parsed_product",
            "product_agent_source",
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
    snapshot = _first_mapping(source_payload, ("snapshot", "capture", "source_snapshot")) or source_payload
    response_headers = _string_mapping(snapshot.get("response_headers") or snapshot.get("headers"))
    return FetchResult(
        url=str(snapshot.get("requested_url") or source_payload.get("requested_url") or requested_url),
        final_url=str(
            snapshot.get("final_url")
            or source_payload.get("final_url")
            or source_product.canonical_url
            or source_product.url
            or requested_url
        ),
        html=str(snapshot.get("body_text") or snapshot.get("html") or snapshot.get("raw_html") or source_payload.get("raw_html") or ""),
        status_code=_int_value(snapshot.get("status_code") or source_payload.get("status_code"), default=200),
        method="shared_source_capture",
        fallback_used=False,
        response_headers=response_headers,
    )


def _source_product_data_from_mapping(payload: Mapping[str, Any], *, source: str, url: str) -> SourceProductData | None:
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
    values["gallery_images"] = _gallery_images_from_payload(values.get("gallery_images"))
    values["besco_images"] = _gallery_images_from_payload(values.get("besco_images"))
    values["key_specs"] = _spec_items_from_payload(values.get("key_specs"))
    values["spec_sections"] = _spec_sections_from_payload(values.get("spec_sections"))
    values["manufacturer_spec_sections"] = _spec_sections_from_payload(values.get("manufacturer_spec_sections"))
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
        items.append(SpecItem(label=str(item.get("label") or ""), value=None if item.get("value") is None else str(item.get("value"))))
    return items


def _spec_sections_from_payload(value: Any) -> list[SpecSection]:
    if not isinstance(value, list):
        return []
    sections: list[SpecSection] = []
    for section in value:
        if not isinstance(section, Mapping):
            continue
        sections.append(SpecSection(section=str(section.get("section") or ""), items=_spec_items_from_payload(section.get("items"))))
    return sections


def _source_capture_response_warnings(payload: Mapping[str, Any] | None) -> list[str]:
    warnings: list[str] = []
    for source in (payload or {}).get("sources", []):
        if not isinstance(source, Mapping):
            continue
        if source.get("capture_status") == "failed":
            code = str(source.get("error_code") or "CAPTURE_FAILED")
            message = str(source.get("error_message") or "").strip()
            warnings.append(f"source_capture_failed:{code}:{message}" if message else f"source_capture_failed:{code}")
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
    if any(key in payload for key in ("source_name", "page_type", "spec_sections", "gallery_images", "taxonomy_source_category")):
        return True
    return bool(payload.get("name") and (payload.get("brand") or payload.get("mpn") or payload.get("product_code")))


def _inject_energy_label_into_gallery(source: SourceProductData) -> list[GalleryImage]:
    gallery_images = list(getattr(source, "gallery_images", []) or [])
    energy_label_asset_url = str(getattr(source, "energy_label_asset_url", "") or "").strip()
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


def _resolve_requested_gallery_photos(requested_photos: int, source: SourceProductData) -> int:
    requested = max(int(requested_photos), 0)
    if requested <= 0:
        return requested
    if not str(source.energy_label_asset_url or "").strip():
        return requested
    return requested + 1
