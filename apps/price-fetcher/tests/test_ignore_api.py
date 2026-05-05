import csv
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pricefetcher.api.app import create_app  # noqa: E402
from pricefetcher.ignore.product_ignore import PRICE_IGNORE_ENV_VAR  # noqa: E402


def _client_with_ignore_path(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    ignore_path = tmp_path / "price_ignore.csv"
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(ignore_path))
    return TestClient(create_app()), ignore_path


def test_get_ignore_products(tmp_path: Path, monkeypatch) -> None:
    client, ignore_path = _client_with_ignore_path(tmp_path, monkeypatch)
    ignore_path.write_text(
        "model,name,manufacturer,mpn,reason,ignored_at,notes\n"
        "005606,Product One,Bosch,MPN-1,manual,2026-04-28T12:30:00+00:00,note\n"
        "123456,Product Two,Miele,MPN-2,other,2026-04-28T12:31:00+00:00,\n",
        encoding="utf-8-sig",
    )

    response = client.get("/api/ignore/products", params={"q": "bosch", "page": 1, "page_size": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["filtered_total"] == 1
    assert payload["items"][0]["model"] == "005606"


def test_post_ignore_product_creates_file_and_returns_stored_row(tmp_path: Path, monkeypatch) -> None:
    client, ignore_path = _client_with_ignore_path(tmp_path, monkeypatch)

    response = client.post(
        "/api/ignore/products",
        json={
            "model": " 005606 ",
            "name": " Product ",
            "manufacturer": " Bosch ",
            "mpn": " MPN-1 ",
            "reason": "do not price monitor",
            "notes": "manual",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "005606"
    assert payload["name"] == "Product"
    assert payload["manufacturer"] == "Bosch"
    assert payload["mpn"] == "MPN-1"
    assert payload["reason"] == "do not price monitor"
    assert payload["ignored_at"]
    assert ignore_path.exists()

    with ignore_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["model"] == "005606"


def test_post_ignore_product_rejects_composite_model(tmp_path: Path, monkeypatch) -> None:
    client, _ignore_path = _client_with_ignore_path(tmp_path, monkeypatch)

    response = client.post("/api/ignore/products", json={"model": "233374-233203"})

    assert response.status_code == 400
    assert "exactly 6 numeric digits" in response.json()["detail"]


def test_post_ignore_product_missing_model_returns_400(tmp_path: Path, monkeypatch) -> None:
    client, _ignore_path = _client_with_ignore_path(tmp_path, monkeypatch)

    response = client.post("/api/ignore/products", json={"reason": "manual"})

    assert response.status_code == 400
    assert response.json()["detail"] == "model is required"


def test_delete_ignore_product(tmp_path: Path, monkeypatch) -> None:
    client, _ignore_path = _client_with_ignore_path(tmp_path, monkeypatch)
    client.post("/api/ignore/products", json={"model": "005606"})

    removed = client.delete("/api/ignore/products/005606")
    missing = client.delete("/api/ignore/products/005606")

    assert removed.status_code == 200
    assert removed.json() == {"model": "005606", "removed": True}
    assert missing.status_code == 200
    assert missing.json() == {"model": "005606", "removed": False}
