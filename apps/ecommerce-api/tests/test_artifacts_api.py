import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.artifacts import ARTIFACT_ROOTS_ENV_VAR, artifact_link_payload  # noqa: E402
from ecommerce.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(SOURCE_CATA_ENV_VAR, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.setenv(
        ARTIFACT_ROOTS_ENV_VAR,
        (
            f"{tmp_path / 'output' / 'ecommerce' / 'monitoring' / 'runs'};"
            f"{tmp_path / 'extra_artifacts'}"
        ),
    )
    return TestClient(create_app())


def _write_price_monitoring_run(tmp_path: Path, run_id: str = "pm-1") -> Path:
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "review.csv").write_text("model,price\n005606,123.45\n", encoding="utf-8")
    (run_dir / "selection_summary.json").write_text(
        json.dumps({"run_id": run_id, "source": "skroutz"}),
        encoding="utf-8",
    )
    (run_dir / "notes.xlsx").write_text("not previewable\n", encoding="utf-8")
    (run_dir / "nested").mkdir()
    return run_dir


def test_health_endpoint_returns_ok_without_catalog_or_export_files(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "ecommerce-api"
    assert payload["api"] == "commerce"
    assert payload["checks"] == {"app": "ok", "database": "not_configured"}


def test_artifact_roots_endpoint_uses_temp_roots(tmp_path: Path, monkeypatch) -> None:
    _write_price_monitoring_run(tmp_path)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/roots")

    assert response.status_code == 200
    roots = response.json()["roots"]
    assert any(root["path"] == str(Path("output") / "ecommerce" / "monitoring" / "runs") and root["exists"] for root in roots)
    assert any(str(tmp_path / "extra_artifacts") == root["path"] for root in roots)


def test_artifact_link_payload_allowed_path_includes_access_metadata(tmp_path: Path, monkeypatch) -> None:
    run_dir = _write_price_monitoring_run(tmp_path)
    _client(tmp_path, monkeypatch)

    payload = artifact_link_payload(run_dir / "review.csv")

    assert payload["name"] == "review.csv"
    assert payload["download_url"].startswith("/api/artifacts/download?path=")
    assert payload["read_url"].startswith("/api/artifacts/read?path=")
    assert payload["is_allowed"] is True
    assert payload["can_read"] is True
    assert payload["can_download"] is True
    assert payload["warning"] == ""


def test_artifact_link_payload_outside_root_has_empty_urls(tmp_path: Path, monkeypatch) -> None:
    outside = tmp_path / "outside.csv"
    outside.write_text("model,price\n005606,123.45\n", encoding="utf-8")
    _client(tmp_path, monkeypatch)

    payload = artifact_link_payload(outside)

    assert payload["name"] == "outside.csv"
    assert payload["download_url"] == ""
    assert payload["read_url"] == ""
    assert payload["is_allowed"] is False
    assert payload["can_read"] is False
    assert payload["can_download"] is False
    assert payload["warning"] == "outside_configured_artifact_roots"


def test_price_monitoring_run_artifact_listing(tmp_path: Path, monkeypatch) -> None:
    _write_price_monitoring_run(tmp_path)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/price-monitoring/runs/pm-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "pm-1"
    assert payload["run_type"] == "price-monitoring"
    assert [item["name"] for item in payload["items"]] == ["notes.xlsx", "review.csv", "selection_summary.json"]


def test_read_csv_artifact(tmp_path: Path, monkeypatch) -> None:
    run_dir = _write_price_monitoring_run(tmp_path)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/read", params={"path": str(run_dir / "review.csv")})

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "review.csv"
    assert payload["extension"] == ".csv"
    assert payload["content"].startswith("model,price")
    assert payload["truncated"] is False


def test_read_json_artifact(tmp_path: Path, monkeypatch) -> None:
    run_dir = _write_price_monitoring_run(tmp_path)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/read", params={"path": str(run_dir / "selection_summary.json")})

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "selection_summary.json"
    assert '"source": "skroutz"' in payload["content"]


def test_read_rejects_unsupported_extension(tmp_path: Path, monkeypatch) -> None:
    run_dir = _write_price_monitoring_run(tmp_path)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/read", params={"path": str(run_dir / "notes.xlsx")})

    assert response.status_code == 400
    assert "Unsupported preview extension" in response.json()["detail"]


def test_download_returns_file(tmp_path: Path, monkeypatch) -> None:
    run_dir = _write_price_monitoring_run(tmp_path)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/download", params={"path": str(run_dir / "review.csv")})

    assert response.status_code == 200
    assert response.content.startswith(b"model,price")
    assert "review.csv" in response.headers["content-disposition"]


def test_missing_artifact_returns_404(tmp_path: Path, monkeypatch) -> None:
    run_dir = _write_price_monitoring_run(tmp_path)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/download", params={"path": str(run_dir / "missing.csv")})

    assert response.status_code == 404
    assert "Artifact not found" in response.json()["detail"]


def test_path_traversal_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _write_price_monitoring_run(tmp_path, run_id="run-1")
    client = _client(tmp_path, monkeypatch)

    response = client.get(
        "/api/artifacts/read",
        params={"path": str(Path("output") / "ecommerce" / "monitoring" / "runs" / "run-1" / ".." / "run-1" / "review.csv")},
    )

    assert response.status_code == 400
    assert "Path traversal" in response.json()["detail"]


def test_path_outside_artifact_roots_is_rejected(tmp_path: Path, monkeypatch) -> None:
    outside = tmp_path / "outside.csv"
    outside.write_text("model,price\n005606,123.45\n", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/read", params={"path": str(outside)})

    assert response.status_code == 403
    assert "outside allowed artifact roots" in response.json()["detail"]


def test_download_path_outside_artifact_roots_is_rejected(tmp_path: Path, monkeypatch) -> None:
    outside = tmp_path / "outside.csv"
    outside.write_text("model,price\n005606,123.45\n", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/artifacts/download", params={"path": str(outside)})

    assert response.status_code == 403
    assert "outside allowed artifact roots" in response.json()["detail"]


def test_artifact_api_does_not_require_real_downloads_or_exports(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    roots_response = client.get("/api/artifacts/roots")
    health_response = client.get("/api/health")

    assert roots_response.status_code == 200
    assert health_response.status_code == 200
