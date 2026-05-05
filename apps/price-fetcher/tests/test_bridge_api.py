import csv
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.api.app import create_app


def test_post_bridge_run_uses_temp_paths_and_returns_artifacts(tmp_path: Path) -> None:
    stock_csv = tmp_path / "stock.csv"
    stock_csv.write_text(
        "model,quantity\n"
        "123456,6\n"
        "1234567,10\n",
        encoding="utf-8-sig",
    )
    opencart_csv = tmp_path / "opencart.csv"
    opencart_csv.write_text(
        "model,name,quantity,price,status\n"
        "123456,API Product,1,20.00,0\n",
        encoding="utf-8-sig",
    )
    output_dir = tmp_path / "api-run"

    response = TestClient(create_app()).post(
        "/api/bridge/run",
        json={
            "opencart_export_path": str(opencart_csv),
            "stock_csv_path": str(stock_csv),
            "output_dir": str(output_dir),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["stock_csv_path"] == str(stock_csv)
    assert payload["opencart_export_path"] == str(opencart_csv)
    assert payload["output_dir"] == str(output_dir)
    assert payload["summary"]["updated_count"] == 1
    assert payload["summary"]["invalid_or_composite_models_ignored"] == 1

    artifact_names = {artifact["name"] for artifact in payload["artifacts"]}
    assert "oc_import.csv" in artifact_names
    assert "summary.csv" in artifact_names

    with (output_dir / "oc_import.csv").open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows == [{"model": "123456", "quantity": "6", "price": "20.00", "status": "1"}]


def test_post_bridge_run_missing_stock_csv_returns_404(tmp_path: Path) -> None:
    opencart_csv = tmp_path / "opencart.csv"
    opencart_csv.write_text("model,name,quantity,price,status\n123456,Product,1,20.00,1\n", encoding="utf-8-sig")

    response = TestClient(create_app()).post(
        "/api/bridge/run",
        json={
            "opencart_export_path": str(opencart_csv),
            "stock_csv_path": str(tmp_path / "missing-stock.csv"),
            "output_dir": str(tmp_path / "out"),
        },
    )

    assert response.status_code == 404
    assert "Stock CSV not found" in response.json()["detail"]
