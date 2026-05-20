import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.catalog.source_catalog import (  # noqa: E402
    MissingCatalogColumnsError,
    is_atomic_model,
    load_source_catalog,
)


def _write_catalog(path: Path) -> None:
    path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        "005606, MPN-1 , Product One , Cat A , Bosch ,123.45,3,1,1,0\n"
        " 123456 ,MPN-2,Product Two,Cat B,Miele,0,0,1,1,1\n"
        "233374-233203,,Bundle Product,Cat A,Bosch,50.00,2,1,0,0\n",
        encoding="utf-8-sig",
    )


def test_load_source_catalog_reads_comma_utf8_sig_and_preserves_leading_zeroes(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)

    products = load_source_catalog(catalog_path)

    assert products[0].model == "005606"
    assert products[0].mpn == "MPN-1"
    assert products[0].name == "Product One"
    assert products[0].category == "Cat A"
    assert products[0].raw_category == "Cat A"
    assert products[0].family == "Cat A"
    assert products[0].category_name == ""
    assert products[0].sub_category == ""
    assert products[0].category_levels == ["Cat A"]
    assert products[0].manufacturer == "Bosch"
    assert products[0].price == 123.45
    assert products[0].quantity == 3
    assert products[0].status == 1
    assert products[0].bestprice_status == 1
    assert products[0].skroutz_status == 0
    assert products[0].is_atomic_model
    assert products[0].automation_eligible
    assert products[0].warnings == []


def test_load_source_catalog_adds_parsed_category_fields(tmp_path: Path) -> None:
    raw_category = (
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::"
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής:::"
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Σκεύη Μαγειρικής///Γάστρες"
    )
    catalog_path = tmp_path / "sourceCata.csv"
    catalog_path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        f"005606,MPN-1,Product One,{raw_category},Bosch,123.45,3,1,1,1\n",
        encoding="utf-8-sig",
    )

    product = load_source_catalog(catalog_path)[0]

    assert product.category == raw_category
    assert product.raw_category == raw_category
    assert product.family == "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ"
    assert product.category_name == "Σκεύη Μαγειρικής"
    assert product.sub_category == "Γάστρες"
    assert product.category_levels == [
        "ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ",
        "Σκεύη Μαγειρικής",
        "Γάστρες",
    ]


def test_model_whitespace_is_stripped_before_validation_and_output(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)

    products = load_source_catalog(catalog_path)

    assert products[1].model == "123456"
    assert products[1].is_atomic_model
    assert not products[1].automation_eligible


def test_atomic_model_detection_examples() -> None:
    assert is_atomic_model("005606")
    assert is_atomic_model("123456")
    assert not is_atomic_model("233374-233203")
    assert not is_atomic_model(" 233374-233203")
    assert not is_atomic_model("232624-232646-232647")
    assert not is_atomic_model("ABC123")
    assert not is_atomic_model("12345")
    assert not is_atomic_model("1234567")


def test_composite_model_and_missing_mpn_warnings(tmp_path: Path) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    _write_catalog(catalog_path)

    product = load_source_catalog(catalog_path)[2]

    assert product.model == "233374-233203"
    assert not product.is_atomic_model
    assert not product.automation_eligible
    assert product.mpn == ""
    assert product.warnings == ["composite_or_invalid_model", "missing_mpn"]


def test_missing_required_columns_are_reported(tmp_path: Path) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    catalog_path.write_text(
        "model,mpn,name\n005606,MPN,Product\n", encoding="utf-8-sig"
    )

    with pytest.raises(MissingCatalogColumnsError) as exc_info:
        load_source_catalog(catalog_path)

    assert "category" in exc_info.value.missing_columns
    assert "skroutz_status" in exc_info.value.missing_columns
