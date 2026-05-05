from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pipeline import repo_paths
from pipeline.api.app import create_app
from pipeline.tools.sync_filter_map import (
    build_filter_map_payload,
    default_manual_overrides,
    regenerate_filter_map_from_overrides,
    stable_category_id,
    stable_group_id,
    stable_value_id,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def filter_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    paths = {
        "base": tmp_path / "filter_map.base.json",
        "manual": tmp_path / "filter_map.manual_overrides.json",
        "backups": tmp_path / "backups" / "filter_overrides",
        "final": tmp_path / "filter_map.json",
        "report": tmp_path / "filter_map.sync_report.json",
    }
    monkeypatch.setattr(repo_paths, "FILTER_MAP_BASE_PATH", paths["base"])
    monkeypatch.setattr(repo_paths, "FILTER_MAP_MANUAL_OVERRIDES_PATH", paths["manual"])
    monkeypatch.setattr(repo_paths, "FILTER_MAP_MANUAL_OVERRIDES_BACKUP_DIR", paths["backups"])
    monkeypatch.setattr(repo_paths, "FILTER_MAP_PATH", paths["final"])
    monkeypatch.setattr(repo_paths, "FILTER_MAP_SYNC_REPORT_PATH", paths["report"])
    _write_json(paths["base"], _base_payload())
    _write_json(paths["manual"], default_manual_overrides())
    regenerate_filter_map_from_overrides(
        base_path=paths["base"],
        manual_path=paths["manual"],
        filter_map_path=paths["final"],
        report_path=paths["report"],
    )
    return paths


@pytest.fixture()
def client(filter_paths: dict[str, Path]) -> TestClient:
    return TestClient(create_app())


def _ids() -> dict[str, str]:
    path = "Computers > Laptops > Ultrabooks"
    category_id = stable_category_id(path)
    group_id = stable_group_id(category_id, "Memory")
    value_id = stable_value_id(group_id, "16 GB")
    return {
        "path": path,
        "category_id": category_id,
        "group_id": group_id,
        "value_id": value_id,
    }


def _category() -> dict[str, Any]:
    ids = _ids()
    return {
        "category_id": ids["category_id"],
        "key": "Ultrabooks",
        "parent_category": "Computers",
        "leaf_category": "Laptops",
        "sub_category": "Ultrabooks",
        "path": ids["path"],
        "url": "",
        "filter_groups": [
            {
                "group_id": ids["group_id"],
                "name": "Memory",
                "required": True,
                "status": "active",
                "values": [
                    {
                        "value_id": ids["value_id"],
                        "value": "16 GB",
                        "status": "active",
                    }
                ],
            }
        ],
    }


def _base_payload() -> dict[str, Any]:
    return build_filter_map_payload([_category()], source="test")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_create_app_registers_global_filters_routes(client: TestClient) -> None:
    routes = {
        (next(iter(route.methods - {"HEAD", "OPTIONS"})), route.path)
        for route in client.app.routes
        if getattr(route, "path", "").startswith("/api/filters")
    }

    ids = _ids()
    assert ("GET", "/api/filters/categories") in routes
    assert ("GET", "/api/filters/categories/{category_id}") in routes
    assert ("PUT", "/api/filters/categories/{category_id}/groups") in routes
    assert ("PATCH", "/api/filters/categories/{category_id}/groups/{group_id}") in routes
    assert ("PUT", "/api/filters/categories/{category_id}/groups/{group_id}/values") in routes
    assert ("PATCH", "/api/filters/categories/{category_id}/groups/{group_id}/values/{value_id}") in routes
    assert ("POST", "/api/filters/sync") in routes
    assert ("GET", "/api/filters/sync-report") in routes
    assert ("GET", "/api/filters/backups") in routes
    assert ("POST", "/api/filters/backups/restore") in routes
    assert ("DELETE", f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}") not in routes


def test_list_and_detail_include_counts_and_source_metadata(
    client: TestClient,
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    new_group_id = stable_group_id(ids["category_id"], "Color")
    new_value_id = stable_value_id(new_group_id, "Black")
    manual = default_manual_overrides()
    manual["categories"] = {
        ids["category_id"]: {
            "category_id": ids["category_id"],
            "path": ids["path"],
            "groups": {
                ids["group_id"]: {
                    "group_id": ids["group_id"],
                    "name": "Memory",
                    "required": False,
                    "status": "inactive",
                    "values": {
                        ids["value_id"]: {
                            "value_id": ids["value_id"],
                            "value": "16 GB",
                            "status": "deprecated",
                        }
                    },
                },
                new_group_id: {
                    "group_id": new_group_id,
                    "name": "Color",
                    "required": True,
                    "status": "active",
                    "values": {
                        new_value_id: {
                            "value_id": new_value_id,
                            "value": "Black",
                            "status": "active",
                        }
                    },
                },
            },
        }
    }
    _write_json(filter_paths["manual"], manual)
    regenerate_filter_map_from_overrides(
        base_path=filter_paths["base"],
        manual_path=filter_paths["manual"],
        filter_map_path=filter_paths["final"],
        report_path=filter_paths["report"],
    )

    listed = client.get("/api/filters/categories")
    assert listed.status_code == 200
    item = listed.json()["categories"][0]
    assert item["category_id"] == ids["category_id"]
    assert item["path"] == ids["path"]
    assert item["group_count"] == 2
    assert item["active_group_count"] == 1
    assert item["inactive_group_count"] == 1
    assert item["required_group_count"] == 1
    assert item["source"] == "merged"

    detail = client.get(f"/api/filters/categories/{ids['category_id']}")
    assert detail.status_code == 200
    groups = {group["group_id"]: group for group in detail.json()["groups"]}
    assert groups[ids["group_id"]]["source"] == "merged"
    assert groups[ids["group_id"]]["values"][0]["source"] == "merged"
    assert groups[new_group_id]["source"] == "manual"
    assert groups[new_group_id]["values"][0]["source"] == "manual"
    assert client.get("/api/filters/categories/cat_missing").status_code == 404


def test_add_group_writes_manual_defaults_regenerates_and_rejects_duplicates(
    client: TestClient,
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    before_base = filter_paths["base"].read_text(encoding="utf-8")

    response = client.put(f"/api/filters/categories/{ids['category_id']}/groups", json={"name": "Color"})
    assert response.status_code == 200
    group_id = stable_group_id(ids["category_id"], "Color")
    group = next(group for group in response.json()["groups"] if group["group_id"] == group_id)
    assert group["required"] is True
    assert group["status"] == "active"
    assert group["source"] == "manual"

    manual = _read(filter_paths["manual"])
    assert manual["categories"][ids["category_id"]]["groups"][group_id]["name"] == "Color"
    final = _read(filter_paths["final"])
    assert any(group["group_id"] == group_id for group in final["by_category_id"][ids["category_id"]]["filter_groups"])
    assert filter_paths["base"].read_text(encoding="utf-8") == before_base
    assert client.put(f"/api/filters/categories/{ids['category_id']}/groups", json={"name": "Color"}).status_code == 409
    assert client.put(f"/api/filters/categories/{ids['category_id']}/groups", json={"name": " color "}).status_code == 409


def test_update_group_preserves_group_id_and_validates_requests(
    client: TestClient,
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    url = f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}"

    response = client.patch(url, json={"name": "Memory RAM", "required": False, "status": "inactive"})
    assert response.status_code == 200
    group = next(group for group in response.json()["groups"] if group["group_id"] == ids["group_id"])
    assert group["name"] == "Memory RAM"
    assert group["required"] is False
    assert group["status"] == "inactive"
    assert group["group_id"] == ids["group_id"]

    manual_group = _read(filter_paths["manual"])["categories"][ids["category_id"]]["groups"][ids["group_id"]]
    assert manual_group["name"] == "Memory RAM"
    assert manual_group["required"] is False
    assert manual_group["status"] == "inactive"
    assert client.patch(url, json={"status": "bad"}).status_code == 422
    assert client.patch(url, json={"name": "   "}).status_code == 422
    assert client.patch(f"/api/filters/categories/{ids['category_id']}/groups/fg_missing", json={"status": "inactive"}).status_code == 404


def test_add_value_writes_manual_defaults_regenerates_and_rejects_duplicates(
    client: TestClient,
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    url = f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}/values"

    response = client.put(url, json={"value": "32 GB"})
    assert response.status_code == 200
    value_id = stable_value_id(ids["group_id"], "32 GB")
    group = next(group for group in response.json()["groups"] if group["group_id"] == ids["group_id"])
    value = next(value for value in group["values"] if value["value_id"] == value_id)
    assert value["status"] == "active"
    assert value["source"] == "manual"
    assert _read(filter_paths["manual"])["categories"][ids["category_id"]]["groups"][ids["group_id"]]["values"][value_id]["value"] == "32 GB"
    assert any(value["value_id"] == value_id for value in _read(filter_paths["final"])["by_category_id"][ids["category_id"]]["filter_groups"][0]["values"])
    assert client.put(url, json={"value": "32 GB"}).status_code == 409
    assert client.put(url, json={"value": " 32   gb "}).status_code == 409


def test_update_value_preserves_value_id_and_validates_requests(client: TestClient) -> None:
    ids = _ids()
    url = f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}/values/{ids['value_id']}"

    response = client.patch(url, json={"value": "16GB", "status": "deprecated"})
    assert response.status_code == 200
    group = next(group for group in response.json()["groups"] if group["group_id"] == ids["group_id"])
    value = next(value for value in group["values"] if value["value_id"] == ids["value_id"])
    assert value["value"] == "16GB"
    assert value["status"] == "deprecated"
    assert value["value_id"] == ids["value_id"]
    assert client.patch(url, json={"status": "bad"}).status_code == 422
    assert client.patch(url, json={"value": ""}).status_code == 422
    missing_url = f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}/values/fv_missing"
    assert client.patch(missing_url, json={"status": "deprecated"}).status_code == 404


def test_no_delete_behavior_and_inactive_status_preserves_values(client: TestClient) -> None:
    ids = _ids()
    group_url = f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}"
    value_url = f"{group_url}/values/{ids['value_id']}"

    assert client.delete(group_url).status_code == 405
    assert client.delete(value_url).status_code == 405
    assert client.patch(group_url, json={"status": "deprecated"}).status_code == 200
    assert client.patch(value_url, json={"status": "inactive"}).status_code == 200
    detail = client.get(f"/api/filters/categories/{ids['category_id']}").json()
    group = next(group for group in detail["groups"] if group["group_id"] == ids["group_id"])
    assert group["status"] == "deprecated"
    assert group["values"][0]["status"] == "inactive"


def test_sync_endpoint_uses_base_plus_manual_without_csv_and_report_is_readable(
    client: TestClient,
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    before_base = filter_paths["base"].read_text(encoding="utf-8")
    manual = default_manual_overrides()
    manual["categories"] = {
        ids["category_id"]: {
            "category_id": ids["category_id"],
            "path": ids["path"],
            "groups": {
                ids["group_id"]: {
                    "group_id": ids["group_id"],
                    "name": "Memory RAM",
                    "required": False,
                    "status": "active",
                    "values": {
                        ids["value_id"]: {
                            "value_id": ids["value_id"],
                            "value": "16GB",
                            "status": "deprecated",
                        }
                    },
                }
            },
        }
    }
    _write_json(filter_paths["manual"], manual)

    response = client.post("/api/filters/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["category_count"] == 1
    assert body["overridden_group_count"] >= 1
    assert body["overridden_value_count"] >= 1
    assert filter_paths["base"].read_text(encoding="utf-8") == before_base

    final_group = _read(filter_paths["final"])["by_category_id"][ids["category_id"]]["filter_groups"][0]
    assert final_group["group_id"] == ids["group_id"]
    assert final_group["name"] == "Memory RAM"
    assert final_group["values"][0]["value_id"] == ids["value_id"]
    assert final_group["values"][0]["value"] == "16GB"

    report = client.get("/api/filters/sync-report")
    assert report.status_code == 200
    assert report.json()["overridden_groups"]
    assert report.json()["overridden_values"]


def test_sync_report_missing_returns_404(client: TestClient, filter_paths: dict[str, Path]) -> None:
    filter_paths["report"].unlink()
    assert client.get("/api/filters/sync-report").status_code == 404


def test_api_list_backups_works(client: TestClient, filter_paths: dict[str, Path]) -> None:
    ids = _ids()
    client.put(f"/api/filters/categories/{ids['category_id']}/groups", json={"name": "Color"})

    response = client.get("/api/filters/backups")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["backup_name"].startswith("filter_map.manual_overrides.")
    assert body["items"][0]["size_bytes"] > 0


def test_api_restore_backup_works(client: TestClient, filter_paths: dict[str, Path]) -> None:
    ids = _ids()
    client.put(f"/api/filters/categories/{ids['category_id']}/groups", json={"name": "Color"})
    backup_name = client.get("/api/filters/backups").json()["items"][0]["backup_name"]

    response = client.post("/api/filters/backups/restore", json={"backup_name": backup_name})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["restored_backup_name"] == backup_name
    manual_groups = _read(filter_paths["manual"]).get("categories", {}).get(ids["category_id"], {}).get("groups", {})
    assert stable_group_id(ids["category_id"], "Color") not in manual_groups
