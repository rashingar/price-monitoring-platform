"""OpenCart price update CSV export for reviewed Price Monitoring rows."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ecommerce.catalog.source_catalog import is_atomic_model
from ecommerce.ignore.product_ignore import load_ignored_products
from ecommerce.price_monitoring.review import PriceReviewError, PriceReviewRow, _money_text

OPENCART_PRICE_UPDATE_COLUMNS = ["model", "price"]


@dataclass(frozen=True)
class PriceExportResult:
    run_id: str
    output_path: Path
    rows_exported: int
    columns: list[str]


def export_price_update_csv(
    run_dir: Path,
    reviewed_rows: list[PriceReviewRow],
    output_path: Path | None = None,
) -> PriceExportResult:
    """Write a manual OpenCart price update CSV from reviewed rows."""

    run_dir = Path(run_dir)
    output = Path(output_path) if output_path is not None else run_dir / "opencart_price_update.csv"
    ignored_models = {product.model for product in load_ignored_products()}
    export_rows: list[dict[str, str]] = []

    for row in reviewed_rows:
        if row.selected_action not in {"match_price", "undercut"}:
            continue
        if row.model in ignored_models:
            continue
        if not is_atomic_model(row.model):
            continue
        if row.target_price is None or row.target_price <= 0:
            continue
        export_rows.append({"model": row.model, "price": _money_text(row.target_price)})

    if not export_rows:
        raise PriceReviewError("No exportable price update rows.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OPENCART_PRICE_UPDATE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(export_rows)

    return PriceExportResult(
        run_id=run_dir.name,
        output_path=output,
        rows_exported=len(export_rows),
        columns=OPENCART_PRICE_UPDATE_COLUMNS.copy(),
    )
