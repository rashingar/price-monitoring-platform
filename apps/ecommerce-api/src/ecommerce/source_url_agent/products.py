"""Product input readers for Source URL Agent Mode."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecommerce.catalog.source_catalog import DEFAULT_CATALOG_SOURCE
from ecommerce.db.models.catalog import CatalogProductRow


CSV_REQUIRED_COLUMNS = (
    "model",
    "mpn",
    "name",
    "category",
    "manufacturer",
    "price",
    "quantity",
    "status",
    "bestprice_status",
    "skroutz_status",
)


class SourceUrlAgentInputError(ValueError):
    """Raised when source URL agent input cannot be parsed safely."""


@dataclass(frozen=True)
class AgentProduct:
    model: str
    mpn: str
    name: str
    category: str
    manufacturer: str
    price: Decimal | None
    quantity: int | None
    status: int | None
    bestprice_status: int | None
    skroutz_status: int | None
    catalog_product_id: int | None = None
    catalog_source: str = DEFAULT_CATALOG_SOURCE
    raw_row: dict[str, str] = field(default_factory=dict)

    def expected_listing(self, source_name: str) -> str:
        if source_name == "bestprice":
            return _status_hint(self.bestprice_status)
        if source_name == "skroutz":
            return _status_hint(self.skroutz_status)
        return "unknown"

    def to_identity_dict(self) -> dict[str, Any]:
        return {
            "catalog_product_id": self.catalog_product_id,
            "catalog_source": self.catalog_source,
            "model": self.model,
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "product_name": self.name,
            "category": self.category,
            "own_price": str(self.price) if self.price is not None else "",
        }


def read_products_from_csv(
    path: Path,
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    active_only: bool = True,
    limit: int | None = None,
    offset: int = 0,
    model: str | None = None,
) -> list[AgentProduct]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    selected_model = _optional_text(model)
    products: list[AgentProduct] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header_map = _header_map(reader.fieldnames or [])
        missing = [column for column in CSV_REQUIRED_COLUMNS if column not in header_map]
        if missing:
            raise SourceUrlAgentInputError(f"Input CSV missing required columns: {', '.join(missing)}")

        skipped = 0
        for row in reader:
            product = _row_to_product(row, header_map, catalog_source=catalog_source)
            if active_only and product.status != 1:
                continue
            if selected_model and product.model != selected_model:
                continue
            if skipped < max(0, offset):
                skipped += 1
                continue
            products.append(product)
            if limit is not None and len(products) >= max(0, limit):
                break
    return products


def read_products_from_catalog(
    session: Session,
    *,
    catalog_source: str = DEFAULT_CATALOG_SOURCE,
    active_only: bool = True,
    limit: int | None = None,
    offset: int = 0,
    catalog_product_id: int | None = None,
    model: str | None = None,
    selected_models: list[str] | None = None,
) -> list[AgentProduct]:
    statement = select(CatalogProductRow).where(CatalogProductRow.catalog_source == catalog_source)
    if active_only:
        statement = statement.where(CatalogProductRow.active.is_(True), CatalogProductRow.status == 1)
    if catalog_product_id is not None:
        statement = statement.where(CatalogProductRow.id == catalog_product_id)
    selected_model = _optional_text(model)
    if selected_model:
        statement = statement.where(CatalogProductRow.model == selected_model)
    selected_model_set = _normalized_text_set(selected_models or [])
    if selected_model_set:
        statement = statement.where(CatalogProductRow.model.in_(selected_model_set))
    statement = statement.order_by(CatalogProductRow.id.asc()).offset(max(0, offset))
    if limit is not None:
        statement = statement.limit(max(0, limit))
    return [_catalog_row_to_product(row) for row in session.execute(statement).scalars().all()]


def _row_to_product(row: dict[str, str], header_map: dict[str, str], *, catalog_source: str) -> AgentProduct:
    raw = _raw_row(row)
    return AgentProduct(
        catalog_product_id=None,
        catalog_source=catalog_source,
        model=_text(row.get(header_map["model"])),
        mpn=_text(row.get(header_map["mpn"])),
        name=_text(row.get(header_map["name"])),
        category=_text(row.get(header_map["category"])),
        manufacturer=_text(row.get(header_map["manufacturer"])),
        price=_decimal_or_none(row.get(header_map["price"])),
        quantity=_int_or_none(row.get(header_map["quantity"])),
        status=_int_or_none(row.get(header_map["status"])),
        bestprice_status=_int_or_none(row.get(header_map["bestprice_status"])),
        skroutz_status=_int_or_none(row.get(header_map["skroutz_status"])),
        raw_row=raw,
    )


def _catalog_row_to_product(row: CatalogProductRow) -> AgentProduct:
    return AgentProduct(
        catalog_product_id=row.id,
        catalog_source=row.catalog_source,
        model=row.model or "",
        mpn=row.mpn or "",
        name=row.name or "",
        category=row.category or "",
        manufacturer=row.manufacturer or "",
        price=Decimal(str(row.price)) if row.price is not None else None,
        quantity=row.quantity,
        status=row.status,
        bestprice_status=row.bestprice_status,
        skroutz_status=row.skroutz_status,
        raw_row={str(key): str(value or "") for key, value in (row.raw_catalog_row or {}).items()},
    )


def _header_map(fieldnames: list[str]) -> dict[str, str]:
    return {str(fieldname).strip(): fieldname for fieldname in fieldnames if fieldname is not None}


def _raw_row(row: dict[str, str]) -> dict[str, str]:
    return {str(key): value if value is not None else "" for key, value in row.items() if key is not None}


def _status_hint(value: int | None) -> str:
    if value == 1:
        return "listed"
    if value == 0:
        return "not_listed"
    return "unknown"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_text_set(values: list[str]) -> set[str]:
    return {text for value in values if (text := _text(value))}


def _text(value: object) -> str:
    return str(value or "").strip()


def _decimal_or_none(value: object) -> Decimal | None:
    text = _text(value).replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None
