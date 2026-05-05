import csv
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.ignore.product_ignore import (  # noqa: E402
    IGNORE_REQUIRED_COLUMNS,
    IgnoredProductInput,
    InvalidIgnoredModelError,
    MissingIgnoreColumnsError,
    is_product_ignored,
    load_ignored_products,
    remove_ignored_product,
    upsert_ignored_product,
)


def test_loading_missing_ignore_csv_returns_empty_list(tmp_path: Path) -> None:
    assert load_ignored_products(tmp_path / "missing.csv") == []


def test_upsert_creates_ignore_csv_with_headers_and_preserves_leading_zeroes(tmp_path: Path) -> None:
    ignore_path = tmp_path / "price_ignore.csv"

    product = upsert_ignored_product(
        IgnoredProductInput(model=" 005606 ", name=" Product ", manufacturer=" Bosch ", mpn=" MPN-1 "),
        ignore_path,
    )

    assert product.model == "005606"
    assert product.name == "Product"
    assert product.manufacturer == "Bosch"
    assert product.mpn == "MPN-1"
    assert product.ignored_at

    with ignore_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        assert next(reader) == list(IGNORE_REQUIRED_COLUMNS)


def test_rejecting_composite_bundle_model_on_create(tmp_path: Path) -> None:
    with pytest.raises(InvalidIgnoredModelError, match="exactly 6 numeric digits"):
        upsert_ignored_product(IgnoredProductInput(model="233374-233203"), tmp_path / "price_ignore.csv")


def test_upserting_duplicate_model_replaces_existing_row(tmp_path: Path) -> None:
    ignore_path = tmp_path / "price_ignore.csv"
    upsert_ignored_product(IgnoredProductInput(model="005606", reason="old"), ignore_path)
    upsert_ignored_product(IgnoredProductInput(model=" 005606 ", reason="new", notes="updated"), ignore_path)

    products = load_ignored_products(ignore_path)

    assert len(products) == 1
    assert products[0].model == "005606"
    assert products[0].reason == "new"
    assert products[0].notes == "updated"


def test_deleting_ignored_product(tmp_path: Path) -> None:
    ignore_path = tmp_path / "price_ignore.csv"
    upsert_ignored_product(IgnoredProductInput(model="005606"), ignore_path)

    assert is_product_ignored("005606", ignore_path)
    assert remove_ignored_product(" 005606 ", ignore_path)
    assert not is_product_ignored("005606", ignore_path)
    assert not remove_ignored_product("005606", ignore_path)


def test_existing_ignore_csv_missing_required_columns_is_reported(tmp_path: Path) -> None:
    ignore_path = tmp_path / "price_ignore.csv"
    ignore_path.write_text("model,name\n005606,Product\n", encoding="utf-8-sig")

    with pytest.raises(MissingIgnoreColumnsError) as exc_info:
        load_ignored_products(ignore_path)

    assert "manufacturer" in exc_info.value.missing_columns
    assert "notes" in exc_info.value.missing_columns
