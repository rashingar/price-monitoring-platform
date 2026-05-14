"""Product, product source, and source snapshot repository helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.vendor_sources import Vendor
from ecommerce.db.models.products import Product, ProductSource, SourceCaptureSnapshot
from ecommerce.db.models.price_monitoring import OfferObservation, PriceObservation
from ecommerce.db.repositories.common import _decimal_or_none, _empty_to_none, _first_text, _json_safe, json_safe_value
from ecommerce.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url
from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_capture.runner import capture_source_url
from ecommerce.source_capture.vendor_registry import VENDORS_BY_SLUG


def upsert_product_from_catalog_row(
    session: Session,
    row: dict[str, Any],
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    updated_at: datetime | None = None,
) -> Product | None:
    model = _empty_to_none(_first_text(row, ("model", "product_model", "sku")))
    mpn = _empty_to_none(_first_text(row, ("mpn", "manufacturer_part_number", "matched_mpn")))
    if not model and not mpn:
        return None

    timestamp = updated_at or _now()
    product = find_product_by_identity(session, catalog_source=catalog_source, model=model, mpn=mpn)
    if product is None:
        product = Product(
            catalog_source=catalog_source,
            model=model,
            mpn=mpn,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(product)
        session.flush()

    product.catalog_source = catalog_source
    product.model = model or product.model
    product.mpn = mpn or product.mpn
    product.name = _empty_to_none(_first_text(row, ("name", "product_name", "title")))
    product.manufacturer = _empty_to_none(_first_text(row, ("manufacturer", "brand")))
    product.family = _empty_to_none(_first_text(row, ("family",)))
    product.category_name = _empty_to_none(_first_text(row, ("category_name", "category")))
    product.sub_category = _empty_to_none(_first_text(row, ("sub_category", "subcategory")))
    product.current_price = _decimal_or_none(_first_text(row, ("own_price", "price", "current_price", "internal_price", "catalog_price")))
    product.currency = _first_text(row, ("currency",)) or "EUR"
    product.active = True
    product.raw_catalog_row = _json_safe(row)
    product.updated_at = timestamp
    return product


def find_product_by_identity(
    session: Session,
    *,
    catalog_source: str,
    model: str | None,
    mpn: str | None,
) -> Product | None:
    if model:
        return session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.model == model).limit(1)
        ).scalar_one_or_none()
    if mpn:
        return session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.mpn == mpn).limit(1)
        ).scalar_one_or_none()
    return None


def match_product_for_observation(
    session: Session,
    *,
    catalog_source: str,
    model: str | None,
    mpn: str | None,
) -> tuple[Product | None, str | None]:
    if model:
        product = session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.model == model).limit(1)
        ).scalar_one_or_none()
        if product is not None:
            return product, "model"
    if mpn:
        product = session.execute(
            select(Product).where(Product.catalog_source == catalog_source, Product.mpn == mpn).limit(1)
        ).scalar_one_or_none()
        if product is not None:
            return product, "mpn"
    return None, None


def product_to_dict(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "catalog_source": product.catalog_source,
        "model": product.model,
        "mpn": product.mpn,
        "name": product.name,
        "manufacturer": product.manufacturer,
        "family": product.family,
        "category_name": product.category_name,
        "sub_category": product.sub_category,
        "current_price": json_safe_value(product.current_price),
        "currency": product.currency,
        "active": product.active,
        "raw_catalog_row": json_safe_value(product.raw_catalog_row),
        "created_at": json_safe_value(product.created_at),
        "updated_at": json_safe_value(product.updated_at),
    }


@dataclass(frozen=True)
class ProductFromSourceResult:
    product: Product
    source_results: list[dict[str, Any]]


def ensure_vendor_rows(session: Session) -> dict[str, Vendor]:
    now = _now()
    existing = {row.slug: row for row in session.execute(select(Vendor)).scalars().all()}
    for slug, definition in VENDORS_BY_SLUG.items():
        row = existing.get(slug)
        if row is None:
            row = Vendor(
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
            session.add(row)
            session.flush()
            existing[slug] = row
            continue
        row.name = definition.name
        row.base_url = definition.base_url
        row.vendor_type = definition.vendor_type
        row.active = definition.active
        row.supports_direct_product_url = definition.supports_direct_product_url
        row.supports_search = definition.supports_search
        row.supports_xhr_capture = definition.supports_xhr_capture
        row.updated_at = now
    session.flush()
    return existing


def find_or_create_product_from_model(
    session: Session,
    *,
    model: str,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    enrichment: dict[str, Any] | None = None,
) -> Product:
    normalized_model = " ".join(str(model or "").split())
    if not normalized_model:
        raise ValueError("model is required.")
    product = find_product_by_identity(session, catalog_source=catalog_source, model=normalized_model, mpn=None)
    now = _now()
    if product is None:
        product = Product(
            catalog_source=catalog_source,
            model=normalized_model,
            currency="EUR",
            active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()
    if enrichment:
        _apply_safe_product_enrichment(product, enrichment)
    product.updated_at = now
    return product


def create_or_reuse_product_source(
    session: Session,
    *,
    product: Product,
    source_url: str,
    confidence_score: Decimal | None = Decimal("1.0"),
) -> tuple[ProductSource, bool]:
    canonical = canonicalize_url(source_url)
    digest = canonical_url_hash(canonical)
    existing = session.execute(
        select(ProductSource).where(
            ProductSource.product_id == product.id,
            ProductSource.canonical_url_hash == digest,
        )
    ).scalar_one_or_none()
    now = _now()
    vendors = ensure_vendor_rows(session)
    vendor_slug = detect_vendor_slug(canonical)
    vendor = vendors.get(vendor_slug or "")
    if existing is not None:
        existing.source_url = source_url.strip()
        existing.canonical_url = canonical
        existing.vendor_id = vendor.id if vendor is not None else existing.vendor_id
        existing.last_seen_at = now
        existing.updated_at = now
        if confidence_score is not None:
            existing.confidence_score = confidence_score
        session.flush()
        from ecommerce.db.repositories.source_convergence import sync_product_source_to_source_url

        sync_product_source_to_source_url(session, existing)
        return existing, False
    row = ProductSource(
        product_id=product.id,
        vendor_id=vendor.id if vendor is not None else None,
        source_url=source_url.strip(),
        canonical_url=canonical,
        canonical_url_hash=digest,
        source_type="direct_product_url",
        active=True,
        confidence_score=confidence_score,
        first_seen_at=now,
        last_seen_at=now,
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    from ecommerce.db.repositories.source_convergence import sync_product_source_to_source_url

    sync_product_source_to_source_url(session, row)
    return row, True


def create_product_from_source_urls(
    session: Session,
    *,
    model: str,
    source_urls: list[str],
    capture: bool = True,
    capture_fn=capture_source_url,
) -> ProductFromSourceResult:
    if not source_urls:
        raise ValueError("source_urls must contain at least one URL.")
    product = find_or_create_product_from_model(session, model=model)
    results: list[dict[str, Any]] = []
    for source_url in source_urls:
        source, created = create_or_reuse_product_source(session, product=product, source_url=source_url)
        if not capture:
            results.append(_source_result_payload(source, "skipped", created, initial_observations=[]))
            continue
        result = capture_fn(source.canonical_url, vendor_slug=_vendor_slug(session, source.vendor_id))
        from ecommerce.db.repositories.capture_persistence import persist_capture_result

        snapshot = persist_capture_result(session, product=product, source=source, result=result)
        observations = _initial_observation_payload(session, snapshot)
        results.append(
            _source_result_payload(
                source,
                result.status,
                created,
                initial_observations=observations,
                error_code=result.error_code,
                error_message=result.error_message,
            )
        )
    return ProductFromSourceResult(product=product, source_results=results)


def product_source_to_dict(row: ProductSource) -> dict[str, Any]:
    return {
        "id": row.id,
        "product_id": row.product_id,
        "vendor_id": row.vendor_id,
        "source_url": row.source_url,
        "canonical_url": row.canonical_url,
        "canonical_url_hash": row.canonical_url_hash,
        "source_type": row.source_type,
        "active": row.active,
        "confidence_score": json_safe_value(row.confidence_score),
        "first_seen_at": json_safe_value(row.first_seen_at),
        "last_seen_at": json_safe_value(row.last_seen_at),
        "last_success_at": json_safe_value(row.last_success_at),
        "last_error_at": json_safe_value(row.last_error_at),
        "last_fetch_status": row.last_fetch_status,
        "last_error_code": row.last_error_code,
        "last_error_message": row.last_error_message,
        "last_parser_version": row.last_parser_version,
        "last_capture_strategy": row.last_capture_strategy,
        "consecutive_failures": row.consecutive_failures,
        "content_hash": row.content_hash,
        "data_quality_flags": row.data_quality_flags or [],
        "created_at": json_safe_value(row.created_at),
        "updated_at": json_safe_value(row.updated_at),
    }


def _source_result_payload(
    source: ProductSource,
    status: str,
    created: bool,
    *,
    initial_observations: list[dict[str, Any]],
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    payload = {
        "source_url": source.source_url,
        "canonical_url": source.canonical_url,
        "vendor": detect_vendor_slug(source.canonical_url),
        "capture_status": status,
        "source_created": created,
        "initial_observations": initial_observations,
        "health": {
            "last_fetch_status": source.last_fetch_status,
            "last_success_at": json_safe_value(source.last_success_at),
            "last_error_at": json_safe_value(source.last_error_at),
            "consecutive_failures": source.consecutive_failures,
            "data_quality_flags": source.data_quality_flags or [],
        },
    }
    if error_code:
        payload["error_code"] = error_code
    if error_message:
        payload["error_message"] = error_message
    return payload


def _initial_observation_payload(session: Session, snapshot: SourceCaptureSnapshot) -> list[dict[str, Any]]:
    prices = session.execute(
        select(PriceObservation).where(PriceObservation.source_capture_snapshot_id == snapshot.id).order_by(PriceObservation.id.asc())
    ).scalars()
    offers = session.execute(
        select(OfferObservation).where(OfferObservation.source_capture_snapshot_id == snapshot.id).order_by(OfferObservation.id.asc())
    ).scalars()
    payload: list[dict[str, Any]] = []
    for row in prices:
        payload.append(
            {
                "type": "price",
                "price": json_safe_value(row.competitor_price),
                "currency": row.currency,
                "availability": row.availability,
                "observed_at": json_safe_value(row.observed_at),
            }
        )
    for row in offers:
        payload.append(
            {
                "type": "offer",
                "seller_name": row.seller_name,
                "price": json_safe_value(row.price),
                "currency": row.currency,
                "availability": row.availability,
                "observed_at": json_safe_value(row.observed_at),
            }
        )
    return payload


def _vendor_slug(session: Session, vendor_id: int | None) -> str | None:
    if vendor_id is None:
        return None
    row = session.get(Vendor, vendor_id)
    return row.slug if row is not None else None


def _apply_safe_product_enrichment(product: Product, enrichment: dict[str, Any]) -> None:
    for source_key, target_key in (("title", "name"), ("name", "name"), ("brand", "manufacturer"), ("manufacturer", "manufacturer")):
        value = _optional_text(enrichment.get(source_key))
        if value and not getattr(product, target_key):
            setattr(product, target_key, value)


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
