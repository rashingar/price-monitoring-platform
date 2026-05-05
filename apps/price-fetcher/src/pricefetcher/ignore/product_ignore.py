"""Product-level ignore list backed by a manually editable CSV file."""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pricefetcher.catalog.source_catalog import is_atomic_model
from pricefetcher.env import load_local_env_if_present

DEFAULT_PRICE_IGNORE_PATH = Path(r"C:\Users\user\Downloads\price_ignore.csv")
PRICE_IGNORE_ENV_VAR = "PRICEFETCHER_PRICE_IGNORE_PATH"
IGNORE_REQUIRED_COLUMNS = (
    "model",
    "name",
    "manufacturer",
    "mpn",
    "reason",
    "ignored_at",
    "notes",
)


class MissingIgnoreColumnsError(ValueError):
    """Raised when an existing ignore CSV is missing required columns."""

    def __init__(self, missing_columns: list[str]) -> None:
        self.missing_columns = missing_columns
        super().__init__(f"price_ignore.csv missing required columns: {', '.join(missing_columns)}")


class InvalidIgnoredModelError(ValueError):
    """Raised when an ignore model is empty, composite, or otherwise invalid."""


@dataclass(frozen=True)
class IgnoredProduct:
    model: str
    name: str = ""
    manufacturer: str = ""
    mpn: str = ""
    reason: str = ""
    ignored_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IgnoredProductInput:
    model: str
    name: str = ""
    manufacturer: str = ""
    mpn: str = ""
    reason: str = ""
    ignored_at: str = ""
    notes: str = ""


def resolve_price_ignore_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    load_local_env_if_present()
    env_path = os.environ.get(PRICE_IGNORE_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_PRICE_IGNORE_PATH


def load_ignored_products(path: Path | None = None) -> list[IgnoredProduct]:
    ignore_path = resolve_price_ignore_path(path)
    if not ignore_path.exists():
        return []

    with ignore_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        header_map = {header.strip(): header for header in fieldnames if header is not None}
        missing = [column for column in IGNORE_REQUIRED_COLUMNS if column not in header_map]
        if missing:
            raise MissingIgnoreColumnsError(missing)

        products_by_model: dict[str, IgnoredProduct] = {}
        order: list[str] = []
        for row in reader:
            product = _row_to_ignored_product(row, header_map)
            if not product.model:
                continue
            if product.model not in products_by_model:
                order.append(product.model)
            products_by_model[product.model] = product
        return [products_by_model[model] for model in order]


def is_product_ignored(model: str, path: Path | None = None) -> bool:
    normalized_model = _normalize_model(model)
    if not normalized_model:
        return False
    return any(product.model == normalized_model for product in load_ignored_products(path))


def upsert_ignored_product(entry: IgnoredProductInput, path: Path | None = None) -> IgnoredProduct:
    product = _input_to_ignored_product(entry)
    ignore_path = resolve_price_ignore_path(path)
    existing_products = load_ignored_products(ignore_path)

    updated = False
    next_products: list[IgnoredProduct] = []
    for existing in existing_products:
        if existing.model == product.model:
            if not updated:
                next_products.append(product)
                updated = True
            continue
        next_products.append(existing)
    if not updated:
        next_products.append(product)

    _write_ignored_products(ignore_path, next_products)
    return product


def remove_ignored_product(model: str, path: Path | None = None) -> bool:
    normalized_model = _normalize_model(model)
    if not normalized_model:
        return False

    ignore_path = resolve_price_ignore_path(path)
    if not ignore_path.exists():
        return False

    existing_products = load_ignored_products(ignore_path)
    next_products = [product for product in existing_products if product.model != normalized_model]
    removed = len(next_products) != len(existing_products)
    if removed:
        _write_ignored_products(ignore_path, next_products)
    return removed


def _input_to_ignored_product(entry: IgnoredProductInput) -> IgnoredProduct:
    model = _normalize_model(entry.model)
    if not model:
        raise InvalidIgnoredModelError("model is required")
    if not is_atomic_model(model):
        raise InvalidIgnoredModelError("model must be exactly 6 numeric digits")

    ignored_at = _text(entry.ignored_at) or _now_iso()
    return IgnoredProduct(
        model=model,
        name=_text(entry.name),
        manufacturer=_text(entry.manufacturer),
        mpn=_text(entry.mpn),
        reason=_text(entry.reason),
        ignored_at=ignored_at,
        notes=_text(entry.notes),
    )


def _row_to_ignored_product(row: dict[str, str], header_map: dict[str, str]) -> IgnoredProduct:
    return IgnoredProduct(
        model=_normalize_model(row.get(header_map["model"], "")),
        name=_text(row.get(header_map["name"], "")),
        manufacturer=_text(row.get(header_map["manufacturer"], "")),
        mpn=_text(row.get(header_map["mpn"], "")),
        reason=_text(row.get(header_map["reason"], "")),
        ignored_at=_text(row.get(header_map["ignored_at"], "")),
        notes=_text(row.get(header_map["notes"], "")),
    )


def _write_ignored_products(path: Path, products: list[IgnoredProduct]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(IGNORE_REQUIRED_COLUMNS))
        writer.writeheader()
        for product in products:
            writer.writerow(product.to_dict())


def _normalize_model(model: object) -> str:
    return _text(model)


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
