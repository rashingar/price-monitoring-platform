from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from product_factory import repo_paths
from product_factory.api.app import create_app
from product_factory.api.job_runner import SequentialJobRunner
from product_factory.api.job_store import JobStore
from product_factory.services.settings_service import default_product_agent_settings_payload
from product_factory.tools.sync_filter_map import build_filter_map_payload, default_manual_overrides


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture()
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    settings_path = tmp_path / "resources" / "settings" / "product_agent_settings.json"
    monkeypatch.setattr(repo_paths, "PRODUCT_AGENT_SETTINGS_PATH", settings_path)
    return settings_path


@pytest.fixture()
def isolated_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(repo_paths, "REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture()
def isolated_filter_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    paths = {
        "base": tmp_path / "resources" / "mappings" / "filter_map.base.json",
        "manual": tmp_path / "resources" / "mappings" / "filter_map.manual_overrides.json",
        "final": tmp_path / "resources" / "mappings" / "filter_map.json",
        "report": tmp_path / "resources" / "mappings" / "filter_map.sync_report.json",
    }
    monkeypatch.setattr(repo_paths, "FILTER_MAP_BASE_PATH", paths["base"])
    monkeypatch.setattr(repo_paths, "FILTER_MAP_MANUAL_OVERRIDES_PATH", paths["manual"])
    monkeypatch.setattr(repo_paths, "FILTER_MAP_PATH", paths["final"])
    monkeypatch.setattr(repo_paths, "FILTER_MAP_SYNC_REPORT_PATH", paths["report"])
    payload = build_filter_map_payload([], source="contract-smoke")
    _write_json(paths["base"], payload)
    _write_json(paths["manual"], default_manual_overrides())
    _write_json(paths["final"], payload)
    _write_json(paths["report"], {"mode": "contract-smoke", "warnings": []})
    return paths


def test_health_endpoint_returns_stable_status_shape() -> None:
    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jobs_endpoint_returns_empty_list_from_temp_store(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store)
    client = TestClient(create_app(job_store=store, job_runner=runner))

    try:
        response = client.get("/api/jobs")
    finally:
        runner.stop()

    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_missing_job_routes_return_controlled_404(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    runner = SequentialJobRunner(store)
    client = TestClient(create_app(job_store=store, job_runner=runner))

    try:
        responses = [
            client.get("/api/jobs/missing"),
            client.post("/api/jobs/missing/stop"),
            client.get("/api/jobs/missing/logs"),
            client.get("/api/jobs/missing/artifacts"),
        ]
    finally:
        runner.stop()

    assert [response.status_code for response in responses] == [404, 404, 404, 404]
    assert all(response.json()["detail"] == "Job not found." for response in responses)


def test_settings_endpoint_returns_shape_and_rejects_invalid_patch(isolated_settings: Path) -> None:
    _write_json(isolated_settings, default_product_agent_settings_payload())
    client = TestClient(create_app())

    get_response = client.get("/api/settings")
    patch_response = client.patch("/api/settings", json={"authoring": {"unsupported": {}}})

    assert get_response.status_code == 200
    assert {"schema_version", "authoring"}.issubset(get_response.json())
    assert patch_response.status_code == 422
    assert "Unsupported settings patch path" in patch_response.json()["detail"]


def test_filter_status_returns_configured_paths_and_valid_statuses(isolated_filter_paths: dict[str, Path]) -> None:
    response = TestClient(create_app()).get("/api/filters/status")
    body = response.json()

    assert response.status_code == 200
    assert body["filter_map_base_path"] == str(isolated_filter_paths["base"])
    assert body["filter_map_manual_overrides_path"] == str(isolated_filter_paths["manual"])
    assert body["filter_map_path"] == str(isolated_filter_paths["final"])
    assert body["sync_report_path"] == str(isolated_filter_paths["report"])
    assert set(body["valid_statuses"]) == {"active", "deprecated", "inactive"}


def test_filter_category_missing_id_returns_404(isolated_filter_paths: dict[str, Path]) -> None:
    response = TestClient(create_app()).get("/api/filters/categories/cat_missing")

    assert response.status_code == 404
    assert "category_id not found" in response.json()["detail"]


def test_filter_request_validation_rejects_empty_names_and_values() -> None:
    client = TestClient(create_app())

    group_response = client.put("/api/filters/categories/cat/groups", json={"name": ""})
    value_response = client.put("/api/filters/categories/cat/groups/group/values", json={"value": ""})

    assert group_response.status_code == 422
    assert value_response.status_code == 422


def test_filter_review_missing_model_returns_controlled_404(isolated_repo_root: Path) -> None:
    response = TestClient(create_app()).get("/api/filter-review/missing-model")

    assert response.status_code == 404
    assert "Run prepare first" in response.json()["detail"]


def test_authoring_missing_model_returns_controlled_404(isolated_repo_root: Path) -> None:
    response = TestClient(create_app()).get("/api/authoring/missing-model")

    assert response.status_code == 404
    assert "Run prepare first" in response.json()["detail"]
