"""ERP warehouse CSV lookup for Telegram Product Factory intake."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


OPTIONAL_METADATA_COLUMNS = ("manufacturer", "mpn", "barcode", "category", "price", "quantity")


@dataclass(frozen=True)
class WarehouseProduct:
    model: str
    name: str
    metadata: dict[str, str] = field(default_factory=dict)


class WarehouseCatalogError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def lookup_warehouse_product(
    *,
    path: str | Path | None,
    model: str,
    model_column: str = "model",
    name_column: str = "name",
    encoding: str = "utf-8-sig",
) -> WarehouseProduct:
    if not str(path or "").strip():
        raise WarehouseCatalogError(
            "warehouse_catalog_path_missing",
            "ERP warehouse catalog path is not configured.",
        )
    catalog_path = Path(str(path)).expanduser()
    if catalog_path.suffix.casefold() != ".csv":
        raise WarehouseCatalogError(
            "warehouse_catalog_invalid_csv",
            "ERP warehouse catalog must be a CSV file.",
        )

    try:
        with catalog_path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise WarehouseCatalogError(
                    "warehouse_catalog_invalid_csv",
                    "ERP warehouse catalog CSV is missing a header row.",
                )
            _require_column(reader.fieldnames, model_column, "warehouse_catalog_model_column_missing")
            _require_column(reader.fieldnames, name_column, "warehouse_catalog_name_column_missing")
            matches = _matching_rows(reader, model_column=model_column, model=model)
    except WarehouseCatalogError:
        raise
    except (OSError, LookupError) as exc:
        raise WarehouseCatalogError(
            "warehouse_catalog_unreadable",
            "ERP warehouse catalog file is not readable.",
        ) from exc
    except (UnicodeDecodeError, csv.Error) as exc:
        raise WarehouseCatalogError(
            "warehouse_catalog_invalid_csv",
            "ERP warehouse catalog CSV is invalid.",
        ) from exc

    if not matches:
        raise WarehouseCatalogError(
            "warehouse_catalog_model_not_found",
            f"Model {model} was not found in the ERP warehouse catalog.",
        )
    if len(matches) > 1:
        raise WarehouseCatalogError(
            "warehouse_catalog_duplicate_model",
            f"Model {model} appears more than once in the ERP warehouse catalog.",
        )

    row = matches[0]
    product_name = str(row.get(name_column) or "").strip()
    if not product_name:
        raise WarehouseCatalogError(
            "warehouse_catalog_empty_product_name",
            f"Model {model} has an empty product name in the ERP warehouse catalog.",
        )
    return WarehouseProduct(
        model=model,
        name=product_name,
        metadata=_metadata_from_row(row, model_column=model_column, name_column=name_column),
    )


def _require_column(fieldnames: list[str], column: str, code: str) -> None:
    if column not in fieldnames:
        raise WarehouseCatalogError(code, f"ERP warehouse catalog is missing configured column {column}.")


def _matching_rows(
    reader: csv.DictReader,
    *,
    model_column: str,
    model: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in reader:
        if None in row:
            raise WarehouseCatalogError(
                "warehouse_catalog_invalid_csv",
                "ERP warehouse catalog CSV has rows with an unexpected number of fields.",
            )
        if row.get(model_column) == model:
            matches.append(row)
    return matches


def _metadata_from_row(row: dict[str, Any], *, model_column: str, name_column: str) -> dict[str, str]:
    excluded = {model_column, name_column}
    metadata: dict[str, str] = {}
    for key in OPTIONAL_METADATA_COLUMNS:
        if key in excluded:
            continue
        value = str(row.get(key) or "").strip()
        if value:
            metadata[key] = value
    return metadata
