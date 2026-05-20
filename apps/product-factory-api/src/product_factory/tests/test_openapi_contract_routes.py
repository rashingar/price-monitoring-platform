from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_PATH = REPO_ROOT / "docs" / "contracts" / "openapi.product-factory.json"

REQUIRED_ENDPOINTS: dict[str, set[str]] = {
    "/api/health": {"get"},
    "/api/jobs": {"get"},
    "/api/jobs/prepare": {"post"},
    "/api/jobs/authoring/intro-text": {"post"},
    "/api/jobs/authoring/seo-meta": {"post"},
    "/api/jobs/full-pipeline": {"post"},
    "/api/jobs/render": {"post"},
    "/api/jobs/publish": {"post"},
    "/api/jobs/{job_id}": {"get"},
    "/api/jobs/{job_id}/stop": {"post"},
    "/api/jobs/{job_id}/start": {"post"},
    "/api/jobs/{job_id}/retry": {"post"},
    "/api/jobs/{job_id}/logs": {"get"},
    "/api/jobs/{job_id}/artifacts": {"get"},
    "/api/filters/status": {"get"},
    "/api/filters/categories": {"get"},
    "/api/filters/categories/{category_id}": {"get"},
    "/api/filters/categories/{category_id}/groups": {"put"},
    "/api/filters/categories/{category_id}/groups/{group_id}": {"patch"},
    "/api/filters/categories/{category_id}/groups/{group_id}/values": {"put"},
    "/api/filters/categories/{category_id}/groups/{group_id}/values/{value_id}": {
        "patch"
    },
    "/api/filters/sync": {"post"},
    "/api/filters/sync-report": {"get"},
    "/api/filters/backups": {"get"},
    "/api/filters/backups/restore": {"post"},
    "/api/filter-review/{model}": {"get", "put"},
    "/api/filter-review/{model}/approve": {"post"},
    "/api/authoring/{model}": {"get"},
    "/api/authoring/{model}/intro-text": {"post"},
    "/api/authoring/{model}/intro-text/retry": {"post"},
    "/api/authoring/{model}/seo-meta": {"post"},
    "/api/authoring/{model}/seo-meta/retry": {"post"},
    "/api/settings": {"get", "patch"},
}


def test_openapi_snapshot_contains_ui_facing_product_factory_routes() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    paths = snapshot["paths"]

    missing: list[str] = []
    for path, methods in REQUIRED_ENDPOINTS.items():
        if path not in paths:
            missing.append(path)
            continue
        for method in methods:
            if method not in paths[path]:
                missing.append(f"{method.upper()} {path}")

    assert not missing, f"Missing Product Factory API contract routes: {missing}"


def test_openapi_snapshot_documents_authoring_posts_as_queued_jobs() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    paths = snapshot["paths"]

    for path in [
        "/api/authoring/{model}/intro-text",
        "/api/authoring/{model}/intro-text/retry",
        "/api/authoring/{model}/seo-meta",
        "/api/authoring/{model}/seo-meta/retry",
    ]:
        operation = paths[path]["post"]
        assert "202" in operation["responses"]
        schema_ref = operation["responses"]["202"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        assert schema_ref.endswith("/JobResponse")

    job_type_schema = snapshot["components"]["schemas"]["JobType"]
    assert {"authoring_intro", "authoring_seo", "full_pipeline"}.issubset(
        set(job_type_schema["enum"])
    )
