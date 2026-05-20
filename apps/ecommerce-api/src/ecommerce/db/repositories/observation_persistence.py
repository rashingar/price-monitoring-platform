"""Persistence helpers for source capture observation rows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ecommerce.db.models.products import Product, ProductSource, SourceCaptureSnapshot
from ecommerce.db.models.price_monitoring import (
    OfferObservation,
    PriceObservation,
    PriceObservationListing,
)
from ecommerce.source_capture.sanitize import sanitize_json
from ecommerce.source_capture.types import (
    ParsedOfferObservation,
    ParsedPriceObservation,
)


def price_observation_row(
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
    observed_at = (
        snapshot.parsed_at or snapshot.fetched_at or snapshot.captured_at or now
    )
    timestamp_source, timestamp_quality = observation_timestamp_metadata(
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
        competitor_name=observation.seller_name or vendor_slug,
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


def offer_observation_row(
    product: Product,
    source: ProductSource,
    snapshot: SourceCaptureSnapshot,
    vendor_id: int | None,
    observation: ParsedOfferObservation,
    now: datetime,
    *,
    observation_batch_id: str | None = None,
) -> OfferObservation:
    observed_at = (
        snapshot.parsed_at or snapshot.fetched_at or snapshot.captured_at or now
    )
    timestamp_source, timestamp_quality = observation_timestamp_metadata(
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


def add_price_observation_listings(
    session: Session,
    price_observation: PriceObservation,
    *,
    product: Product,
    source: ProductSource,
    snapshot: SourceCaptureSnapshot,
    vendor_id: int | None,
    vendor_slug: str,
    offers: tuple[ParsedOfferObservation, ...],
    now: datetime,
    observation_batch_id: str | None,
) -> None:
    observed_at = (
        snapshot.parsed_at or snapshot.fetched_at or snapshot.captured_at or now
    )
    for rank, offer in enumerate(rank_parsed_offer_observations(offers), start=1):
        if offer.price is None or offer.price <= 0:
            continue
        session.add(
            PriceObservationListing(
                price_observation_id=price_observation.id,
                monitoring_run_id=price_observation.monitoring_run_id,
                run_id=price_observation.run_id,
                observation_batch_id=observation_batch_id,
                product_id=product.id,
                product_source_id=source.id,
                source_capture_snapshot_id=snapshot.id,
                vendor_id=vendor_id,
                source=vendor_slug,
                rank=rank,
                seller_name=offer.seller_name,
                seller_url=offer.seller_url,
                price=offer.price,
                original_price=offer.original_price,
                currency=offer.currency or product.currency or "EUR",
                availability=offer.availability,
                stock_status=offer.stock_status,
                shipping_cost=offer.shipping_cost,
                delivery_text=offer.delivery_text,
                product_url=source.canonical_url,
                raw_listing=sanitize_json(offer.raw_observation or {}),
                observed_at=observed_at,
                created_at=now,
            )
        )


def rank_parsed_offer_observations(
    offers: tuple[ParsedOfferObservation, ...],
) -> list[ParsedOfferObservation]:
    valid = [offer for offer in offers if offer.price is not None and offer.price > 0]
    if any(parsed_offer_rank(offer) is not None for offer in valid):
        return sorted(
            valid,
            key=lambda offer: (
                parsed_offer_rank(offer) or 1_000_000,
                offer.price or Decimal("0"),
                (offer.seller_name or "").casefold(),
            ),
        )
    return sorted(
        valid,
        key=lambda offer: (
            offer.price or Decimal("0"),
            (offer.seller_name or "").casefold(),
            offer.seller_url or "",
        ),
    )


def parsed_offer_rank(offer: ParsedOfferObservation) -> int | None:
    raw = offer.raw_observation if isinstance(offer.raw_observation, dict) else {}
    for key in ("rank", "position", "index", "listing_rank"):
        value = raw.get(key)
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def price_observation_from_offer(
    offer: ParsedOfferObservation,
) -> ParsedPriceObservation:
    raw = dict(offer.raw_observation or {})
    raw.setdefault("persistence_source", "offer_observation_primary_bridge")
    return ParsedPriceObservation(
        price=offer.price,
        original_price=offer.original_price,
        currency=offer.currency,
        availability=offer.availability,
        stock_status=offer.stock_status,
        shipping_cost=offer.shipping_cost,
        delivery_text=offer.delivery_text,
        seller_name=offer.seller_name,
        raw_observation=raw,
        timestamp_source=offer.timestamp_source,
        timestamp_quality=offer.timestamp_quality,
    )


def observation_timestamp_metadata(
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
