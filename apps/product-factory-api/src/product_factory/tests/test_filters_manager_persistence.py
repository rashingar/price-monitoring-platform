from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from product_factory import repo_paths
from product_factory.api.app import create_app
from product_factory.api.schemas import AddFilterGroupRequest
from product_factory.services.filters_manager_service import (
    FILTER_OVERRIDE_BACKUP_RETENTION,
    FilterManagerError,
    _FilterPersistenceLock,
    add_filter_group,
    list_filter_override_backups,
    restore_filter_override_backup,
)
from product_factory.tools.sync_filter_map import (
    build_filter_map_payload,
    default_manual_overrides,
    regenerate_filter_map_from_overrides,
    run_apply_overrides,
    stable_category_id,
    stable_group_id,
    stable_value_id,
    write_filter_map_json,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    _write_json(paths["base"], build_filter_map_payload([_category()], source="test"))
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


def test_filter_persistence_lock_acquires_writes_metadata_and_releases(tmp_path: Path) -> None:
    lock_path = tmp_path / "filter_map.manual_overrides.json.lock"

    with _FilterPersistenceLock(lock_path, purpose="test", timeout_seconds=0.2, retry_seconds=0.01):
        payload = _read_json(lock_path)
        assert payload["purpose"] == "test"
        assert payload["pid"]
        assert payload["token"]

    assert not lock_path.exists()


def test_filter_persistence_lock_timeout_returns_controlled_error(tmp_path: Path) -> None:
    lock_path = tmp_path / "filter_map.manual_overrides.json.lock"
    _write_json(lock_path, {"pid": 999999, "token": "other", "purpose": "busy"})

    with pytest.raises(FilterManagerError) as excinfo:
        with _FilterPersistenceLock(lock_path, purpose="test", timeout_seconds=0.01, retry_seconds=0.001):
            pass

    assert excinfo.value.status_code == 409
    assert "persistence lock timed out" in excinfo.value.detail


def test_add_group_updates_manual_overrides_effective_map_and_audit_metadata(
    client: TestClient,
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    response = client.put(f"/api/filters/categories/{ids['category_id']}/groups", json={"name": "Color"})

    assert response.status_code == 200
    group_id = stable_group_id(ids["category_id"], "Color")
    manual = _read_json(filter_paths["manual"])
    group = manual["categories"][ids["category_id"]]["groups"][group_id]
    assert group["name"] == "Color"
    assert group["metadata"]["operation"] == "add_group"
    assert manual["metadata"]["last_operation"] == "add_group"
    assert manual["metadata"]["revision"] == response.json()["revision"]
    final_groups = _read_json(filter_paths["final"])["by_category_id"][ids["category_id"]]["filter_groups"]
    assert any(group["group_id"] == group_id for group in final_groups)
    assert not Path(str(filter_paths["manual"]) + ".lock").exists()


def test_update_group_updates_revision(client: TestClient) -> None:
    ids = _ids()
    before = client.get(f"/api/filters/categories/{ids['category_id']}").json()["revision"]

    response = client.patch(
        f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}",
        json={"required": False},
    )

    assert response.status_code == 200
    assert response.json()["revision"] != before


def test_add_value_updates_revision(client: TestClient) -> None:
    ids = _ids()
    before = client.get(f"/api/filters/categories/{ids['category_id']}").json()["revision"]

    response = client.put(
        f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}/values",
        json={"value": "32 GB"},
    )

    assert response.status_code == 200
    assert response.json()["revision"] != before


def test_update_value_updates_revision(client: TestClient) -> None:
    ids = _ids()
    before = client.get(f"/api/filters/categories/{ids['category_id']}").json()["revision"]

    response = client.patch(
        f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}/values/{ids['value_id']}",
        json={"status": "deprecated"},
    )

    assert response.status_code == 200
    assert response.json()["revision"] != before


def test_stale_expected_revision_returns_409_and_does_not_modify_manual_overrides(
    client: TestClient,
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    before_manual = filter_paths["manual"].read_text(encoding="utf-8")

    response = client.patch(
        f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}",
        json={"status": "inactive", "expected_revision": "sha256:stale"},
    )

    assert response.status_code == 409
    assert "Stale filter revision" in response.json()["detail"]
    assert filter_paths["manual"].read_text(encoding="utf-8") == before_manual


def test_matching_expected_revision_succeeds_and_returns_new_revision(client: TestClient) -> None:
    ids = _ids()
    before = client.get(f"/api/filters/categories/{ids['category_id']}").json()["revision"]

    response = client.put(
        f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}/values",
        json={"value": "32 GB", "expected_revision": before},
    )

    assert response.status_code == 200
    assert response.json()["revision"] != before


def test_omitted_expected_revision_succeeds_for_current_clients(client: TestClient) -> None:
    ids = _ids()

    response = client.put(
        f"/api/filters/categories/{ids['category_id']}/groups/{ids['group_id']}/values",
        json={"value": "32 GB"},
    )

    assert response.status_code == 200


def test_api_stale_revision_response_is_409(client: TestClient) -> None:
    ids = _ids()

    response = client.put(
        f"/api/filters/categories/{ids['category_id']}/groups",
        json={"name": "Color", "expected_revision": "sha256:not-current"},
    )

    assert response.status_code == 409
    assert "Stale filter revision" in response.json()["detail"]


def test_sync_ignores_manual_metadata_fields(filter_paths: dict[str, Path]) -> None:
    ids = _ids()
    manual = default_manual_overrides()
    manual["metadata"] = {
        "schema_version": 1,
        "updated_at": "2026-05-02T00:00:00Z",
        "revision": "sha256:old",
        "last_operation": "test",
    }
    manual["categories"] = {
        ids["category_id"]: {
            "category_id": ids["category_id"],
            "path": ids["path"],
            "metadata": {"updated_at": "2026-05-02T00:00:00Z", "operation": "test"},
            "groups": {
                ids["group_id"]: {
                    "group_id": ids["group_id"],
                    "name": "Memory RAM",
                    "required": False,
                    "status": "active",
                    "metadata": {"updated_at": "2026-05-02T00:00:00Z", "operation": "test"},
                    "values": {
                        ids["value_id"]: {
                            "value_id": ids["value_id"],
                            "value": "16GB",
                            "status": "deprecated",
                            "metadata": {"updated_at": "2026-05-02T00:00:00Z", "operation": "test"},
                        }
                    },
                }
            },
        }
    }
    _write_json(filter_paths["manual"], manual)

    result = run_apply_overrides(
        base_path=filter_paths["base"],
        manual_path=filter_paths["manual"],
        filter_map_path=filter_paths["final"],
        report_path=filter_paths["report"],
        write=True,
    )

    assert result == 0
    final_group = _read_json(filter_paths["final"])["by_category_id"][ids["category_id"]]["filter_groups"][0]
    assert final_group["name"] == "Memory RAM"
    assert "metadata" not in final_group
    assert "metadata" not in final_group["values"][0]


def test_concurrent_filter_writes_do_not_drop_updates(filter_paths: dict[str, Path]) -> None:
    ids = _ids()
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            add_filter_group(ids["category_id"], AddFilterGroupRequest(name=name))
        except BaseException as exc:  # pragma: no cover - reported by assertion below
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("Color",)),
        threading.Thread(target=worker, args=("Screen Size",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    manual_groups = _read_json(filter_paths["manual"])["categories"][ids["category_id"]]["groups"]
    final_groups = _read_json(filter_paths["final"])["by_category_id"][ids["category_id"]]["filter_groups"]
    assert stable_group_id(ids["category_id"], "Color") in manual_groups
    assert stable_group_id(ids["category_id"], "Screen Size") in manual_groups
    assert {group["name"] for group in final_groups} >= {"Color", "Screen Size"}


def test_successful_write_creates_backup_of_previous_manual_overrides(
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    before_manual = _read_json(filter_paths["manual"])

    add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Color"))

    backups = sorted(filter_paths["backups"].glob("filter_map.manual_overrides.*.json"))
    assert len(backups) == 1
    assert _read_json(backups[0]) == before_manual


def test_backup_retention_removes_old_backups_beyond_cap(filter_paths: dict[str, Path]) -> None:
    ids = _ids()

    for index in range(FILTER_OVERRIDE_BACKUP_RETENTION + 3):
        add_filter_group(ids["category_id"], AddFilterGroupRequest(name=f"Group {index}"))

    backups = sorted(filter_paths["backups"].glob("filter_map.manual_overrides.*.json"))
    assert len(backups) == FILTER_OVERRIDE_BACKUP_RETENTION


def test_manual_override_write_is_atomic_when_replace_fails(
    filter_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _ids()
    original_replace = os.replace

    def failing_replace(source: str | Path, target: str | Path) -> None:
        if Path(target) == filter_paths["manual"]:
            raise OSError("simulated replace failure")
        original_replace(source, target)

    before_manual = filter_paths["manual"].read_text(encoding="utf-8")
    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(FilterManagerError) as excinfo:
        add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Color"))

    assert excinfo.value.status_code == 500
    assert filter_paths["manual"].read_text(encoding="utf-8") == before_manual
    assert not list(filter_paths["manual"].parent.glob(".filter_map.manual_overrides.json.*.tmp"))


def test_corrupt_current_manual_override_json_returns_controlled_error_and_preserves_file(
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    filter_paths["manual"].write_text("{not valid", encoding="utf-8")

    with pytest.raises(FilterManagerError) as excinfo:
        add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Color"))

    assert excinfo.value.status_code == 409
    assert "Manual filter override JSON is invalid" in excinfo.value.detail
    assert filter_paths["manual"].read_text(encoding="utf-8") == "{not valid"


def test_latest_valid_backup_can_be_restored(filter_paths: dict[str, Path]) -> None:
    ids = _ids()
    add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Color"))
    after_color = _read_json(filter_paths["manual"])
    add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Screen Size"))
    filter_paths["manual"].write_text("{broken", encoding="utf-8")

    response = restore_filter_override_backup()

    restored = _read_json(filter_paths["manual"])
    assert response.status == "ok"
    assert restored["categories"] == after_color["categories"]
    assert restored["metadata"]["revision"] == response.revision
    final_groups = _read_json(filter_paths["final"])["by_category_id"][ids["category_id"]]["filter_groups"]
    assert {group["name"] for group in final_groups} >= {"Color"}
    assert all(group["name"] != "Screen Size" for group in final_groups)
    assert _read_json(filter_paths["report"])["rollback"]["status"] == "restored"


def test_specific_named_backup_can_be_restored(filter_paths: dict[str, Path]) -> None:
    ids = _ids()
    add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Color"))
    first_backup = list_filter_override_backups().items[0].backup_name
    add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Screen Size"))

    response = restore_filter_override_backup(first_backup)

    assert response.restored_backup_name == first_backup
    manual_groups = _read_json(filter_paths["manual"]).get("categories", {}).get(ids["category_id"], {}).get("groups", {})
    assert stable_group_id(ids["category_id"], "Color") not in manual_groups
    assert stable_group_id(ids["category_id"], "Screen Size") not in manual_groups


def test_restore_rejects_path_traversal(filter_paths: dict[str, Path]) -> None:
    with pytest.raises(FilterManagerError) as excinfo:
        restore_filter_override_backup("..\\filter_map.manual_overrides.json")

    assert excinfo.value.status_code == 400


def test_restore_rejects_invalid_backup_json(filter_paths: dict[str, Path]) -> None:
    backup_dir = filter_paths["backups"]
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / "filter_map.manual_overrides.20260502-120000.no-revision.json"
    backup.write_text("{broken", encoding="utf-8")

    with pytest.raises(FilterManagerError) as excinfo:
        restore_filter_override_backup(backup.name)

    assert excinfo.value.status_code == 400
    assert "backup JSON is invalid" in excinfo.value.detail


def test_restore_updates_revision(filter_paths: dict[str, Path]) -> None:
    ids = _ids()
    before = add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Color")).revision
    add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Screen Size"))

    response = restore_filter_override_backup()

    assert response.revision != before
    assert _read_json(filter_paths["manual"])["metadata"]["revision"] == response.revision


def test_sync_failure_during_normal_write_leaves_previous_manual_recoverable(
    filter_paths: dict[str, Path],
) -> None:
    ids = _ids()
    before_manual = _read_json(filter_paths["manual"])

    def failing_write(path: Path, payload: dict[str, Any]) -> None:
        if path == filter_paths["final"]:
            raise OSError("simulated sync failure")
        write_filter_map_json(path, payload)

    patcher = pytest.MonkeyPatch()
    patcher.setattr("product_factory.services.filters_manager_service.write_filter_map_json", failing_write)

    try:
        with pytest.raises(FilterManagerError) as excinfo:
            add_filter_group(ids["category_id"], AddFilterGroupRequest(name="Color"))
    finally:
        patcher.undo()

    assert excinfo.value.status_code == 500
    backup = list(filter_paths["backups"].glob("filter_map.manual_overrides.*.json"))[0]
    assert _read_json(backup) == before_manual
    restore_filter_override_backup(backup.name)
    assert _read_json(filter_paths["manual"])["categories"] == before_manual["categories"]
