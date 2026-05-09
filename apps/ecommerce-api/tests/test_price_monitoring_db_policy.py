import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.artifacts import ARTIFACT_ROOTS_ENV_VAR  # noqa: E402
from ecommerce.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.file_editor.safe_paths import FILE_ROOTS_ENV_VAR  # noqa: E402


def _client_without_db(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    return TestClient(create_app())


def _blocked_detail(response) -> dict:
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "price_monitoring_database_required"
    assert detail["configured"] is False
    assert detail["ready_for_price_monitoring"] is False
    assert "database_not_configured" in detail["blocking_reasons"]
    return detail


def _write_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.csv").write_text("model,mpn,name,price\n005606,MPN-1,Product,10.00\n", encoding="utf-8")
    (run_dir / "selection_summary.json").write_text('{"run_id":"run-1","source":"skroutz"}\n', encoding="utf-8")
    (run_dir / "review.csv").write_text("model,target_price,status\n005606,9.00,exportable\n", encoding="utf-8")


def test_db_status_reports_monitoring_not_ready_without_database(tmp_path: Path, monkeypatch) -> None:
    response = _client_without_db(tmp_path, monkeypatch).get("/api/price-monitoring/db/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["ready_for_price_monitoring"] is False
    assert payload["catalog_requires_database"] is True
    assert payload["ready_for_catalog"] is False
    assert payload["price_monitoring_requires_database"] is True
    assert payload["non_db_workflows_available"] is True
    assert "database_not_configured" in payload["blocking_reasons"]


def test_monitoring_workflow_routes_return_structured_503_without_database(tmp_path: Path, monkeypatch) -> None:
    client = _client_without_db(tmp_path, monkeypatch)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    _write_run(run_dir)

    responses = [
        client.post("/api/price-monitoring/selection/preview", json={"source": "skroutz"}),
        client.get("/api/price-monitoring/runs"),
        client.get("/api/price-monitoring/runs/run-1"),
        client.post("/api/price-monitoring/runs/run-1/fetch", json={"source": "skroutz"}),
        client.get("/api/price-monitoring/runs/run-1/fetch"),
        client.get("/api/price-monitoring/runs/run-1/review"),
        client.post("/api/price-monitoring/runs/run-1/review/actions", json={"actions": []}),
        client.post("/api/price-monitoring/runs/run-1/export-price-update", json={}),
        client.get("/api/price-monitoring/observations"),
        client.get("/api/price-monitoring/runs/run-1/observations"),
        client.get("/api/price-monitoring/runs/run-1/catalog-snapshot"),
        client.get("/api/price-monitoring/products/1/price-history"),
        client.get("/api/price-monitoring/products/by-model/005606/price-history"),
        client.get("/api/price-monitoring/alerts/rules"),
    ]

    for response in responses:
        _blocked_detail(response)


def test_run_creation_is_blocked_before_creating_file_folder(tmp_path: Path, monkeypatch) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    catalog_path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        "005606,MPN-1,Product,Family,Brand,10.00,1,1,1,1\n",
        encoding="utf-8-sig",
    )
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    client = _client_without_db(tmp_path, monkeypatch)

    response = client.post("/api/price-monitoring/runs", json={"source": "skroutz", "selected_models": ["005606"]})

    _blocked_detail(response)
    assert not (tmp_path / "output" / "ecommerce" / "monitoring" / "runs").exists()


def test_non_monitoring_routes_are_not_db_blocked(tmp_path: Path, monkeypatch) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    catalog_path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        "005606,MPN-1,Product,Family,Brand,10.00,1,1,1,1\n",
        encoding="utf-8-sig",
    )
    file_root = tmp_path / "files"
    file_root.mkdir()
    editable = file_root / "editable.csv"
    editable.write_text("model\n005606\n", encoding="utf-8")
    artifact_root = tmp_path / "output" / "ecommerce" / "monitoring" / "runs"
    run_dir = artifact_root / "run-1"
    _write_run(run_dir)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, str(file_root))
    monkeypatch.setenv(ARTIFACT_ROOTS_ENV_VAR, str(artifact_root))
    client = _client_without_db(tmp_path, monkeypatch)

    assert client.get("/api/health").status_code == 200
    catalog_response = client.get("/api/catalog/summary")
    assert catalog_response.status_code == 503
    assert catalog_response.json()["detail"]["code"] == "catalog_database_required"
    assert client.get("/api/files/roots").status_code == 200
    assert client.post("/api/files/read", json={"path": str(editable)}).status_code == 200
    assert client.get("/api/artifacts/price-monitoring/runs/run-1").status_code == 200


def test_mocked_db_ready_allows_monitoring_routes_to_reach_normal_validation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes_price_monitoring, "require_database_ready_for_price_monitoring", lambda: None)
    client = _client_without_db(tmp_path, monkeypatch)

    response = client.post("/api/price-monitoring/runs/missing/fetch", json={"source": "skroutz"})

    assert response.status_code == 404
    assert "run folder not found" in response.json()["detail"]
