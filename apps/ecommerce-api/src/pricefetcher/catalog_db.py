"""Database-backed active catalog ingestion and queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pricefetcher.catalog import CatalogProduct, DEFAULT_CATALOG_SOURCE, read_source_catalog_records
from pricefetcher.catalog.source_catalog import resolve_source_catalog_path
from pricefetcher.db.models import CatalogProductRow
from pricefetcher.db.session import session_scope


@dataclass(frozen=True)
class CatalogIngestionResult:
    catalog_source: str
    source_path: str
    imported: int
    inserted: int
    updated: int
    inactive_or_missing: int
    skipped_invalid: int
    imported_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_source": self.catalog_source,
            "source_path": self.source_path,
            "imported": self.imported,
            "inserted": self.inserted,
            "updated": self.updated,
            "inactive_or_missing": self.inactive_or_missing,
            "skipped_invalid": self.skipped_invalid,
            "imported_at": self.imported_at,
        }


def ingest_source_catalog(
    session: Session,
    *,
    source_cata_path: Path | None = None,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    imported_at: datetime | None = None,
) -> CatalogIngestionResult:
    resolved_source_path = resolve_source_catalog_path(source_cata_path)
    records = read_source_catalog_records(resolved_source_path)
    timestamp = _timestamp(imported_at)
    source_path = str(resolved_source_path.expanduser().resolve(strict=False))
    source_filename = Path(source_path).name if source_path else None
    imported = 0
    inserted = 0
    updated_count = 0
    skipped_invalid = 0
    seen_models: set[str] = set()

    for record in records:
        product = record.product
        if not product.model:
            skipped_invalid += 1
            continue
        seen_models.add(product.model)
        row = session.execute(
            select(CatalogProductRow).where(
                CatalogProductRow.catalog_source == catalog_source,
                CatalogProductRow.model == product.model,
            )
        ).scalar_one_or_none()
        if row is None:
            row = CatalogProductRow(
                catalog_source=catalog_source,
                model=product.model,
                created_at=timestamp,
                updated_at=timestamp,
                imported_at=timestamp,
            )
            session.add(row)
            inserted += 1
        else:
            updated_count += 1
        _apply_product(row, product, record.raw_row, timestamp, source_path, source_filename)
        imported += 1

    session.flush()
    inactive_or_missing = 0
    if seen_models:
        result = session.execute(
            update(CatalogProductRow)
            .where(
                CatalogProductRow.catalog_source == catalog_source,
                CatalogProductRow.active.is_(True),
                ~CatalogProductRow.model.in_(seen_models),
            )
            .values(active=False, updated_at=timestamp)
        )
        inactive_or_missing = int(result.rowcount or 0)
    else:
        result = session.execute(
            update(CatalogProductRow)
            .where(CatalogProductRow.catalog_source == catalog_source, CatalogProductRow.active.is_(True))
            .values(active=False, updated_at=timestamp)
        )
        inactive_or_missing = int(result.rowcount or 0)

    return CatalogIngestionResult(
        catalog_source=catalog_source,
        source_path=source_path,
        imported=imported,
        inserted=inserted,
        updated=updated_count,
        inactive_or_missing=inactive_or_missing,
        skipped_invalid=skipped_invalid,
        imported_at=timestamp.isoformat(),
    )


def load_active_catalog_products(
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    database_url: str | None = None,
) -> list[CatalogProduct]:
    with session_scope(database_url) as session:
        return list_catalog_products(session, catalog_source=catalog_source, active_only=True)


def list_catalog_products(
    session: Session,
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    active_only: bool = True,
) -> list[CatalogProduct]:
    statement = select(CatalogProductRow).where(CatalogProductRow.catalog_source == catalog_source)
    if active_only:
        statement = statement.where(CatalogProductRow.active.is_(True))
    statement = statement.order_by(CatalogProductRow.id.asc())
    return [_row_to_catalog_product(row) for row in session.execute(statement).scalars().all()]


def count_active_catalog_products(session: Session, *, catalog_source: str = DEFAULT_CATALOG_SOURCE) -> int:
    return int(
        session.execute(
            select(func.count(CatalogProductRow.id)).where(
                CatalogProductRow.catalog_source == catalog_source,
                CatalogProductRow.active.is_(True),
            )
        ).scalar_one()
    )


def latest_active_catalog_imported_at(session: Session, *, catalog_source: str = DEFAULT_CATALOG_SOURCE) -> datetime | None:
    return session.execute(
        select(func.max(CatalogProductRow.imported_at)).where(
            CatalogProductRow.catalog_source == catalog_source,
            CatalogProductRow.active.is_(True),
        )
    ).scalar_one()


def catalog_product_row_to_dict(row: CatalogProductRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "catalog_source": row.catalog_source,
        "model": row.model,
        "mpn": row.mpn,
        "name": row.name,
        "category": row.category,
        "raw_category": row.raw_category,
        "family": row.family,
        "category_name": row.category_name,
        "sub_category": row.sub_category,
        "category_levels": json_safe_value(row.category_levels or []),
        "manufacturer": row.manufacturer,
        "price": json_safe_value(row.price),
        "quantity": row.quantity,
        "status": row.status,
        "bestprice_status": row.bestprice_status,
        "skroutz_status": row.skroutz_status,
        "is_atomic_model": row.is_atomic_model,
        "automation_eligible": row.automation_eligible,
        "active": row.active,
        "imported_at": json_safe_value(row.imported_at),
        "source_path": row.source_path,
        "source_filename": row.source_filename,
        "raw_catalog_row": json_safe_value(row.raw_catalog_row),
        "warnings": json_safe_value(row.warnings or []),
        "created_at": json_safe_value(row.created_at),
        "updated_at": json_safe_value(row.updated_at),
    }


def _apply_product(
    row: CatalogProductRow,
    product: CatalogProduct,
    raw_row: dict[str, str],
    timestamp: datetime,
    source_path: str,
    source_filename: str | None,
) -> None:
    row.mpn = product.mpn
    row.name = product.name
    row.category = product.category
    row.raw_category = product.raw_category
    row.family = product.family
    row.category_name = product.category_name
    row.sub_category = product.sub_category
    row.category_levels = list(product.category_levels)
    row.manufacturer = product.manufacturer
    row.price = _decimal_or_none(product.price)
    row.quantity = product.quantity
    row.status = product.status
    row.bestprice_status = product.bestprice_status
    row.skroutz_status = product.skroutz_status
    row.is_atomic_model = product.is_atomic_model
    row.automation_eligible = product.automation_eligible
    row.active = True
    row.imported_at = timestamp
    row.source_path = source_path or None
    row.source_filename = source_filename
    row.raw_catalog_row = dict(raw_row)
    row.warnings = list(product.warnings)
    row.updated_at = timestamp


def _row_to_catalog_product(row: CatalogProductRow) -> CatalogProduct:
    return CatalogProduct(
        catalog_product_id=row.id,
        model=row.model or "",
        mpn=row.mpn or "",
        name=row.name or "",
        category=row.category or "",
        raw_category=row.raw_category or "",
        family=row.family or "",
        category_name=row.category_name or "",
        sub_category=row.sub_category or "",
        category_levels=_string_list(row.category_levels),
        manufacturer=row.manufacturer or "",
        price=float(row.price) if row.price is not None else None,
        quantity=row.quantity,
        status=row.status,
        bestprice_status=row.bestprice_status,
        skroutz_status=row.skroutz_status,
        is_atomic_model=bool(row.is_atomic_model),
        automation_eligible=bool(row.automation_eligible),
        warnings=_string_list(row.warnings),
    )


def _timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def json_safe_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    return value
