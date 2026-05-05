"""Repository helpers for first-class product sources and capture observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models import OfferObservation, PriceObservation, Product, ProductSource, SourceCaptureSnapshot, Vendor
from ecommerce.db.repositories import find_product_by_identity, json_safe_value, product_to_dict
from ecommerce.db.source_convergence import sync_product_source_to_source_url
from ecommerce.source_capture.canonicalize_url import canonical_url_hash, canonicalize_url
from ecommerce.source_capture.detect_vendor import detect_vendor_slug
from ecommerce.source_capture.runner import capture_source_url
from ecommerce.source_capture.sanitize import content_hash, sanitize_json
from ecommerce.source_capture.types import CaptureResult, ParsedOfferObservation, ParsedPriceObservation
from ecommerce.source_capture.vendor_registry import VENDORS_BY_SLUG


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


def persist_capture_result(
    session: Session,
    *,
    product: Product,
    source: ProductSource,
    result: CaptureResult,
    run_id: str | None = None,
    observation_batch_id: str | None = None,
    monitoring_run_id: int | None = None,
) -> SourceCaptureSnapshot:
    vendor_id = source.vendor_id
    now = _now()
    payload = result.snapshot
    response_text_hash = content_hash(payload.response_body_text or payload.raw_html)
    snapshot = SourceCaptureSnapshot(
        product_id=product.id,
        product_source_id=source.id,
        vendor_id=vendor_id,
        capture_strategy=payload.capture_strategy,
        page_url=payload.page_url,
        final_url=payload.final_url,
        request_url=payload.request_url,
        request_method=payload.request_method,
        response_status=payload.response_status,
        response_content_type=payload.response_content_type,
        response_body_json=sanitize_json(payload.response_body_json) if payload.response_body_json is not None else None,
        response_body_text_ref=_inline_text_ref(payload.response_body_text, kind="response_body_text"),
        raw_html_ref=_inline_text_ref(payload.raw_html, kind="raw_html"),
        artifact_ref=payload.artifact_ref,
        content_hash=payload.content_hash or response_text_hash,
        parser_version=payload.parser_version,
        capture_version=payload.capture_version,
        playwright_version=payload.playwright_version,
        fetch_status_code=payload.fetch_status_code,
        fetch_latency_ms=payload.fetch_latency_ms,
        candidate_score=payload.candidate_score,
        candidate_reason=payload.candidate_reason,
        network_event_type=payload.network_event_type,
        trigger_action=payload.trigger_action,
        data_quality_flags=payload.data_quality_flags,
        error_code=payload.error_code or result.error_code,
        error_message=payload.error_message or result.error_message,
        captured_at=payload.captured_at,
        fetched_at=payload.fetched_at,
        parsed_at=payload.parsed_at,
        imported_at=payload.imported_at,
        created_at=now,
    )
    session.add(snapshot)
    session.flush()
    for observation in result.price_observations:
        session.add(
            _price_observation_row(
                product,
                source,
                snapshot,
                vendor_id,
                result.vendor_slug,
                observation,
                now,
                run_id=run_id,
                observation_batch_id=observation_batch_id,
                monitoring_run_id=monitoring_run_id,
            )
        )
    for observation in result.offer_observations:
        session.add(_offer_observation_row(product, source, snapshot, vendor_id, observation, now, observation_batch_id=observation_batch_id))
    _update_source_health(source, result, snapshot)
    session.flush()
    sync_product_source_to_source_url(session, source)
    return snapshot


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


def _price_observation_row(
    product: Product,
    source: ProductSource,
    snapshot: SourceCaptureSnapshot,
    vendor_id: int | None,
    vendor_slug: str,
    observation: ParsedPriceObservation,
    now: datetime,
    *,
    run_id: str | None = None,
    observation_batch_id: str | None = None,
    monitoring_run_id: int | None = None,
) -> PriceObservation:
    observed_at = snapshot.parsed_at or snapshot.fetched_at or snapshot.captured_at or now
    timestamp_source, timestamp_quality = _observation_timestamp_metadata(
        observation.timestamp_source,
        observation.timestamp_quality,
        snapshot=snapshot,
    )
    return PriceObservation(
        monitoring_run_id=monitoring_run_id,
        product_id=product.id,
        product_source_id=source.id,
        vendor_id=vendor_id,
        source_capture_snapshot_id=snapshot.id,
        run_id=run_id or f"source-capture-{uuid4().hex}",
        observation_batch_id=observation_batch_id,
        catalog_source=product.catalog_source,
        source=vendor_slug,
        model=product.model,
        mpn=product.mpn,
        product_name=observation.product_name or product.name,
        competitor_name=vendor_slug,
        competitor_price=observation.price,
        original_price=observation.original_price,
        discount_percent=observation.discount_percent,
        currency=observation.currency or product.currency or "EUR",
        availability=observation.availability,
        stock_status=observation.stock_status,
        shipping_cost=observation.shipping_cost,
        delivery_text=observation.delivery_text,
        seller_name=observation.seller_name,
        product_url=source.canonical_url,
        raw_observation=observation.raw_observation,
        matched_by="product_source",
        match_status="matched",
        observed_at=observed_at,
        fetched_at=snapshot.fetched_at,
        parsed_at=snapshot.parsed_at,
        timestamp_source=timestamp_source,
        timestamp_quality=timestamp_quality,
        created_at=now,
    )


def _offer_observation_row(
    product: Product,
    source: ProductSource,
    snapshot: SourceCaptureSnapshot,
    vendor_id: int | None,
    observation: ParsedOfferObservation,
    now: datetime,
    *,
    observation_batch_id: str | None = None,
) -> OfferObservation:
    observed_at = snapshot.parsed_at or snapshot.fetched_at or snapshot.captured_at or now
    timestamp_source, timestamp_quality = _observation_timestamp_metadata(
        observation.timestamp_source,
        observation.timestamp_quality,
        snapshot=snapshot,
    )
    return OfferObservation(
        product_id=product.id,
        product_source_id=source.id,
        aggregator_vendor_id=vendor_id,
        source_capture_snapshot_id=snapshot.id,
        observation_batch_id=observation_batch_id,
        seller_name=observation.seller_name,
        seller_url=observation.seller_url,
        price=observation.price,
        original_price=observation.original_price,
        currency=observation.currency,
        availability=observation.availability,
        stock_status=observation.stock_status,
        shipping_cost=observation.shipping_cost,
        delivery_text=observation.delivery_text,
        raw_observation=observation.raw_observation,
        observed_at=observed_at,
        fetched_at=snapshot.fetched_at,
        parsed_at=snapshot.parsed_at,
        timestamp_source=timestamp_source,
        timestamp_quality=timestamp_quality,
        created_at=now,
    )


def _observation_timestamp_metadata(
    timestamp_source: str | None,
    timestamp_quality: str | None,
    *,
    snapshot: SourceCaptureSnapshot,
) -> tuple[str, str]:
    if timestamp_source and timestamp_quality:
        return timestamp_source, timestamp_quality
    if snapshot.parsed_at is not None:
        return timestamp_source or "parsed_at", timestamp_quality or "exact"
    if snapshot.fetched_at is not None:
        return timestamp_source or "fetched_at", timestamp_quality or "exact"
    if snapshot.captured_at is not None:
        return timestamp_source or "captured_at", timestamp_quality or "exact"
    if snapshot.imported_at is not None:
        return timestamp_source or "imported_at", timestamp_quality or "derived"
    return timestamp_source or "created_at", timestamp_quality or "derived"


def _update_source_health(source: ProductSource, result: CaptureResult, snapshot: SourceCaptureSnapshot) -> None:
    now = _now()
    source.last_seen_at = now
    source.last_fetch_status = result.status
    source.last_capture_strategy = snapshot.capture_strategy
    source.last_parser_version = snapshot.parser_version
    source.content_hash = snapshot.content_hash
    source.data_quality_flags = snapshot.data_quality_flags or []
    if result.successful:
        source.last_success_at = now
        source.last_error_code = None
        source.last_error_message = None
        source.consecutive_failures = 0
    else:
        source.last_error_at = now
        source.last_error_code = result.error_code
        source.last_error_message = _short_text(result.error_message)
        source.consecutive_failures = int(source.consecutive_failures or 0) + 1
    source.updated_at = now


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


def _inline_text_ref(text: str | None, *, kind: str, limit: int = 100_000) -> str | None:
    if not text:
        return None
    del limit
    sanitized = _sanitize_text_content(text)
    digest = content_hash(sanitized)
    if digest is None:
        return None
    artifact_dir = Path(os.environ.get("ECOMMERCE_SOURCE_CAPTURE_ARTIFACT_DIR", "output/source_capture/artifacts"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".html" if kind == "raw_html" else ".txt"
    artifact_path = artifact_dir / f"{kind}_{digest}{suffix}"
    if not artifact_path.exists():
        artifact_path.write_text(sanitized, encoding="utf-8")
    return str(artifact_path)


def _sanitize_text_content(text: str) -> str:
    sensitive_markers = ("authorization", "cookie", "set-cookie", "csrf", "token", "session", "password")
    clean_lines: list[str] = []
    for line in str(text).splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in sensitive_markers):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines)


def _short_text(value: object, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
