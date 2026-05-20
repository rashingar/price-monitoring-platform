"""Read the canonical active product catalog snapshot from sourceCata.csv."""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ecommerce.catalog.category_path import parse_opencart_category
from ecommerce.env import load_local_env_if_present

DEFAULT_SOURCE_CATA_PATH = Path(r"C:\Users\user\Downloads\sourceCata.csv")
DEFAULT_CATALOG_SOURCE = "sourceCata"
SOURCE_CATA_ENV_VAR = "ECOMMERCE_SOURCE_CATA_PATH"
SOURCE_CATA_REQUIRED_COLUMNS = (
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


class MissingCatalogColumnsError(ValueError):
    """Raised when sourceCata.csv is missing required columns."""

    def __init__(self, missing_columns: list[str]) -> None:
        self.missing_columns = missing_columns
        super().__init__(
            f"sourceCata.csv missing required columns: {', '.join(missing_columns)}"
        )


@dataclass(frozen=True)
class CatalogProduct:
    catalog_product_id: int | None
    model: str
    mpn: str
    name: str
    category: str
    raw_category: str
    family: str
    category_name: str
    sub_category: str
    category_levels: list[str]
    manufacturer: str
    price: float | None
    quantity: int | None
    status: int | None
    bestprice_status: int | None
    skroutz_status: int | None
    is_atomic_model: bool
    automation_eligible: bool
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceCatalogRecord:
    product: CatalogProduct
    raw_row: dict[str, str]


def is_atomic_model(model: str) -> bool:
    value = str(model or "").strip()
    return value.isdigit() and len(value) == 6


def resolve_source_catalog_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    load_local_env_if_present()
    env_path = os.environ.get(SOURCE_CATA_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_SOURCE_CATA_PATH


def load_source_catalog(path: Path | None = None) -> list[CatalogProduct]:
    return [record.product for record in read_source_catalog_records(path)]


def read_source_catalog_records(path: Path | None = None) -> list[SourceCatalogRecord]:
    catalog_path = resolve_source_catalog_path(path)
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog file not found: {catalog_path}")

    with catalog_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        header_map = {
            header.strip(): header for header in fieldnames if header is not None
        }
        missing = [
            column
            for column in SOURCE_CATA_REQUIRED_COLUMNS
            if column not in header_map
        ]
        if missing:
            raise MissingCatalogColumnsError(missing)

        records: list[SourceCatalogRecord] = []
        for row in reader:
            product = _row_to_product(row, header_map)
            records.append(SourceCatalogRecord(product=product, raw_row=_raw_row(row)))
        return records


def _row_to_product(row: dict[str, str], header_map: dict[str, str]) -> CatalogProduct:
    model = _text(row.get(header_map["model"], ""))
    mpn = _text(row.get(header_map["mpn"], ""))
    name = _text(row.get(header_map["name"], ""))
    category = _text(row.get(header_map["category"], ""))
    parsed_category = parse_opencart_category(category)
    manufacturer = _text(row.get(header_map["manufacturer"], ""))
    price = _parse_float(row.get(header_map["price"], ""))
    quantity = _parse_int(row.get(header_map["quantity"], ""))
    status = _parse_int(row.get(header_map["status"], ""))
    bestprice_status = _parse_int(row.get(header_map["bestprice_status"], ""))
    skroutz_status = _parse_int(row.get(header_map["skroutz_status"], ""))

    warnings: list[str] = []
    atomic = is_atomic_model(model)
    if not atomic:
        warnings.append("composite_or_invalid_model")
    if not mpn:
        warnings.append("missing_mpn")

    automation_eligible = (
        atomic and status == 1 and price is not None and price > 0 and bool(mpn)
    )

    return CatalogProduct(
        catalog_product_id=None,
        model=model,
        mpn=mpn,
        name=name,
        category=category,
        raw_category=parsed_category.raw,
        family=parsed_category.family,
        category_name=parsed_category.category_name,
        sub_category=parsed_category.sub_category,
        category_levels=parsed_category.levels,
        manufacturer=manufacturer,
        price=price,
        quantity=quantity,
        status=status,
        bestprice_status=bestprice_status,
        skroutz_status=skroutz_status,
        is_atomic_model=atomic,
        automation_eligible=automation_eligible,
        warnings=warnings,
    )


def _raw_row(row: dict[str, str]) -> dict[str, str]:
    return {
        str(key): value if value is not None else ""
        for key, value in row.items()
        if key is not None
    }


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_float(value: object) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return None
