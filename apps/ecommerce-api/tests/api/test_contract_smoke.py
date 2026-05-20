import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.api import routes_price_monitoring  # noqa: E402
from ecommerce.api.app import create_app  # noqa: E402
from ecommerce.artifacts import (
    ARTIFACT_ROOTS_ENV_VAR,
    artifact_link_payload,
)  # noqa: E402
from ecommerce.catalog_db import ingest_source_catalog  # noqa: E402
from ecommerce.catalog.source_catalog import SOURCE_CATA_ENV_VAR  # noqa: E402
from ecommerce.db.config import DATABASE_URL_ENV_VAR  # noqa: E402
from ecommerce.db.models.base import Base  # noqa: E402
from ecommerce.db.session import get_engine, session_scope  # noqa: E402
from ecommerce.file_editor import FILE_ROOTS_ENV_VAR  # noqa: E402
from ecommerce.ignore.product_ignore import PRICE_IGNORE_ENV_VAR  # noqa: E402


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    artifact_roots = [
        tmp_path / "output" / "ecommerce" / "monitoring" / "runs",
        tmp_path / "extra-artifacts",
    ]
    file_root = tmp_path / "files"
    for path in [*artifact_roots, file_root]:
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(
        ARTIFACT_ROOTS_ENV_VAR, ";".join(str(path) for path in artifact_roots)
    )
    monkeypatch.setenv(FILE_ROOTS_ENV_VAR, str(file_root))
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(tmp_path / "missing-sourceCata.csv"))
    monkeypatch.setenv(PRICE_IGNORE_ENV_VAR, str(tmp_path / "missing-price-ignore.csv"))
    return TestClient(create_app())


@pytest.mark.smoke
def test_health_returns_stable_commerce_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _client(tmp_path, monkeypatch).get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "ecommerce-api"
    assert payload["api"] == "commerce"
    assert payload["checks"] == {"app": "ok", "database": "not_configured"}


@pytest.mark.smoke
def test_paths_roots_returns_safe_metadata_without_secret_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ECOMMERCE_SECRET_TOKEN", "do-not-expose")
    response = _client(tmp_path, monkeypatch).get("/api/paths/roots")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "artifact_roots",
        "file_roots",
        "output_roots",
        "env",
        "env_readiness",
        "local_env",
        "path_separator",
        "platform",
    }
    assert payload["path_separator"] == ";"
    assert payload["platform"] == "Windows-compatible"
    assert payload["env"][DATABASE_URL_ENV_VAR] == "not_configured"
    assert "ECOMMERCE_SECRET_TOKEN" not in payload["env"]
    assert "ECOMMERCE_SECRET_TOKEN" not in str(payload["env_readiness"])
    assert "ECOMMERCE_SECRET_TOKEN" not in str(payload["local_env"])
    for group in ("artifact_roots", "file_roots", "output_roots"):
        assert payload[group]
        assert all(
            set(item) == {"path", "source", "exists", "is_default", "is_configured"}
            for item in payload[group]
        )


@pytest.mark.contract
@pytest.mark.smoke
def test_db_status_not_configured_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _client(tmp_path, monkeypatch).get("/api/price-monitoring/db/status")

    assert response.status_code == 200
    payload = response.json()
    for field in (
        "configured",
        "reachable",
        "required_tables_present",
        "alembic_up_to_date",
        "setup_hints",
    ):
        assert field in payload
    assert payload["configured"] is False
    assert payload["reachable"] is False
    assert payload["required_tables_present"] is False
    assert isinstance(payload["setup_hints"], list)


@pytest.mark.smoke
def test_db_backed_alert_routes_return_503_without_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    responses = [
        client.get("/api/price-monitoring/alerts/rules"),
        client.post("/api/price-monitoring/alerts/rules", json={}),
        client.get("/api/price-monitoring/alerts/rules/1"),
        client.patch("/api/price-monitoring/alerts/rules/1", json={"active": False}),
        client.post("/api/price-monitoring/alerts/rules/1/deactivate"),
        client.get("/api/price-monitoring/alerts/events"),
        client.post("/api/price-monitoring/alerts/events/1/acknowledge", json={}),
        client.post("/api/price-monitoring/alerts/events/1/resolve", json={}),
        client.post("/api/price-monitoring/alerts/evaluate/run-1"),
    ]

    assert {response.status_code for response in responses} == {503}
    assert all(
        response.json()["detail"]["code"] == "price_monitoring_database_required"
        for response in responses
    )


@pytest.mark.smoke
def test_artifacts_reject_outside_root_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside.csv"
    outside.write_text("model,price\n005606,1.23\n", encoding="utf-8")

    response = _client(tmp_path, monkeypatch).get(
        "/api/artifacts/read", params={"path": str(outside)}
    )

    assert response.status_code == 403
    assert "outside allowed artifact roots" in response.json()["detail"]


@pytest.mark.smoke
def test_catalog_missing_source_file_returns_controlled_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _client(tmp_path, monkeypatch).get("/api/catalog/summary")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "catalog_database_required"


@pytest.mark.smoke
def test_price_monitoring_invalid_and_missing_run_errors_are_controlled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    invalid = client.get("/api/price-monitoring/runs/%2E%2E")
    missing_fetch = client.get("/api/price-monitoring/runs/missing/fetch")

    assert invalid.status_code == 503
    assert missing_fetch.status_code == 503
    assert invalid.json()["detail"]["code"] == "price_monitoring_database_required"
    assert (
        missing_fetch.json()["detail"]["code"] == "price_monitoring_database_required"
    )


@pytest.mark.contract
@pytest.mark.smoke
def test_artifact_roots_endpoint_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _client(tmp_path, monkeypatch).get("/api/artifacts/roots")

    assert response.status_code == 200
    roots = response.json()["roots"]
    assert roots
    assert all(set(root) == {"path", "exists"} for root in roots)
    assert all(isinstance(root["exists"], bool) for root in roots)


@pytest.mark.contract
@pytest.mark.smoke
def test_artifact_link_payload_public_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / "run-1"
    artifact = run_dir / "summary.csv"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("metric,value\nupdated,1\n", encoding="utf-8")

    response = client.get("/api/artifacts/price-monitoring/runs/run-1")

    assert response.status_code == 200
    item = response.json()["items"][0]
    expected_fields = {
        "name",
        "path",
        "download_url",
        "read_url",
        "is_allowed",
        "can_read",
        "can_download",
        "warning",
    }
    assert expected_fields.issubset(item)
    assert expected_fields == set(artifact_link_payload(artifact))


@pytest.mark.contract
@pytest.mark.smoke
def test_price_monitoring_fetch_execution_response_shape_from_local_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_price_monitoring,
        "require_database_ready_for_price_monitoring",
        lambda: None,
    )
    client = _client(tmp_path, monkeypatch)
    run_id = "20260502-120000-contract"
    execution_id = "exec-contract"
    run_dir = tmp_path / "output" / "ecommerce" / "monitoring" / "runs" / run_id
    execution_dir = run_dir / "fetch_executions"
    execution_dir.mkdir(parents=True)
    (run_dir / "input.csv").write_text(
        "model,mpn,name,price\n005606,MPN-1,Product,10.00\n", encoding="utf-8"
    )
    payload = {
        "execution_id": execution_id,
        "execution_type": "fetch",
        "run_id": run_id,
        "status": "succeeded",
        "source": "skroutz",
        "catalog_url": None,
        "queued_at": "2026-05-02T12:00:00+00:00",
        "started_at": "2026-05-02T12:00:01+00:00",
        "completed_at": "2026-05-02T12:00:02+00:00",
        "cancelled_at": None,
        "cancel_reason": "",
        "input_csv_path": str(run_dir / "input.csv"),
        "enriched_csv_path": str(run_dir / "input_skroutz_enriched.csv"),
        "fetch_summary_path": str(run_dir / "input_summary.json"),
        "fetch_result_path": str(run_dir / "fetch_result.json"),
        "execution_path": str(execution_dir / f"{execution_id}.json"),
        "log_path": str(execution_dir / f"{execution_id}.log"),
        "warnings": [],
        "error": "",
        "persistence_status": "not_configured",
        "persistence_warnings": [],
        "alert_evaluation_status": "not_configured",
    }
    (run_dir / "fetch_execution.json").write_text(json.dumps(payload), encoding="utf-8")
    (execution_dir / f"{execution_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    response = client.get(f"/api/price-monitoring/runs/{run_id}/fetch/{execution_id}")

    assert response.status_code == 200
    body = response.json()
    for field in (
        "run_id",
        "execution_id",
        "execution_type",
        "status",
        "source",
        "queued_at",
        "started_at",
        "completed_at",
        "artifacts",
        "stale",
        "stale_after_minutes",
        "queue_position",
        "persistence_status",
        "alert_evaluation_status",
    ):
        assert field in body
    assert body["run_id"] == run_id
    assert body["execution_id"] == execution_id
    assert body["status"] == "succeeded"


@pytest.mark.contract
@pytest.mark.smoke
def test_catalog_product_response_shape_from_tmp_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog_path = tmp_path / "sourceCata.csv"
    catalog_path.write_text(
        "model,mpn,name,category,manufacturer,price,quantity,status,bestprice_status,skroutz_status\n"
        "005606,MPN-1,Product One,Family:::Family///Category:::Family///Category///Sub,Brand,12.34,5,1,1,0\n",
        encoding="utf-8-sig",
    )
    client = _client(tmp_path, monkeypatch)
    database_url = f"sqlite+pysqlite:///{tmp_path / 'ecommerce.db'}"
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    monkeypatch.setenv(SOURCE_CATA_ENV_VAR, str(catalog_path))
    Base.metadata.create_all(get_engine(database_url))
    with session_scope(database_url) as session:
        ingest_source_catalog(session, source_cata_path=catalog_path)

    response = client.get("/api/catalog/products")

    assert response.status_code == 200
    body = response.json()
    assert {"items", "page", "page_size", "total", "filtered_total"} <= set(body)
    item = body["items"][0]
    for field in (
        "model",
        "catalog_product_id",
        "mpn",
        "name",
        "category",
        "raw_category",
        "family",
        "category_name",
        "sub_category",
        "category_levels",
        "manufacturer",
        "price",
        "quantity",
        "status",
        "bestprice_status",
        "skroutz_status",
        "is_atomic_model",
        "automation_eligible",
        "ignored",
        "warnings",
    ):
        assert field in item
    assert item["model"] == "005606"
    assert item["automation_eligible"] is True
