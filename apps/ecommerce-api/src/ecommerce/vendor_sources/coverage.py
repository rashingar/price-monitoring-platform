"""Coverage and health summaries for Vendor Sources."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models import CatalogProductRow, Product, ProductSource, SourceCaptureSnapshot, SourceUrl, Vendor
from ecommerce.db.repositories import json_safe_value
from ecommerce.source_capture.skroutz_network_diagnostic import CAPTURE_STRATEGY as SKROUTZ_NETWORK_DIAGNOSTIC_STRATEGY


SOURCE_URL_STATUSES = ("active", "needs_review", "broken", "disabled", "redirected")


def source_url_summary(session: Session, *, source_name: str | None = None) -> dict[str, Any]:
    normalized_source = _optional_text(source_name)
    source_urls = _source_urls(session, normalized_source)
    product_sources = _product_sources(session, normalized_source)
    source_url_status_counts = Counter(str(row.status or "") for row in source_urls)
    products_with_active = {int(row.catalog_product_id) for row in source_urls if row.status == "active"}
    active_catalog_product_ids = set(
        session.execute(select(CatalogProductRow.id).where(CatalogProductRow.active.is_(True))).scalars().all()
    )
    product_source_health = Counter(_product_source_health(row) for row in product_sources)
    by_source: dict[str, Counter] = defaultdict(Counter)
    for row in source_urls:
        by_source[str(row.source_name or "")][str(row.status or "")] += 1
    return {
        "source_name": normalized_source or None,
        "catalog_product_count": len(active_catalog_product_ids),
        "source_url_count": len(source_urls),
        "active_source_url_count": source_url_status_counts["active"],
        "products_with_active_source_urls": len(products_with_active),
        "products_without_active_source_urls": max(0, len(active_catalog_product_ids) - len(products_with_active)),
        "source_url_status_counts": {status: int(source_url_status_counts[status]) for status in SOURCE_URL_STATUSES},
        "product_source_count": len(product_sources),
        "active_product_source_count": sum(1 for row in product_sources if row.active),
        "product_source_health_counts": dict(sorted(product_source_health.items())),
        "sources": [
            {
                "source_name": source,
                "status_counts": {status: int(counts[status]) for status in SOURCE_URL_STATUSES},
                "source_url_count": sum(counts.values()),
            }
            for source, counts in sorted(by_source.items())
        ],
    }


def source_health_items(
    session: Session,
    *,
    vendor: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_vendor = _optional_text(vendor)
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))
    statement = (
        select(ProductSource, Product, Vendor)
        .join(Product, Product.id == ProductSource.product_id)
        .outerjoin(Vendor, Vendor.id == ProductSource.vendor_id)
        .order_by(ProductSource.updated_at.desc(), ProductSource.id.desc())
    )
    if normalized_vendor:
        statement = statement.where(Vendor.slug == normalized_vendor)
    rows = session.execute(statement.offset(safe_offset).limit(safe_limit)).all()
    items = [
        {
            "product_source_id": source.id,
            "product_id": product.id,
            "model": product.model,
            "mpn": product.mpn,
            "vendor": vendor_row.slug if vendor_row is not None else None,
            "source_url": source.source_url,
            "canonical_url": source.canonical_url,
            "active": source.active,
            "health": _product_source_health(source),
            "last_fetch_status": source.last_fetch_status,
            "last_success_at": json_safe_value(source.last_success_at),
            "last_error_at": json_safe_value(source.last_error_at),
            "last_error_code": source.last_error_code,
            "last_error_message": source.last_error_message,
            "consecutive_failures": int(source.consecutive_failures or 0),
            "data_quality_flags": source.data_quality_flags or [],
            "latest_skroutz_network_diagnostic": _latest_skroutz_network_diagnostic_summary(session, source) if (vendor_row.slug if vendor_row is not None else None) == "skroutz" else None,
            "updated_at": json_safe_value(source.updated_at),
        }
        for source, product, vendor_row in rows
    ]
    return {"items": items, "limit": safe_limit, "offset": safe_offset, "count": len(items)}


def _source_urls(session: Session, source_name: str | None) -> list[SourceUrl]:
    statement = select(SourceUrl).join(CatalogProductRow, CatalogProductRow.id == SourceUrl.catalog_product_id)
    if source_name:
        statement = statement.where(SourceUrl.source_name == source_name)
    return list(session.execute(statement).scalars().all())


def _product_sources(session: Session, vendor: str | None) -> list[ProductSource]:
    statement = select(ProductSource).outerjoin(Vendor, Vendor.id == ProductSource.vendor_id)
    if vendor:
        statement = statement.where(Vendor.slug == vendor)
    return list(session.execute(statement).scalars().all())


def _product_source_health(row: ProductSource) -> str:
    if not row.active:
        return "disabled"
    if row.last_fetch_status == "failed" or row.consecutive_failures:
        return "failing"
    if row.last_fetch_status == "success":
        return "healthy"
    return "unknown"


def _latest_skroutz_network_diagnostic_summary(session: Session, source: ProductSource) -> dict[str, Any] | None:
    if source.id is None:
        return None
    snapshot = session.execute(
        select(SourceCaptureSnapshot)
        .where(
            SourceCaptureSnapshot.product_source_id == source.id,
            SourceCaptureSnapshot.capture_strategy == SKROUTZ_NETWORK_DIAGNOSTIC_STRATEGY,
        )
        .order_by(SourceCaptureSnapshot.created_at.desc(), SourceCaptureSnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if snapshot is None or not isinstance(snapshot.response_body_json, dict):
        return None
    report = snapshot.response_body_json
    return {
        "diagnostic_report_id": snapshot.id,
        "status": report.get("status"),
        "captured_response_count": len(report.get("captured_responses") or []) if isinstance(report.get("captured_responses"), list) else 0,
        "observed_filter_products_url": bool(report.get("observed_filter_products_url")),
        "observed_shops_details_url": bool(report.get("observed_shops_details_url")),
        "best_product_data_endpoint": report.get("product_data_candidate_url"),
        "classifications_summary": report.get("classifications_summary") if isinstance(report.get("classifications_summary"), dict) else {},
        "created_at": json_safe_value(snapshot.created_at),
    }


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip().lower()
    return text or None
