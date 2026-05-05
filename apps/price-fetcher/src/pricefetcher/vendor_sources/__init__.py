"""Vendor Sources capability surface for discovery and capture workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MARKETPLACE_VENDOR_TYPES = {"marketplace", "marketplace_or_aggregator"}


@dataclass(frozen=True)
class VendorSourceCapability:
    source_name: str
    source_domain: str
    source_type: str
    discovery_enabled: bool
    capture_enabled: bool
    capture_implemented: bool
    supports_search: bool
    supports_direct_product_url: bool
    supports_xhr_capture: bool
    expected_listing_field: str | None
    rate_limit_seconds: float
    notes: str
    ui_default_enabled: bool

    def to_dict(self) -> dict:
        return asdict(self)


def list_vendor_source_capabilities() -> list[dict]:
    from pricefetcher.source_url_agent.sources import load_source_registry

    registry = load_source_registry()
    return [_source_capability(source).to_dict() for source in registry.sources.values()]


def _source_capability(source: Any) -> VendorSourceCapability:
    from pricefetcher.source_capture.runner import CAPTURE_IMPLEMENTED_VENDOR_SLUGS
    from pricefetcher.source_capture.vendor_registry import VENDORS_BY_SLUG

    vendor = VENDORS_BY_SLUG.get(source.source_name)
    capture_implemented = source.source_name in CAPTURE_IMPLEMENTED_VENDOR_SLUGS
    capture_enabled = bool(vendor and vendor.active and capture_implemented)
    source_type = _normalized_source_type(source.source_type, vendor.vendor_type if vendor else None)
    notes = _capability_notes(
        source.notes,
        source_name=source.source_name,
        vendor_active=bool(vendor and vendor.active),
        capture_implemented=capture_implemented,
    )
    return VendorSourceCapability(
        source_name=source.source_name,
        source_domain=source.source_domain,
        source_type=source_type,
        discovery_enabled=bool(source.enabled),
        capture_enabled=capture_enabled,
        capture_implemented=capture_implemented,
        supports_search=bool(source.public_search_url_templates) or bool(vendor and vendor.supports_search),
        supports_direct_product_url=bool(source.product_url_patterns) or bool(vendor and vendor.supports_direct_product_url),
        supports_xhr_capture=bool(vendor and vendor.supports_xhr_capture and capture_implemented),
        expected_listing_field=source.expected_listing_field,
        rate_limit_seconds=float(source.rate_limit_seconds),
        notes=notes,
        ui_default_enabled=bool(source.enabled),
    )


def _normalized_source_type(source_type: str, vendor_type: str | None) -> str:
    value = (source_type or vendor_type or "").strip().lower()
    if value in MARKETPLACE_VENDOR_TYPES:
        return "marketplace"
    return "direct_vendor"


def _capability_notes(
    source_notes: str,
    *,
    source_name: str,
    vendor_active: bool,
    capture_implemented: bool,
) -> str:
    notes = [source_notes.strip()] if source_notes.strip() else []
    if not capture_implemented:
        if vendor_active:
            notes.append(f"{source_name} source capture is registered but not implemented.")
        else:
            notes.append(f"{source_name} is discovery-only; source capture is not enabled or implemented.")
    return " ".join(notes)
