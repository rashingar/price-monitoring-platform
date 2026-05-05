from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline import repo_paths
from pipeline.api.app import create_app
from pipeline.api.artifact_resolver import resolve_job_artifacts
from pipeline.api.job_models import JobRecord, JobStatus, JobType
from pipeline.models import SourceProductData, SpecItem, TaxonomyResolution
from pipeline.services import metadata as metadata_module
from pipeline.services.filter_review_service import get_filter_review_state
from pipeline.services.models import RunArtifacts, RunStatus, RunType
from pipeline.tools.sync_filter_map import build_filter_map_payload, default_manual_overrides, stable_category_id, stable_group_id, stable_value_id
from pipeline.utils import ensure_directory, write_json


CATEGORY_PATH = "Computing > Computers > Laptops"
MODEL = "234385"


@pytest.fixture()
def review_workspace(tmp_path: Path, monkeypatch) -> dict[str, str]:
    mappings_dir = tmp_path / "resources" / "mappings"
    ensure_directory(mappings_dir)
    monkeypatch.setattr(repo_paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(repo_paths, "FILTER_MAP_BASE_PATH", mappings_dir / "filter_map.base.json")
    monkeypatch.setattr(repo_paths, "FILTER_MAP_MANUAL_OVERRIDES_PATH", mappings_dir / "filter_map.manual_overrides.json")
    monkeypatch.setattr(repo_paths, "FILTER_MAP_MANUAL_OVERRIDES_BACKUP_DIR", mappings_dir / "backups" / "filter_overrides")
    monkeypatch.setattr(repo_paths, "FILTER_MAP_PATH", mappings_dir / "filter_map.json")
    monkeypatch.setattr(repo_paths, "FILTER_MAP_SYNC_REPORT_PATH", mappings_dir / "filter_map.sync_report.json")

    category_id = stable_category_id(CATEGORY_PATH)
    ram_group_id = stable_group_id(category_id, "Memory")
    screen_group_id = stable_group_id(category_id, "Screen")
    color_group_id = stable_group_id(category_id, "Color")
    old_group_id = stable_group_id(category_id, "Old")
    category = {
        "category_id": category_id,
        "key": "Laptops",
        "parent_category": "Computing",
        "leaf_category": "Computers",
        "sub_category": "Laptops",
        "path": CATEGORY_PATH,
        "url": "",
        "filter_groups": [
            {
                "group_id": ram_group_id,
                "name": "Memory",
                "required": True,
                "status": "active",
                "values": [{"value_id": stable_value_id(ram_group_id, "16 GB"), "value": "16 GB", "status": "active"}],
            },
            {
                "group_id": screen_group_id,
                "name": "Screen",
                "required": True,
                "status": "active",
                "values": [{"value_id": stable_value_id(screen_group_id, "15.6"), "value": "15.6", "status": "active"}],
            },
            {
                "group_id": color_group_id,
                "name": "Color",
                "required": False,
                "status": "inactive",
                "values": [{"value_id": stable_value_id(color_group_id, "Black"), "value": "Black", "status": "active"}],
            },
            {
                "group_id": old_group_id,
                "name": "Old",
                "required": False,
                "status": "active",
                "values": [{"value_id": stable_value_id(old_group_id, "Legacy"), "value": "Legacy", "status": "deprecated"}],
            },
        ],
    }
    payload = build_filter_map_payload([category], source="test")
    write_json(repo_paths.FILTER_MAP_BASE_PATH, payload)
    write_json(repo_paths.FILTER_MAP_PATH, payload)
    write_json(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH, default_manual_overrides())
    write_json(repo_paths.FILTER_MAP_SYNC_REPORT_PATH, {"ok": True})

    return {
        "category_id": category_id,
        "ram_group_id": ram_group_id,
        "screen_group_id": screen_group_id,
        "color_group_id": color_group_id,
        "old_group_id": old_group_id,
    }


def _write_prepared(model: str, *, taxonomy: TaxonomyResolution, specs: list[tuple[str, str]]) -> None:
    model_root = repo_paths.model_root_path(model)
    scrape_dir = ensure_directory(model_root / "scrape")
    source = SourceProductData(key_specs=[SpecItem(label=label, value=value) for label, value in specs])
    write_json(scrape_dir / f"{model}.source.json", source.to_dict())
    write_json(scrape_dir / f"{model}.normalized.json", {"taxonomy": taxonomy.to_dict()})


def _client() -> TestClient:
    return TestClient(create_app())


def test_filter_review_routes_are_included_in_create_app() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/filter-review/{model}" in paths
    assert "/api/filter-review/{model}/approve" in paths
    methods: dict[str, set[str]] = {}
    for route in create_app().routes:
        if route.path.startswith("/api/filter-review"):
            methods.setdefault(route.path, set()).update(route.methods)
    assert "GET" in methods["/api/filter-review/{model}"]
    assert "PUT" in methods["/api/filter-review/{model}"]
    assert "POST" in methods["/api/filter-review/{model}/approve"]


def test_get_review_state_fails_when_prepared_artifacts_are_missing(review_workspace) -> None:
    response = _client().get("/api/filter-review/missing")
    assert response.status_code == 404
    assert "Run prepare first" in response.json()["detail"]


def test_get_review_state_loads_category_id_and_reports_missing_required(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[("Memory", "16 GB")],
    )
    response = _client().get(f"/api/filter-review/{MODEL}")
    payload = response.json()
    assert response.status_code == 200
    assert payload["category_id"] == review_workspace["category_id"]
    assert payload["render_blocked"] is False
    assert [group["group_name"] for group in payload["missing_required_groups"]] == ["Screen"]
    assert "required_category_filter_missing:Screen" in payload["warnings"]


def test_get_review_state_falls_back_to_taxonomy_path_when_category_id_missing(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(taxonomy_path=CATEGORY_PATH),
        specs=[("Memory", "16 GB"), ("Screen", "15.6")],
    )
    state = get_filter_review_state(MODEL)
    assert state.category_id == review_workspace["category_id"]
    assert state.render_blocked is False


def test_get_review_state_includes_inactive_and_deprecated_diagnostics(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[("Memory", "16 GB"), ("Screen", "15.6"), ("Color", "Black"), ("Old", "Legacy")],
    )
    payload = _client().get(f"/api/filter-review/{MODEL}").json()
    by_name = {group["group_name"]: group for group in payload["groups"]}
    assert by_name["Color"]["inactive_group"] is True
    assert by_name["Old"]["deprecated_value"] is True


def test_put_saves_canonical_review_artifact_and_requires_reapproval(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[("Memory", "16 GB")],
    )
    review_path = repo_paths.category_filter_review_path(MODEL)
    ensure_directory(review_path.parent)
    write_json(
        review_path,
        {
            "approved": True,
            "approved_at": "2026-05-02T00:00:00+00:00",
            "values": {"Screen": "15.6"},
        },
    )

    response = _client().put(
        f"/api/filter-review/{MODEL}",
        json={"values": [{"group_id": review_workspace["screen_group_id"], "group_name": "Screen", "value": "17"}]},
    )
    assert response.status_code == 200
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["approved"] is False
    assert payload["approved_at"] is None
    assert list(payload["values"]) == [review_workspace["screen_group_id"]]
    assert payload["values"][review_workspace["screen_group_id"]]["group_name"] == "Screen"


def test_put_rejects_empty_group_names_and_values(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[],
    )
    assert _client().put(f"/api/filter-review/{MODEL}", json={"values": [{"group_name": "", "value": "1"}]}).status_code == 422
    assert _client().put(f"/api/filter-review/{MODEL}", json={"values": [{"group_name": "Screen", "value": ""}]}).status_code == 422


def test_put_new_value_updates_manual_overrides_and_regenerates_filter_map_without_approval(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[("Screen", "15.6")],
    )
    response = _client().put(
        f"/api/filter-review/{MODEL}",
        json={"values": [{"group_id": review_workspace["ram_group_id"], "group_name": "Memory", "value": "32 GB"}]},
    )
    assert response.status_code == 200
    assert response.json()["approved"] is False
    manual = json.loads(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    value_id = stable_value_id(review_workspace["ram_group_id"], "32 GB")
    assert manual["categories"][review_workspace["category_id"]]["groups"][review_workspace["ram_group_id"]]["values"][value_id]["status"] == "active"
    final_map = json.loads(repo_paths.FILTER_MAP_PATH.read_text(encoding="utf-8"))
    group = next(group for group in final_map["by_category_id"][review_workspace["category_id"]]["filter_groups"] if group["group_id"] == review_workspace["ram_group_id"])
    assert sum(1 for value in group["values"] if value["value"] == "32 GB") == 1


def test_put_new_group_defaults_required_active_and_regenerates_filter_map(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[("Memory", "16 GB"), ("Screen", "15.6")],
    )
    response = _client().put(f"/api/filter-review/{MODEL}", json={"new_groups": [{"group_name": "Storage", "value": "512 GB"}]})
    assert response.status_code == 200
    storage_group_id = stable_group_id(review_workspace["category_id"], "Storage")
    manual = json.loads(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    storage = manual["categories"][review_workspace["category_id"]]["groups"][storage_group_id]
    assert storage["required"] is True
    assert storage["status"] == "active"
    assert next(iter(storage["values"].values()))["status"] == "active"
    final_map = json.loads(repo_paths.FILTER_MAP_PATH.read_text(encoding="utf-8"))
    assert any(group["group_id"] == storage_group_id for group in final_map["by_category_id"][review_workspace["category_id"]]["filter_groups"])


def test_approval_allows_missing_required_and_saves_review_value(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[("Memory", "16 GB")],
    )
    missing = _client().post(f"/api/filter-review/{MODEL}/approve")
    assert missing.status_code == 200
    assert missing.json()["approved"] is True

    _client().put(
        f"/api/filter-review/{MODEL}",
        json={"values": [{"group_id": review_workspace["screen_group_id"], "group_name": "Screen", "value": "15.6"}]},
    )
    approved = _client().post(f"/api/filter-review/{MODEL}/approve")
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["approved"] is True
    assert payload["approved_at"]


def test_put_group_update_changes_required_rule_and_regenerates_filter_map(review_workspace) -> None:
    _write_prepared(
        MODEL,
        taxonomy=TaxonomyResolution(category_id=review_workspace["category_id"], taxonomy_path=CATEGORY_PATH),
        specs=[("Memory", "16 GB")],
    )

    response = _client().put(
        f"/api/filter-review/{MODEL}",
        json={"group_updates": [{"group_id": review_workspace["screen_group_id"], "group_name": "Screen", "required": False}]},
    )

    assert response.status_code == 200
    payload = response.json()
    screen = next(group for group in payload["groups"] if group["group_id"] == review_workspace["screen_group_id"])
    assert screen["required"] is False
    assert screen["missing_required"] is False
    assert payload["missing_required_groups"] == []
    manual = json.loads(repo_paths.FILTER_MAP_MANUAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    assert manual["categories"][review_workspace["category_id"]]["groups"][review_workspace["screen_group_id"]]["required"] is False


def test_artifact_resolver_returns_category_filter_review_path_when_present(review_workspace) -> None:
    review_path = repo_paths.category_filter_review_path(MODEL)
    ensure_directory(review_path.parent)
    write_json(review_path, {"schema_version": 1, "values": {}})
    record = JobRecord(job_id="1", job_type=JobType.RENDER, status=JobStatus.SUCCEEDED, model=MODEL)
    artifacts = resolve_job_artifacts(record, repo_root=repo_paths.REPO_ROOT)
    assert any(artifact.name == "category_filter_review_path" and artifact.path == str(review_path) for artifact in artifacts)


def test_run_metadata_serializes_optional_category_filter_review_path(tmp_path: Path) -> None:
    model_root = tmp_path / "work" / MODEL
    ensure_directory(model_root)
    review_path = model_root / "review" / "category_filters.override.json"
    metadata_path = metadata_module.maybe_write_run_metadata(
        model=MODEL,
        run_type=RunType.RENDER,
        status=RunStatus.FAILED,
        model_root=model_root,
        artifacts=RunArtifacts(model_root=model_root, category_filter_review_path=review_path),
        requested_at="2026-05-02T00:00:00+00:00",
        started_at="2026-05-02T00:00:00+00:00",
        finished_at="2026-05-02T00:00:01+00:00",
    )
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["artifacts"]["category_filter_review_path"] == str(review_path)


def test_missing_review_artifact_does_not_fail_metadata_writing(tmp_path: Path) -> None:
    model_root = tmp_path / "work" / MODEL
    ensure_directory(model_root)
    metadata_path = metadata_module.maybe_write_run_metadata(
        model=MODEL,
        run_type=RunType.RENDER,
        status=RunStatus.FAILED,
        model_root=model_root,
        artifacts=RunArtifacts(model_root=model_root),
        requested_at="2026-05-02T00:00:00+00:00",
        started_at="2026-05-02T00:00:00+00:00",
        finished_at="2026-05-02T00:00:01+00:00",
    )
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["artifacts"]["category_filter_review_path"] is None
