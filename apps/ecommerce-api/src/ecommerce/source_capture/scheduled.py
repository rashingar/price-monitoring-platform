from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.db.models.vendor_sources import Vendor
from ecommerce.db.models.products import Product, ProductSource
from ecommerce.db.repositories.capture_persistence import persist_capture_result
from ecommerce.source_capture.runner import capture_source_url


@dataclass(frozen=True)
class ScheduledCaptureSummary:
    selected_count: int
    succeeded_count: int
    failed_count: int
    items: list[dict[str, Any]]


def capture_due_product_sources(
    session: Session,
    *,
    refresh_after_minutes: int = 360,
    limit: int = 50,
    vendor_slug: str | None = None,
    product_source_ids: list[int] | None = None,
    include_not_due: bool = False,
    run_id: str | None = None,
    observation_batch_id: str | None = None,
    monitoring_run_id: int | None = None,
    capture_fn=capture_source_url,
) -> ScheduledCaptureSummary:
    threshold = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=refresh_after_minutes)
    statement = select(ProductSource).where(ProductSource.active.is_(True))
    if product_source_ids:
        statement = statement.where(ProductSource.id.in_([int(item) for item in product_source_ids]))
    if not include_not_due:
        statement = statement.where((ProductSource.last_success_at.is_(None)) | (ProductSource.last_success_at < threshold))
    if vendor_slug:
        vendor = session.execute(select(Vendor).where(Vendor.slug == vendor_slug)).scalar_one_or_none()
        if vendor is None:
            rows = []
        else:
            statement = statement.where(ProductSource.vendor_id == vendor.id)
            rows = _selected_sources(session, statement, limit)
    else:
        rows = _selected_sources(session, statement, limit)
    items: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0
    for source in rows:
        product = session.get(Product, source.product_id)
        if product is None:
            continue
        vendor_slug = _vendor_slug(session, source.vendor_id)
        result = capture_fn(source.canonical_url, vendor_slug=vendor_slug)
        snapshot = persist_capture_result(
            session,
            product=product,
            source=source,
            result=result,
            run_id=run_id,
            observation_batch_id=observation_batch_id,
            monitoring_run_id=monitoring_run_id,
        )
        if result.successful:
            succeeded += 1
        else:
            failed += 1
        items.append(
            {
                "product_source_id": source.id,
                "product_id": product.id,
                "vendor": vendor_slug or result.vendor_slug,
                "status": result.status,
                "snapshot_id": snapshot.id,
                "error_code": result.error_code,
            }
        )
    return ScheduledCaptureSummary(
        selected_count=len(rows),
        succeeded_count=succeeded,
        failed_count=failed,
        items=items,
    )


def _selected_sources(session: Session, statement, limit: int) -> list[ProductSource]:
    return list(
        session.execute(
            statement.order_by(ProductSource.last_success_at.asc().nullsfirst(), ProductSource.id.asc()).limit(max(1, int(limit)))
        )
        .scalars()
        .all()
    )


def _vendor_slug(session: Session, vendor_id: int | None) -> str | None:
    if vendor_id is None:
        return None
    vendor = session.get(Vendor, vendor_id)
    return vendor.slug if vendor is not None else None
