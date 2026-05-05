import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.bridge.bridge_core import (
    ARTIFACT_NAMES,
    is_atomic_model,
    read_balance_stock_csv,
    read_model_quantity_export,
    run_bridge_from_balance_csv,
)


def test_is_atomic_model_accepts_exactly_six_digits() -> None:
    assert is_atomic_model("005606")
    assert is_atomic_model(" 123456 ")
    assert not is_atomic_model("233374-233203")
    assert not is_atomic_model("ABC123")
    assert not is_atomic_model("12345")
    assert not is_atomic_model("1234567")


def test_read_simple_model_quantity_stock_csv_ignores_composites(tmp_path: Path) -> None:
    stock_csv = tmp_path / "stock.csv"
    stock_csv.write_text(
        "model,quantity\n"
        "005606,4\n"
        "233374-233203,9\n"
        "ABC123,2\n",
        encoding="utf-8-sig",
    )

    rows = read_model_quantity_export(stock_csv)
    result = read_balance_stock_csv(stock_csv)

    assert rows == {"005606": {"model": "005606", "quantity": "4"}}
    assert result.ignored_count == 2


def test_run_bridge_updates_valid_model_and_ignores_composite_stock(tmp_path: Path) -> None:
    stock_csv = tmp_path / "stock.csv"
    stock_csv.write_text(
        "model,quantity\n"
        "005606,5\n"
        "233374-233203,8\n",
        encoding="utf-8-sig",
    )
    opencart_csv = tmp_path / "opencart.csv"
    opencart_csv.write_text(
        "model,name,quantity,price,status\n"
        "005606,Valid Product,1,10.00,0\n",
        encoding="utf-8-sig",
    )

    result = run_bridge_from_balance_csv(stock_csv, opencart_csv, tmp_path / "out")

    assert {artifact.name for artifact in result.artifacts} == set(ARTIFACT_NAMES)
    assert all(artifact.path.exists() for artifact in result.artifacts)
    assert result.summary.updated_count == 1
    assert result.summary.invalid_or_composite_models_ignored == 1

    with result.oc_import.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows == [{"model": "005606", "quantity": "5", "price": "10.00", "status": "1"}]

    with result.unknown_codes.open("r", encoding="utf-8", newline="") as f:
        unknown_rows = list(csv.DictReader(f))
    assert unknown_rows[0]["model"] == "233374-233203"
    assert unknown_rows[0]["reason"] == "invalid_or_composite_model"
