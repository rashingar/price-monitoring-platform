import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.catalog_db import ingest_source_catalog, list_catalog_products  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.models.catalog import CatalogProductRow  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.price_monitoring.selection import (  # noqa: E402
    PriceMonitoringSelectionRequest,
    select_price_monitoring_products,
)

RAW_COOKWARE = (
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής:::"
    "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής///Γάστρες"
)


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"


def _create_schema(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


def _write_catalog(path: Path, *, name: str = "Product One", second: bool = True) -> None:
    rows = [
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status",
        f"005606,MPN-1,{name},{RAW_COOKWARE},Bosch,123.45,3,1,1,1",
    ]
    if second:
        rows.append("123456,MPN-2,Inactive,Plain,Miele,50.00,0,0,1,1")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8-sig")


def test_ingest_preserves_fields_hierarchy_raw_row_and_leading_zero_model(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)

    with session_scope(database_url) as session:
        result = ingest_source_catalog(session, source_cata_path=catalog_path)
        rows = session.query(CatalogProductRow).order_by(CatalogProductRow.model).all()

    assert result.imported == 2
    assert result.inserted == 2
    row = rows[0]
    assert row.model == "005606"
    assert row.mpn == "MPN-1"
    assert row.name == "Product One"
    assert row.manufacturer == "Bosch"
    assert float(row.price) == 123.45
    assert row.quantity == 3
    assert row.status == 1
    assert row.bestprice_status == 1
    assert row.skroutz_status == 1
    assert row.raw_category == RAW_COOKWARE
    assert row.family == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert row.category_name == "Σκεύη Μαγειρικής"
    assert row.sub_category == "Γάστρες"
    assert row.category_levels == ["ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ", "Σκεύη Μαγειρικής", "Γάστρες"]
    assert row.raw_catalog_row["model"] == "005606"


def test_ingest_upserts_duplicate_model_and_marks_missing_inactive(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)

    with session_scope(database_url) as session:
        first = ingest_source_catalog(session, source_cata_path=catalog_path)
    _write_catalog(catalog_path, name="Updated Product", second=False)
    with session_scope(database_url) as session:
        second = ingest_source_catalog(session, source_cata_path=catalog_path)
        rows = {row.model: row for row in session.query(CatalogProductRow).all()}

    assert first.inserted == 2
    assert second.imported == 1
    assert second.updated == 1
    assert second.inactive_or_missing == 1
    assert rows["005606"].name == "Updated Product"
    assert rows["005606"].active is True
    assert rows["123456"].active is False


def test_price_monitoring_selection_uses_db_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = _sqlite_url(tmp_path)
    monkeypatch.setenv("ECOMMERCE_DATABASE_URL", database_url)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)

    result = select_price_monitoring_products(
        PriceMonitoringSelectionRequest(source="skroutz", selected_models=["005606", "123456"])
    )

    assert [item.model for item in result.items] == ["005606"]
    assert result.skipped[0].model == "123456"
    assert result.skipped[0].reasons == ["inactive"]


def test_list_catalog_products_returns_only_active_by_default(tmp_path: Path) -> None:
    database_url = _sqlite_url(tmp_path)
    _create_schema(database_url)
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)
    _write_catalog(catalog_path, second=False)
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)
        active = list_catalog_products(session)
        all_rows = list_catalog_products(session, active_only=False)

    assert [product.model for product in active] == ["005606"]
    assert {product.model for product in all_rows} == {"005606", "123456"}
