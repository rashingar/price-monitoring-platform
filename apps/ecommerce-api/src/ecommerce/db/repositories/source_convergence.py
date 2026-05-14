"""Convergence helpers for catalog source URLs and product sources."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.catalog import CatalogProductRow
from ecommerce.db.models.source_urls import SourceUrl
from ecommerce.db.models.vendor_sources import Vendor
from ecommerce.db.models.products import Product, ProductSource
from ecommerce.db.repositories.products import upsert_product_from_catalog_row
from ecommerce.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url
from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_capture.vendor_registry import VENDORS_BY_SLUG
from ecommerce.source_urls import extract_source_domain, infer_source_name, normalize_source_url

SOURCE_URL_CAPTURE_TRUST_LEVELS = {"manual", "high_confidence", "reviewed"}


def sync_source_url_to_product_source(session: Session, source_url: SourceUrl) -> ProductSource | None:
    """Mirror an accepted catalog source URL into product_sources for capture."""

    catalog_product = session.get(CatalogProductRow, source_url.catalog_product_id)
    if catalog_product is None:
        return None

    product = upsert_product_from_catalog_row(
        session,
        _catalog_product_payload(catalog_product),
        catalog_source=catalog_product.catalog_source,
        updated_at=_timestamp(source_url.updated_at),
    )
    if product is None:
        return None

    canonical = canonicalize_url(source_url.url_normalized or source_url.url)
    digest = canonical_url_hash(canonical)
    product_source = session.execute(
        select(ProductSource).where(
            ProductSource.product_id == product.id,
            ProductSource.canonical_url_hash == digest,
        )
    ).scalar_one_or_none()

    now = _now()
    active = source_url.status == "active"
    vendor = _vendor_for_url(session, canonical)
    seen_at = _timestamp(source_url.last_seen_at or source_url.updated_at or now)
    success_at = _timestamp_or_none(source_url.last_success_at)
    confidence = _confidence_for_source_url(source_url)

    if product_source is None:
        if not active:
            return None
        product_source = ProductSource(
            product_id=product.id,
            vendor_id=vendor.id if vendor is not None else None,
            source_url=source_url.url.strip(),
            canonical_url=canonical,
            canonical_url_hash=digest,
            source_type="direct_product_url",
            active=True,
            confidence_score=confidence,
            first_seen_at=_timestamp(source_url.created_at or now),
            last_seen_at=seen_at,
            last_success_at=success_at,
            consecutive_failures=max(0, int(source_url.failure_count or 0)),
            created_at=_timestamp(source_url.created_at or now),
            updated_at=now,
        )
        session.add(product_source)
        session.flush()
        return product_source

    product_source.source_url = source_url.url.strip()
    product_source.canonical_url = canonical
    product_source.vendor_id = vendor.id if vendor is not None else product_source.vendor_id
    product_source.active = active
    product_source.last_seen_at = _newer_datetime(product_source.last_seen_at, seen_at)
    product_source.last_success_at = _newer_datetime(product_source.last_success_at, success_at)
    if confidence is not None:
        product_source.confidence_score = confidence
    product_source.consecutive_failures = max(int(product_source.consecutive_failures or 0), int(source_url.failure_count or 0))
    product_source.updated_at = now
    session.flush()
    return product_source if active else None


def sync_product_source_to_source_url(session: Session, product_source: ProductSource) -> SourceUrl | None:
    """Mirror a product_source into source_urls when it maps to a catalog product."""

    product = session.get(Product, product_source.product_id)
    if product is None:
        return None
    catalog_product = _catalog_product_for_product(session, product)
    if catalog_product is None:
        return None

    canonical = canonicalize_url(product_source.canonical_url or product_source.source_url)
    normalized = normalize_source_url(canonical)
    existing = session.execute(
        select(SourceUrl).where(
            SourceUrl.catalog_product_id == catalog_product.id,
            SourceUrl.url_normalized == normalized,
        )
    ).scalar_one_or_none()

    now = _now()
    vendor = session.get(Vendor, product_source.vendor_id) if product_source.vendor_id is not None else None
    domain = extract_source_domain(normalized)
    source_name = vendor.slug if vendor is not None else infer_source_name(domain)
    status = "active" if product_source.active else "disabled"

    if existing is None:
        existing = SourceUrl(
            catalog_product_id=catalog_product.id,
            catalog_source=catalog_product.catalog_source,
            model=catalog_product.model,
            mpn=catalog_product.mpn or "",
            manufacturer=catalog_product.manufacturer or "",
            source_name=source_name,
            source_domain=domain,
            url=product_source.source_url.strip() or canonical,
            url_normalized=normalized,
            status=status,
            url_type="imported",
            trust_level="product_source",
            added_by="product_source_sync",
            last_seen_at=_timestamp_or_none(product_source.last_seen_at),
            last_success_at=_timestamp_or_none(product_source.last_success_at),
            last_error=_short_text(product_source.last_error_message) if product_source.last_error_message else None,
            failure_count=max(0, int(product_source.consecutive_failures or 0)),
            created_at=_timestamp(product_source.created_at or now),
            updated_at=now,
        )
        session.add(existing)
        session.flush()
        return existing

    existing.catalog_source = catalog_product.catalog_source
    existing.model = catalog_product.model
    existing.mpn = catalog_product.mpn or ""
    existing.manufacturer = catalog_product.manufacturer or ""
    existing.source_name = source_name
    existing.source_domain = domain
    existing.url = product_source.source_url.strip() or canonical
    existing.url_normalized = normalized
    if existing.status != "disabled" or not product_source.active:
        existing.status = status
    if existing.url_type != "manual":
        existing.url_type = "imported"
        existing.trust_level = existing.trust_level or "product_source"
    existing.last_seen_at = _newer_datetime(existing.last_seen_at, _timestamp_or_none(product_source.last_seen_at))
    existing.last_success_at = _newer_datetime(existing.last_success_at, _timestamp_or_none(product_source.last_success_at))
    if product_source.last_error_message:
        existing.last_error = _short_text(product_source.last_error_message)
    existing.failure_count = max(int(existing.failure_count or 0), int(product_source.consecutive_failures or 0))
    existing.updated_at = now
    session.flush()
    return existing


def _catalog_product_for_product(session: Session, product: Product) -> CatalogProductRow | None:
    if product.model:
        row = session.execute(
            select(CatalogProductRow).where(
                CatalogProductRow.catalog_source == product.catalog_source,
                CatalogProductRow.model == product.model,
                CatalogProductRow.active.is_(True),
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    if product.mpn:
        return session.execute(
            select(CatalogProductRow)
            .where(
                CatalogProductRow.catalog_source == product.catalog_source,
                CatalogProductRow.mpn == product.mpn,
                CatalogProductRow.active.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
    return None


def _vendor_for_url(session: Session, url: str) -> Vendor | None:
    slug = detect_vendor_slug(url)
    if not slug:
        return None
    vendor = session.execute(select(Vendor).where(Vendor.slug == slug)).scalar_one_or_none()
    definition = VENDORS_BY_SLUG.get(slug)
    if definition is None:
        return vendor
    now = _now()
    if vendor is None:
        vendor = Vendor(
            slug=definition.slug,
            name=definition.name,
            base_url=definition.base_url,
            vendor_type=definition.vendor_type,
            active=definition.active,
            supports_direct_product_url=definition.supports_direct_product_url,
            supports_search=definition.supports_search,
            supports_xhr_capture=definition.supports_xhr_capture,
            created_at=now,
            updated_at=now,
        )
        session.add(vendor)
        session.flush()
        return vendor
    vendor.name = definition.name
    vendor.base_url = definition.base_url
    vendor.vendor_type = definition.vendor_type
    vendor.active = definition.active
    vendor.supports_direct_product_url = definition.supports_direct_product_url
    vendor.supports_search = definition.supports_search
    vendor.supports_xhr_capture = definition.supports_xhr_capture
    vendor.updated_at = now
    session.flush()
    return vendor


def _catalog_product_payload(row: CatalogProductRow) -> dict[str, Any]:
    return {
        "model": row.model,
        "mpn": row.mpn,
        "name": row.name,
        "manufacturer": row.manufacturer,
        "family": row.family,
        "category_name": row.category_name,
        "sub_category": row.sub_category,
        "price": row.price,
        "currency": "EUR",
        "catalog_product_id": row.id,
    }


def _confidence_for_source_url(source_url: SourceUrl) -> Decimal | None:
    if source_url.trust_level in SOURCE_URL_CAPTURE_TRUST_LEVELS:
        return Decimal("1.0")
    if source_url.status == "active":
        return Decimal("0.8")
    return None


def _timestamp(value: datetime | None) -> datetime:
    if value is None:
        return _now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _timestamp_or_none(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _newer_datetime(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    current_cmp = current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)
    candidate_cmp = candidate if candidate.tzinfo is not None else candidate.replace(tzinfo=timezone.utc)
    return candidate if candidate_cmp > current_cmp else current


def _short_text(value: object, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
